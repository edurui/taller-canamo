"""Configurable Access mapping. Historic amounts are evidence, not today's tax calculation."""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from .db import dumps
from .errors import AppError, require
from .validation import normalized, plate, iso_date, valid_tax_id

ALIASES = {
    'legacy_code': ['cod_cli', 'codigo', 'id_cliente', 'legacy_code'],
    'name': ['cliente', 'nombre', 'razon_social', 'name'],
    'tax_id': ['cif_o_nif', 'nif', 'cif', 'tax_id'], 'address': ['direccion', 'address'],
    'postal_code': ['codigo_postal', 'cp', 'postal_code'], 'city': ['poblacion', 'ciudad', 'cp_poblacion', 'city'],
    'province': ['provincia', 'cp_provincia', 'province'], 'phone': ['telefono1', 'telefono', 'phone'],
    'phone2': ['telefono2', 'phone2'], 'email': ['email', 'correo'],
    'plate': ['matricula', 'plate'], 'kind': ['tipo_de_vehiculo', 'tipo_vehiculo', 'kind'],
    'vin': ['n_chasis', 'vin', 'numero_de_chasis'], 'km': ['kms', 'km', 'kilometros'],
    'notes': ['observaciones', 'notas', 'notes'], 'make': ['marca', 'make'], 'model': ['modelo', 'model'],
    'full_number': ['factura', 'numero', 'full_number'], 'issue_date': ['fechafactura', 'fecha', 'issue_date'],
    'base': ['base', 'base_imponible'], 'tax': ['iva', 'cuota_iva'], 'total': ['total', 'total_factura'],
    'paid': ['cobrado', 'paid'], 'description': ['concepto', 'descripcion', 'description'],
    'quantity': ['cantidad', 'quantity'], 'unit_price': ['precio', 'unit_price'],
    'tax_rate': ['tipo_iva', 'porcentaje_iva', 'tax_rate'],
}
CUSTOMER_FIELDS = ('legacy_code', 'name', 'tax_id', 'address', 'postal_code', 'city', 'province', 'country', 'phone', 'phone2', 'email', 'notes')
VEHICLE_FIELDS = ('plate', 'make', 'model', 'vin', 'kind', 'km', 'notes')
ENTITIES = ('customers', 'vehicles', 'invoices')


def heading(text):
    return normalized(str(text)).replace(' ', '_').replace('\ufeff', '')


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def source_key(row, columns):
    require(isinstance(columns, list) and columns, 'Selecciona las columnas de la clave de origen.')
    values = [row.get(column) for column in columns]
    require(all(value is not None and str(value) != '' and not isinstance(value, (dict, list, bool)) for value in values), 'La clave de origen tiene valores vacíos o complejos.')
    return dumps([str(value) for value in values])


def scalar(value, label):
    require(value is None or isinstance(value, (str, int, float, Decimal)) and not isinstance(value, bool), f'{label}: el valor no es texto/número simple.')
    return '' if value is None else str(value)


def exact_decimal(value, separator='.'):
    text = scalar(value, 'Importe').strip()
    if separator == ',':
        require('.' not in text, 'No uses separadores de millares en importes con coma decimal.')
        text = text.replace(',', '.')
    else:
        require(',' not in text, 'El perfil usa punto decimal; revisa las comas del origen.')
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise AppError('Importe decimal no válido: ' + text[:60]) from exc
    require(number.is_finite() and abs(number) < Decimal('100000000000'), 'Importe fuera de rango.')
    return number


def cents(value, separator='.'):
    number = exact_decimal(value, separator) * 100
    require(number == number.to_integral_value(), 'El importe contiene fracciones de céntimo. Conserva el original y documenta su redondeo antes de importar.')
    return int(number)


def historic_date(value, date_format):
    text = scalar(value, 'Fecha').strip()
    if date_format == 'dmy':
        try:
            return datetime.strptime(text[:10], '%d/%m/%Y').date().isoformat()
        except ValueError as exc:
            raise AppError('La fecha no coincide con día/mes/año.') from exc
    return iso_date(text[:10])


def suggested_profile(manifest):
    tables = [table for table in manifest['tables'] if not table.get('linked')]
    def choose(*names):
        return next((table for name in names for table in tables if heading(table['name']) == heading(name)), None)
    def fields(table, names):
        if not table:
            return {}
        columns = {heading(column['name']): column['name'] for column in table['columns']}
        return {name: next((columns[alias] for alias in ALIASES.get(name, [name]) if alias in columns), '') for name in names}
    customer = choose('Clientes', 'customers', 'csv')
    invoice = choose('Facturas', 'invoices')
    line = choose('DETALLE', 'lines')
    cf = fields(customer, CUSTOMER_FIELDS)
    vf = fields(customer, VEHICLE_FIELDS)
    inf = fields(invoice, ('full_number', 'issue_date', 'base', 'tax', 'total', 'paid'))
    lf = fields(line, ('description', 'quantity', 'unit_price', 'base', 'tax_rate', 'tax'))
    if line and not lf.get('base'):
        lf['base'] = fields(line, ('total',))['total']
    ck = [cf['legacy_code']] if cf.get('legacy_code') else []
    ikc = fields(invoice, ('legacy_code',)).get('legacy_code')
    ik = [key for key in (ikc, inf.get('full_number')) if key]
    lk = [fields(line, ('legacy_code',)).get('legacy_code'), fields(line, ('full_number',)).get('full_number')]
    if not inf.get('issue_date') and line:
        date = fields(line, ('issue_date',)).get('issue_date')
        if date:
            inf['issue_date'] = '@lines.' + date
    return {'version': 1, 'customers': {'table': customer['name'] if customer else '', 'key': ck, 'fields': cf, 'joins': []},
            'vehicles': {'table': customer['name'] if customer and vf.get('plate') else '', 'key': ck + ([vf['plate']] if vf.get('plate') else []), 'customer_key': ck, 'fields': vf, 'ignore_blank': 'plate'},
            'invoices': {'table': invoice['name'] if invoice else '', 'key': ik, 'customer_key': [ikc] if ikc else [], 'fields': inf, 'snapshots': {'customer': {}, 'issuer': {}, 'vehicle': {}}},
            'lines': {'table': line['name'] if line else '', 'invoice_key': [key for key in lk if key], 'fields': lf, 'order_by': []},
            'options': {'decimal_separator': '.', 'date_format': 'iso'}, 'historical_calculation': None}


def validate_profile(profile, manifest):
    require(isinstance(profile, dict) and profile.get('version') == 1, 'Perfil de mapeo no compatible.')
    tables = {table['name']: table for table in manifest['tables']}
    require(any(profile.get(entity, {}).get('table') for entity in ENTITIES), 'Selecciona al menos una tabla para importar.')
    for entity in (*ENTITIES, 'lines'):
        config = profile.get(entity, {})
        require(isinstance(config, dict), 'Mapeo de tabla no válido.')
        name = config.get('table')
        if not name:
            continue
        table = tables.get(name)
        require(table and not table.get('linked'), f'{name}: selecciona una tabla local; los vínculos no se abren.')
        columns = {column['name'] for column in table['columns']}
        require(all(isinstance(key, str) and key in columns for key in config.get('key', config.get('invoice_key', []))), f'{name}: la clave usa columnas inexistentes.')
        require(config.get('key', config.get('invoice_key')), f'{name}: falta una clave estable.')
        for key, column in config.get('fields', {}).items():
            require(not column or column in columns or entity == 'invoices' and column.startswith('@lines.') or column.startswith('@join.'), f'{name}: campo {key} no disponible.')
        for snapshot in config.get('snapshots', {}).values():
            require(isinstance(snapshot, dict) and all(not column or column in columns for column in snapshot.values()), f'{name}: el snapshot debe venir de columnas originales.')
        for join in config.get('joins', []):
            target = tables.get(join.get('table'))
            require(target and not target.get('linked') and join.get('local') in columns, 'Relación postal/local no válida.')
            available = {column['name'] for column in target['columns']}
            require(join.get('foreign') in available and all(column in available for column in join.get('fields', {}).values()), 'Campos de relación no válidos.')
    options = profile.get('options', {})
    require(options.get('decimal_separator', '.') in ('.', ',') and options.get('date_format', 'iso') in ('iso', 'dmy'), 'Formato de fecha/decimal no válido.')
    calculation = profile.get('historical_calculation')
    if calculation:
        require(isinstance(calculation, dict) and str(calculation.get('evidence', '')).strip(), 'Indica la evidencia de la fórmula del informe antiguo.')
        rate = exact_decimal(calculation.get('tax_rate'))
        require(0 <= rate <= 100, 'Tipo histórico de IVA fuera de rango.')


def canonical_historical(invoice, *, legacy_v1=False):
    """Validate supplied historic figures without substituting a current tax regime."""
    require(isinstance(invoice, dict), 'Factura histórica no válida.')
    result = dict(invoice)
    require(str(result.get('full_number', '')).strip(), 'Falta el número original.')
    result['issue_date'] = iso_date(result.get('issue_date'))
    lines = result.get('lines')
    require(isinstance(lines, list) and len(lines) > 0, 'La factura no contiene líneas.')
    canonical = []
    derived = False
    for position, raw in enumerate(lines):
        require(isinstance(raw, dict), 'Línea histórica no válida.')
        description = scalar(raw.get('description'), 'Concepto')
        require(description.strip(), 'Falta el concepto histórico.')
        quantity_raw = raw.get('quantity', '1') if legacy_v1 else raw.get('quantity')
        price_raw = raw.get('unit_price')
        quantity = exact_decimal(quantity_raw) if quantity_raw is not None and str(quantity_raw) != '' else None
        price = exact_decimal(price_raw) if price_raw is not None and str(price_raw) != '' else None
        base = raw.get('base_cents')
        rate = raw.get('tax_rate')
        if legacy_v1 and base is None:
            # The old interchange contract explicitly used these defaults. New Access mappings never do.
            discount = exact_decimal(raw.get('discount', '0'))
            require(quantity is not None and price is not None, 'El paquete v1 necesita cantidad y precio para su desglose; usa v2 con importes originales si no constan.')
            base = int((quantity * price * (1 - discount / 100) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            rate = raw.get('tax_rate', '21')
            derived = True
        require(isinstance(base, int) and not isinstance(base, bool), 'Falta el importe de línea en céntimos.')
        if rate is not None and str(rate) != '':
            rate = str(exact_decimal(rate))
        else:
            rate = ''
        canonical.append({**raw, 'position': position, 'description': description, 'quantity': str(quantity) if quantity is not None else None, 'unit_price': str(price) if price is not None else None, 'discount': str(raw.get('discount', '0')), 'base_cents': base, 'tax_rate': rate, 'tax_kind': raw.get('tax_kind', 'subject'), 'tax_reason': raw.get('tax_reason', '')})
    base = result.get('base_cents')
    tax = result.get('tax_cents')
    if legacy_v1 and base is None:
        base = sum(line['base_cents'] for line in canonical)
        grouped = {}
        for line in canonical:
            grouped[line['tax_rate']] = grouped.get(line['tax_rate'], 0) + line['base_cents']
        taxes = [{'rate': rate, 'kind': 'subject', 'reason': '', 'base_cents': subtotal, 'tax_cents': int((Decimal(subtotal) * Decimal(rate) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))} for rate, subtotal in grouped.items()]
        tax = sum(group['tax_cents'] for group in taxes)
        result['taxes'] = taxes
        derived = True
    total = result.get('total_cents')
    require(all(isinstance(value, int) and not isinstance(value, bool) and abs(value) < 10_000_000_000_000 for value in (base, tax, total)), 'Faltan base, cuota o total originales en céntimos, o exceden el límite de 100.000 millones de euros.')
    differences = {'lines_base_cents': sum(line['base_cents'] for line in canonical) - base, 'base_tax_total_cents': base + tax - total}
    result.update({'base_cents': base, 'tax_cents': tax, 'total_cents': total, 'lines': canonical, 'amount_differences': differences})
    result.setdefault('taxes', [{'rate': '', 'kind': 'historical', 'reason': 'Desglose histórico no conservado', 'base_cents': base, 'tax_cents': tax}])
    require(isinstance(result['taxes'], list) and result['taxes'], 'El desglose histórico de impuestos no es válido.')
    for group in result['taxes']:
        require(isinstance(group, dict) and all(isinstance(group.get(key), int) and not isinstance(group[key], bool) for key in ('base_cents', 'tax_cents')), 'Cada grupo fiscal histórico necesita base y cuota originales en céntimos.')
        group.setdefault('rate', ''); group.setdefault('kind', 'historical'); group.setdefault('reason', '')
        if group['rate'] != '': group['rate'] = str(exact_decimal(group['rate']))
    differences['tax_groups_base_cents'] = sum(group['base_cents'] for group in result['taxes']) - base
    differences['tax_groups_tax_cents'] = sum(group['tax_cents'] for group in result['taxes']) - tax
    result['customer_snapshot'] = result.get('customer_snapshot') or {}
    result['issuer_snapshot'] = result.get('issuer_snapshot') or {}
    result['vehicle_snapshot'] = result.get('vehicle_snapshot') or None
    require(all(isinstance(result[key], dict) for key in ('customer_snapshot', 'issuer_snapshot')), 'Snapshot histórico no válido.')
    paid = result.get('paid_cents')
    require(paid is None or isinstance(paid, int) and not isinstance(paid, bool) and min(total, 0) <= paid <= max(total, 0), 'El saldo histórico conocido no está dentro del total.')
    result['payment_state'] = 'known' if paid is not None else 'unknown'
    result['snapshot_certainty'] = {key: ('source' if result[key + '_snapshot'] else 'unknown') for key in ('customer', 'issuer', 'vehicle')}
    result['legacy_v1_derived'] = derived
    return result


def map_tables(stage, profile, manifest):
    validate_profile(profile, manifest)
    sep = profile.get('options', {}).get('decimal_separator', '.')
    date_format = profile.get('options', {}).get('date_format', 'iso')
    calculation = profile.get('historical_calculation')
    conn = stage.connect()
    try:
        conn.execute('DELETE FROM records'); conn.execute('DELETE FROM incidents'); conn.execute('DELETE FROM line_rows')
        def incident(level, entity, key, message):
            conn.execute('INSERT INTO incidents(level,entity,source_key,message) VALUES(?,?,?,?)', (level, entity, key, message))
        lines_config = profile.get('lines', {})
        if lines_config.get('table'):
            for raw in conn.execute('SELECT row_number,data FROM raw_rows WHERE table_name=? ORDER BY row_number', (lines_config['table'],)):
                row = json.loads(raw['data'])
                try:
                    key = source_key(row, lines_config.get('invoice_key'))
                    conn.execute('INSERT INTO line_rows VALUES(?,?,?)', (key, raw['row_number'], raw['data']))
                except AppError as exc:
                    incident('error', 'lines', str(raw['row_number']), str(exc))
        for entity in ENTITIES:
            config = profile.get(entity, {})
            if not config.get('table'):
                continue
            cursor = conn.execute('SELECT row_number,data FROM raw_rows WHERE table_name=? ORDER BY row_number', (config['table'],))
            for raw in cursor:
                row = json.loads(raw['data']); key = 'row:' + str(raw['row_number'])
                try:
                    fields = config.get('fields', {})
                    if config.get('ignore_blank') and not row.get(fields.get(config['ignore_blank'])):
                        continue
                    key = source_key(row, config.get('key'))
                    original = {'table': config['table'], 'row_number': raw['row_number'], 'row': row}
                    values = {name: row.get(column) for name, column in fields.items() if column}
                    for join in config.get('joins', []):
                        # Parameterized JSON path; no source field becomes SQL syntax.
                        matches = conn.execute('SELECT data FROM raw_rows WHERE table_name=? AND CAST(json_extract(data,?) AS TEXT)=?', (join['table'], '$.' + json.dumps(join['foreign']), str(row.get(join['local'], '')))).fetchall()
                        require(len(matches) <= 1, 'Relación ambigua: ' + join['table'])
                        if matches:
                            joined = json.loads(matches[0]['data'])
                            values.update({name: joined.get(column) for name, column in join.get('fields', {}).items()})
                            original.setdefault('joins', []).append(joined)
                        else:
                            incident('warning', entity, key, 'Relación sin coincidencia: ' + join['table'])
                    if entity == 'customers':
                        value = {name: scalar(values.get(name), name) for name in CUSTOMER_FIELDS}
                        require(value['legacy_code'] and value['name'].strip(), 'Falta código antiguo o nombre.')
                        if value['tax_id'] and not valid_tax_id(value['tax_id']):
                            incident('warning', entity, key, 'NIF antiguo no válido; se conserva y debe revisarse antes de emitir.')
                    elif entity == 'vehicles':
                        value = {name: scalar(values.get(name), name) for name in VEHICLE_FIELDS}
                        value['customer_key'] = source_key(row, config.get('customer_key'))
                        require(3 <= len(plate(value['plate'])) <= 15, 'Matrícula/identificador no válido.')
                        km = exact_decimal(value['km'] or '0', sep)
                        require(km == km.to_integral_value() and 0 <= km <= 10000000, 'Kilometraje no válido.')
                        value['km'] = int(km)
                    else:
                        raw_lines = [json.loads(item['data']) for item in conn.execute('SELECT data FROM line_rows WHERE source_key=? ORDER BY row_number', (key,))]
                        order = lines_config.get('order_by') or []
                        if order:
                            raw_lines.sort(key=lambda line: tuple(str(line.get(field, '')) for field in order))
                        original['lines'] = raw_lines
                        for name, column in fields.items():
                            if column.startswith('@lines.'):
                                candidates = {scalar(line.get(column[7:]), name) for line in raw_lines}
                                require(len(candidates) == 1, 'La fecha/cabecera calculada desde líneas es ambigua: ' + name)
                                values[name] = next(iter(candidates))
                        lf = lines_config.get('fields', {})
                        line_values = []
                        for line in raw_lines:
                            mapped = {name: line.get(column) for name, column in lf.items() if column}
                            line_value = {name: scalar(mapped.get(name), name) for name in ('description', 'quantity', 'unit_price', 'tax_rate')}
                            line_value['quantity'] = str(exact_decimal(line_value['quantity'], sep)) if line_value['quantity'] else None
                            line_value['unit_price'] = str(exact_decimal(line_value['unit_price'], sep)) if line_value['unit_price'] else None
                            line_value['base_cents'] = cents(mapped.get('base'), sep)
                            if mapped.get('tax') is not None:
                                line_value['tax_cents'] = cents(mapped['tax'], sep)
                            line_values.append(line_value)
                        value = {'customer_key': source_key(row, config.get('customer_key')), 'full_number': scalar(values.get('full_number'), 'Número'), 'issue_date': historic_date(values.get('issue_date'), date_format), 'lines': line_values,
                                 'base_cents': cents(values['base'], sep) if values.get('base') is not None else None,
                                 'tax_cents': cents(values['tax'], sep) if values.get('tax') is not None else None,
                                 'total_cents': cents(values['total'], sep) if values.get('total') is not None else None,
                                 'paid_cents': cents(values['paid'], sep) if values.get('paid') is not None and str(values['paid']) != '' else None}
                        if config.get('vehicle_key'):
                            value['vehicle_key'] = source_key(row, config['vehicle_key'])
                        if calculation and any(value[name] is None for name in ('base_cents', 'tax_cents', 'total_cents')):
                            base = sum(line['base_cents'] for line in line_values)
                            tax = int((Decimal(base) * exact_decimal(calculation['tax_rate']) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                            for name, amount in (('base_cents', base), ('tax_cents', tax), ('total_cents', base + tax)):
                                if value[name] is None:
                                    value[name] = amount
                            value['calculation_evidence'] = calculation
                            incident('warning', entity, key, 'Importes reconstruidos mediante la fórmula histórica documentada; no son una instantánea impresa conservada.')
                        for part in ('customer', 'issuer', 'vehicle'):
                            value[part + '_snapshot'] = {name: scalar(row.get(column), name) for name, column in config.get('snapshots', {}).get(part, {}).items() if column}
                        value = canonical_historical(value)
                    conn.execute('INSERT INTO records(entity,source_key,source_hash,payload,original) VALUES(?,?,?,?,?)', (entity, key, fingerprint({'payload': value, 'original': {k: v for k, v in original.items() if k != 'row_number'}}), dumps(value), dumps(original)))
                except (AppError, ValueError, TypeError) as exc:
                    incident('error', entity, key, str(exc))
                    conn.execute('INSERT INTO records(entity,source_key,source_hash,payload,original) VALUES(?,?,?,?,?)', (entity, key, fingerprint(row), dumps({'invalid': True}), dumps({'table': config['table'], 'row_number': raw['row_number'], 'row': row})))
        # A mapped detail without a header is never silently dropped.
        for orphan in conn.execute("SELECT DISTINCT l.source_key FROM line_rows l LEFT JOIN records r ON r.entity='invoices' AND r.source_key=l.source_key WHERE r.position IS NULL"):
            incident('error', 'lines', orphan['source_key'], 'Líneas sin cabecera de factura mapeada.')
        for duplicate in conn.execute('SELECT entity,source_key,count(*) AS n FROM records GROUP BY entity,source_key HAVING n>1'):
            incident('error', duplicate['entity'], duplicate['source_key'], 'Clave de origen duplicada; amplía la clave compuesta o resuelve en una copia.')
        conn.commit()
    finally:
        conn.close()
