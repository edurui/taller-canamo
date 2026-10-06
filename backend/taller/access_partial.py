"""Evidence-preserving mapping for archives without stored invoice totals.

No tax rate, rounding policy, invoice date or vehicle owner is inferred here.
Unresolvable identities remain in staging, with a rule and a source row pointer.
"""
from collections import defaultdict
import json

from .access_mapping import (CUSTOMER_FIELDS, VEHICLE_FIELDS, exact_decimal, cents,
                             fingerprint, historic_date, scalar, source_key)
from .db import dumps
from .errors import AppError, require
from .validation import iso_date, plate, valid_tax_id


def canonical_partial(invoice):
    result = dict(invoice)
    result['full_number'] = scalar(result.get('full_number'), 'Número')
    require(result['full_number'].strip(), 'Falta el número original.')
    date = result.get('issue_date')
    result['issue_date'] = iso_date(date) if date is not None else None
    result['date_state'] = 'known' if date is not None else ('conflict' if result.get('date_state') == 'conflict' else 'unknown')
    require(isinstance(result.get('lines'), list), 'Las líneas históricas deben ser una lista.')
    lines = []
    for position, raw in enumerate(result['lines']):
        require(isinstance(raw, dict), 'Línea histórica no válida.')
        line = dict(raw)
        line.update(position=position, description=scalar(raw.get('description'), 'Concepto'))
        for name in ('quantity', 'unit_price', 'amount_raw'):
            value = raw.get(name)
            line[name] = str(exact_decimal(value)) if value is not None and str(value).strip() else None
        for name in ('base_cents', 'tax_cents'):
            value = raw.get(name)
            require(value is None or type(value) is int and abs(value) < 10_000_000_000_000, 'Importe histórico fuera de rango.')
            line[name] = value
        rate = raw.get('tax_rate')
        line['tax_rate'] = str(exact_decimal(rate)) if rate is not None and str(rate).strip() else ''
        line.setdefault('tax_kind', 'historical'); line.setdefault('tax_reason', '')
        lines.append(line)
    result['lines'] = lines
    names = ('base_cents', 'tax_cents', 'total_cents')
    for name in names:
        value = result.get(name)
        require(value is None or type(value) is int and abs(value) < 10_000_000_000_000, 'Importe histórico fuera de rango.')
        result[name] = value
    known = sum(result[name] is not None for name in names)
    result['amounts_state'] = 'known' if known == 3 else 'partial' if known else 'unknown'
    result.setdefault('amounts_provenance', {'policy': 'Only explicit source amounts; no tax or rounding inferred'})
    require(isinstance(result['amounts_provenance'], dict), 'Procedencia de importes no válida.')
    require(isinstance(result.get('date_candidates', []), list) and all(isinstance(value, str) for value in result.get('date_candidates', [])), 'Candidatos de fecha no válidos.')
    differences = {}
    if lines and result['base_cents'] is not None and all(line['base_cents'] is not None for line in lines):
        differences['lines_base_cents'] = sum(line['base_cents'] for line in lines) - result['base_cents']
    if known == 3:
        differences['base_tax_total_cents'] = result['base_cents'] + result['tax_cents'] - result['total_cents']
    taxes = result.get('taxes', [])
    require(isinstance(taxes, list), 'Desglose histórico no válido.')
    taxes = [dict(group) if isinstance(group, dict) else group for group in taxes]
    for group in taxes:
        require(isinstance(group, dict) and all(type(group.get(name)) is int for name in ('base_cents', 'tax_cents')), 'Desglose fiscal no válido.')
        group.setdefault('rate', ''); group.setdefault('kind', 'historical'); group.setdefault('reason', '')
        if group['rate'] != '':
            group['rate'] = str(exact_decimal(group['rate']))
    if taxes:
        for field in ('base_cents', 'tax_cents'):
            if result[field] is not None:
                differences['tax_groups_' + field] = sum(group[field] for group in taxes) - result[field]
    result['taxes'] = taxes
    result['amount_differences'] = differences
    paid = result.get('paid_cents')
    total = result['total_cents']
    require(paid is None or total is not None and type(paid) is int and min(total, 0) <= paid <= max(total, 0), 'El cobro conocido necesita un total original conocido.')
    result['payment_state'] = 'known' if paid is not None else 'unknown'
    for part in ('customer', 'issuer', 'vehicle'):
        snapshot = result.get(part + '_snapshot') or {}
        require(isinstance(snapshot, dict), 'Snapshot histórico no válido.')
        result[part + '_snapshot'] = snapshot
    result['snapshot_certainty'] = {part: 'source' if result[part + '_snapshot'] else 'unknown' for part in ('customer', 'issuer', 'vehicle')}
    result['legacy_v1_derived'] = False
    return result


def map_partial_tables(stage, profile, manifest):
    """Map safe identities and retain exceptions without dropping any source row."""
    conn = stage.connect()
    sep = profile.get('options', {}).get('decimal_separator', '.')
    date_format = profile.get('options', {}).get('date_format', 'iso')
    try:
        conn.execute('DELETE FROM records'); conn.execute('DELETE FROM incidents'); conn.execute('DELETE FROM line_rows')
        conn.execute('DELETE FROM row_decisions')

        def incident(entity, key, message, level='warning'):
            conn.execute('INSERT INTO incidents(level,entity,source_key,message) VALUES(?,?,?,?)', (level, entity, key, message))

        def decision(entity, table, number, disposition, rule, key):
            conn.execute('INSERT OR REPLACE INTO row_decisions VALUES(?,?,?,?,?,?)', (entity, table, number, disposition, rule, key))

        def record(entity, key, value, original, rule=None):
            value = {**value, 'preservation': 'partial'}
            if rule:
                value = {**value, 'quarantine_reason': rule}
            def semantic(item):
                if isinstance(item, dict):
                    return {name: semantic(content) for name, content in item.items() if name not in ('row_number', 'source_row')}
                if isinstance(item, list):
                    return [semantic(content) for content in item]
                return item
            conn.execute('INSERT INTO records(entity,source_key,source_hash,payload,original,action) VALUES(?,?,?,?,?,?)',
                         (entity, key, fingerprint(semantic({'payload': value, 'original': original})), dumps(value), dumps(original), 'quarantine' if rule else 'insert'))

        def rows(table):
            for raw in conn.execute('SELECT row_number,data FROM raw_rows WHERE table_name=? ORDER BY row_number', (table,)):
                yield raw['row_number'], json.loads(raw['data'])

        def text(value):
            return scalar(value, 'Campo')

        # Customers remain real identities. Missing names are not invented.
        for entity, fields in (('customers', CUSTOMER_FIELDS), ('vehicles', VEHICLE_FIELDS)):
            config = profile.get(entity, {})
            if not config.get('table'):
                continue
            for number, row in rows(config['table']):
                original = {'table': config['table'], 'row_number': number, 'row': row}
                key = 'row:' + config['table'] + ':' + str(number)
                try:
                    values = {name: text(row.get(column)) for name, column in config.get('fields', {}).items() if column}
                    if entity == 'vehicles' and not values.get('plate', '').strip():
                        decision(entity, config['table'], number, 'not_applicable', 'no_vehicle_identifier', key)
                        continue
                    key = source_key(row, config['key'])
                    value = {name: values.get(name, '') for name in fields}
                    if entity == 'customers':
                        require(value['legacy_code'].strip() and value['name'].strip(), 'customer_identity_incomplete')
                        for join in config.get('joins', []):
                            matches = conn.execute('SELECT data FROM raw_rows WHERE table_name=? AND CAST(json_extract(data,?) AS TEXT)=?', (join['table'], '$.' + json.dumps(join['foreign']), str(row.get(join['local'], '')))).fetchall()
                            if len(matches) == 1:
                                joined = json.loads(matches[0]['data'])
                                value.update({name: text(joined.get(column)) for name, column in join.get('fields', {}).items()})
                                original.setdefault('joins', []).append(joined)
                            else:
                                incident(entity, key, 'Relación postal sin coincidencia única; se conserva el código original.')
                        if value['tax_id'] and not valid_tax_id(value['tax_id']):
                            incident(entity, key, 'NIF antiguo no válido; se conserva y debe revisarse antes de emitir.')
                    else:
                        value['customer_key'] = source_key(row, config['customer_key'])
                        require(3 <= len(plate(value['plate'])) <= 15, 'vehicle_identifier_invalid')
                        km = exact_decimal(value['km'] or '0', sep)
                        require(km == km.to_integral_value() and 0 <= km <= 10000000, 'vehicle_km_invalid')
                        value['km'] = int(km)
                    record(entity, key, value, original)
                    decision(entity, config['table'], number, 'mapped', 'source_identity', key)
                except AppError as exc:
                    rule = str(exc) if str(exc).startswith(('customer_', 'vehicle_')) else 'identity_incomplete'
                    record(entity, key, {'invalid': True}, original, rule)
                    decision(entity, config['table'], number, 'quarantine', rule, key)
                    incident(entity, key, 'Conservado para revisión: identidad incompleta o identificador no válido.')

        # A repeated client/vehicle key is not a stable identity, even if the
        # legacy_code collision check sees the same source_key twice.
        for duplicate in conn.execute("SELECT entity,source_key FROM records GROUP BY entity,source_key HAVING count(*)>1").fetchall():
            for record_row in conn.execute('SELECT position,payload FROM records WHERE entity=? AND source_key=?', tuple(duplicate)).fetchall():
                value = json.loads(record_row['payload']); value['quarantine_reason'] = 'duplicate_source_identity'
                conn.execute("UPDATE records SET payload=?,action='quarantine' WHERE position=?", (dumps(value), record_row['position']))
            conn.execute("UPDATE row_decisions SET disposition='quarantine',rule='duplicate_source_identity' WHERE entity=? AND source_key=?", tuple(duplicate))
            incident(duplicate['entity'], duplicate['source_key'], 'Clave de cliente/vehículo duplicada: todas sus filas se conservan para revisar la identidad.')
        config = profile.get('invoices', {})
        lc = profile.get('lines', {})
        if not config.get('table'):
            conn.commit(); return
        headers = defaultdict(list)
        for number, row in rows(config['table']):
            try:
                key = source_key(row, config['key'])
                headers[key].append((number, row))
            except AppError:
                key = 'row:' + config['table'] + ':' + str(number)
                record('invoices', key, {'invalid': True}, {'table': config['table'], 'row_number': number, 'row': row}, 'header_identity_incomplete')
                decision('invoices', config['table'], number, 'quarantine', 'header_identity_incomplete', key)
                incident('invoices', key, 'Cabecera sin clave completa; conservada para revisión, sin borrar el original.')
        if lc.get('table'):
            for number, row in rows(lc['table']):
                try:
                    key = source_key(row, lc['invoice_key'])
                    conn.execute('INSERT INTO line_rows VALUES(?,?,?)', (key, number, dumps(row)))
                except AppError:
                    decision('lines', lc['table'], number, 'quarantine', 'line_identity_incomplete', 'row:' + str(number))
                    incident('lines', 'row:' + str(number), 'Línea sin clave completa; conservada en originales y pendiente de atribución.')
        # A complete compound identity in detail is evidence of a historical record,
        # even if its header is absent. No client is joined by invoice number alone.
        keys = list(headers)
        keys.extend(row[0] for row in conn.execute('SELECT DISTINCT source_key FROM line_rows ORDER BY source_key') if row[0] not in headers)
        for key in keys:
            group = headers.get(key, [])
            source_lines = [(raw['row_number'], json.loads(raw['data'])) for raw in conn.execute('SELECT row_number,data FROM line_rows WHERE source_key=? ORDER BY row_number', (key,))]
            if lc.get('order_by'):
                source_lines.sort(key=lambda item: tuple(str(item[1].get(field, '')) for field in lc['order_by']))
            original = {'table': config['table'], 'headers': [{'row_number': number, 'row': row} for number, row in group],
                        'lines_table': lc.get('table'), 'lines': [{'row_number': number, 'row': row} for number, row in source_lines]}
            try:
                require(len({fingerprint(row) for _, row in group}) <= 1, 'header_key_conflict')
                if group:
                    row = group[0][1]
                    owner = source_key(row, config['customer_key'])
                    fields = config.get('fields', {})
                    values = {name: row.get(column) for name, column in fields.items() if column and not column.startswith('@lines.')}
                else:
                    # Recover only columns shared by the explicitly mapped compound key.
                    require(all(column in config['key'] for column in config['customer_key']), 'orphan_identity_unmapped')
                    parts = json.loads(key)
                    row = dict(zip(config['key'], parts))
                    owner = source_key(row, config['customer_key'])
                    fields = config.get('fields', {})
                    require(fields.get('full_number') in row, 'orphan_number_unmapped')
                    values = {'full_number': row[fields['full_number']]}
                    incident('invoices', key, 'Cabecera ausente: identidad recuperada de la clave completa de las líneas; procedencia conservada.')
                date_values = []
                date_column = fields.get('issue_date', '')
                if date_column.startswith('@lines.'):
                    date_values = [line.get(date_column[7:]) for _, line in source_lines]
                elif values.get('issue_date') is not None:
                    date_values = [values['issue_date']]
                dates = set(); invalid_date = False
                for raw_date in date_values:
                    if raw_date is None or str(raw_date).strip() == '':
                        continue
                    try:
                        dates.add(historic_date(raw_date, date_format))
                    except AppError:
                        invalid_date = True
                reliable_date = next(iter(dates)) if len(dates) == 1 and not invalid_date else None
                lf = lc.get('fields', {})
                mapped_lines = []
                for number, line in source_lines:
                    mapped = {name: line.get(column) for name, column in lf.items() if column}
                    item = {'description': text(mapped.get('description')), 'base_cents': None, 'tax_cents': None,
                            'amount_semantics': 'unclassified_source_amount'}
                    for field in ('quantity', 'unit_price', 'tax_rate'):
                        raw_value = mapped.get(field)
                        try:
                            item[field] = str(exact_decimal(raw_value, sep)) if raw_value is not None and str(raw_value).strip() else None
                        except AppError:
                            item[field] = None
                            item.setdefault('unknown_fields', []).append(field)
                    # TOTAL from detail is retained verbatim as decimal evidence. It
                    # is not proof of tax base or of printed rounding in the report.
                    raw_amount = mapped.get('base')
                    try:
                        item['amount_raw'] = str(exact_decimal(raw_amount, sep)) if raw_amount is not None and str(raw_amount).strip() else None
                    except AppError:
                        item['amount_raw'] = None
                    item['amount_source_value'] = raw_amount
                    mapped_lines.append(item)
                value = {'preservation': 'partial', 'customer_key': owner, 'full_number': text(values.get('full_number')),
                         'issue_date': reliable_date, 'date_state': 'conflict' if len(dates) > 1 or invalid_date else 'unknown',
                         'date_candidates': sorted(dates), 'lines': mapped_lines, 'paid_cents': None,
                         'header_state': 'source' if group else 'recovered_from_lines',
                         'amounts_provenance': {'policy': 'source_only_no_rounding', 'fields': {}, 'line_amount': 'unclassified'}}
                if config.get('vehicle_key'):
                    try:
                        value['vehicle_key'] = source_key(row, config['vehicle_key'])
                    except AppError:
                        value['vehicle_identity_state'] = 'unknown'
                        incident('invoices', key, 'Clave de vehículo incompleta: histórico conservado sin atribuir un vehículo.')
                for field, destination in (('base', 'base_cents'), ('tax', 'tax_cents'), ('total', 'total_cents')):
                    value[destination] = None
                    raw_amount = values.get(field)
                    if raw_amount is not None and str(raw_amount).strip():
                        try:
                            value[destination] = cents(raw_amount, sep)
                        except AppError:
                            pass
                    value['amounts_provenance']['fields'][destination] = {'column': fields.get(field) or None, 'raw': raw_amount, 'state': 'source' if value[destination] is not None else 'unknown'}
                if values.get('paid') is not None and str(values['paid']).strip() and value['total_cents'] is not None:
                    value['paid_cents'] = cents(values['paid'], sep)
                for part in ('customer', 'issuer', 'vehicle'):
                    value[part + '_snapshot'] = {name: text(row.get(column)) for name, column in config.get('snapshots', {}).get(part, {}).items() if column}
                if profile.get('historical_calculation'):
                    incident('invoices', key, 'El modo de conservación no aplica fórmulas globales de IVA; conserva la evidencia sin reconstruir importes.')
                value = canonical_partial(value)
                record('invoices', key, value, original)
                for number, _ in group:
                    decision('invoices', config['table'], number, 'mapped', 'duplicate_identical_header' if len(group) > 1 else 'source_identity', key)
                for number, _ in source_lines:
                    decision('lines', lc['table'], number, 'mapped', 'recovered_header' if not group else 'source_identity', key)
                if value['date_state'] != 'known':
                    incident('invoices', key, 'Fecha no fiable o no conservada: No consta; se conservan todos los valores de las líneas.')
                if not source_lines:
                    incident('invoices', key, 'Cabecera histórica sin líneas; se conserva sin inventar conceptos ni importes.')
                if len(group) > 1:
                    incident('invoices', key, 'Cabeceras idénticas con la misma clave: un histórico, todos los originales conservados.')
            except (AppError, ValueError, TypeError):
                record('invoices', key, {'invalid': True}, original, 'invoice_identity_conflict')
                for number, _ in group:
                    decision('invoices', config['table'], number, 'quarantine', 'invoice_identity_conflict', key)
                for number, _ in source_lines:
                    decision('lines', lc['table'], number, 'quarantine', 'invoice_identity_conflict', key)
                incident('invoices', key, 'Identidad/cabecera histórica en conflicto; original completo conservado para revisión.')
        conn.commit()
    finally:
        conn.close()
