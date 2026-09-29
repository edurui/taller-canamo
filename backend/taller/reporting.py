"""Operational reports and a documented, lossless portable export (not a restore)."""
import base64
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from decimal import Decimal
from pathlib import Path

from . import __version__
from .db import SCHEMA_VERSION, dumps, uid
from .documents import PAID_SQL, PAYMENT_KNOWN_SQL, METHODS
from .errors import require
from .validation import iso_date, now, today
from .backups import Backups, CHUNK_BYTES, MAX_BYTES, MAX_FILES, _valid_name
from .certificates import private_directory

EXPORT_TABLES = (
    'customers', 'vehicles', 'vehicle_owners', 'series', 'documents', 'payments',
    'document_payment_baselines', 'suppliers', 'products', 'stock_movements', 'events',
    'event_exceptions', 'notifications', 'fiscal_records', 'fiscal_outbox', 'fiscal_attempts',
    'fiscal_channels', 'fiscal_reconciliations', 'fiscal_wire_evidence', 'imports',
    'import_sources', 'import_profiles', 'import_batches', 'import_records', 'import_changes',
    'b2b_documents', 'b2b_events', 'b2b_obligations', 'b2b_source_files', 'audit', 'schema_migrations',
)
CSV_TABLES = {'customers': 'customers', 'vehicles': 'vehicles', 'invoices': 'documents',
              'stock': 'products', 'suppliers': 'suppliers', 'payments': 'payments',
              'stock_movements': 'stock_movements'}
LINE_FIELDS = ['document_id', 'kind', 'status', 'number', 'issue_date', 'customer_id', 'customer_name',
               'vehicle_id', 'plate', 'position', 'product_id', 'description', 'quantity', 'unit_price',
               'discount', 'tax_rate', 'base_cents', 'tax_cents', 'total_cents', 'original_line_json']


def _range(start='', end=''):
    first = iso_date(start) if start else '0001-01-01'
    last = iso_date(end) if end else '9999-12-31'
    require(first <= last, 'La fecha final no puede ser anterior a la inicial.')
    return first, last


def _json(value):
    if isinstance(value, bytes):
        return {'$binary': {'encoding': 'base64', 'sha256': hashlib.sha256(value).hexdigest(),
                            'data': base64.b64encode(value).decode('ascii')}}
    raise TypeError('Valor no exportable')


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True, default=_json).encode('utf-8')


def _cell(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        return json_bytes(value).decode() if isinstance(value, (dict, list, bytes)) else str(value)
    # Spreadsheet protection applies to CSV; JSON retains the exact original.
    dangerous = value.lstrip(' \t\r\n\ufeff').startswith(('=', '+', '-', '@'))
    return "'" + value if dangerous or value.startswith(('\t', '\r', '\n')) or re.fullmatch(r'0\d+', value) else value


def _csv_write(output, rows, fields):
    class TextSink:
        def write(self, value):
            return output.write(value.encode('utf-8'))
    output.write(b'\xef\xbb\xbf')
    writer = csv.DictWriter(TextSink(), fieldnames=fields, delimiter=';', lineterminator='\r\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key:_cell(row.get(key)) for key in fields})


def csv_bytes(rows, fields):
    output = io.BytesIO()
    _csv_write(output, rows, fields)
    return output.getvalue()


class _FileWriter:
    def __init__(self, output, account=None):
        self.output, self.account = output, account
        self.digest, self.size = hashlib.sha256(), 0

    def write(self, value):
        self.size += len(value)
        require(self.size<=MAX_BYTES, 'La exportación supera 8 GiB. No se ha truncado ningún dato.')
        if self.account:
            self.account(len(value))
        self.digest.update(value)
        return self.output.write(value)


def _lines(documents):
    output = []
    for document in documents:
        payload = json.loads(document['payload']) if isinstance(document['payload'], str) else document['payload']
        for position, line in enumerate(payload.get('lines', [])):
            output.append({**{key: line.get(key) for key in LINE_FIELDS}, 'document_id': document['id'],
                           'kind': document['kind'], 'status': document['status'], 'number': document['full_number'],
                           'issue_date': document['issue_date'], 'customer_id': document['customer_id'],
                           'vehicle_id': document['vehicle_id'], 'customer_name': (payload.get('customer') or {}).get('name'),
                           'plate': (payload.get('vehicle') or {}).get('plate'), 'position': line.get('position', position),
                           'original_line_json': dumps(line)})
    return output


class Reporting:
    def __init__(self, db, settings, backups=None):
        self.db, self.settings = db, settings
        self.backups = backups or Backups(db, settings)

    def summary(self, start='', end=''):
        first, last = _range(start, end)
        with self.db.read() as conn:
            conn.execute('BEGIN')
            clause = "d.kind='invoice' AND d.status IN ('issued','historical') AND d.issue_date BETWEEN ? AND ?"
            totals = dict(conn.execute('SELECT count(*) AS count,coalesce(sum(base_cents),0) AS base_cents,'
                    'coalesce(sum(tax_cents),0) AS tax_cents,coalesce(sum(total_cents),0) AS total_cents,'
                    "sum(CASE WHEN reference_id IS NOT NULL THEN 1 ELSE 0 END) AS rectifications,"
                    "sum(CASE WHEN status='historical' THEN 1 ELSE 0 END) AS historical_count,"
                    "sum(CASE WHEN json_extract(payload,'$.test_document')=1 THEN 1 ELSE 0 END) AS test_count "
                    'FROM documents d WHERE ' + clause, (first, last)).fetchone())
            totals = {key: value or 0 for key, value in totals.items()}
            months = [dict(row) for row in conn.execute('SELECT substr(issue_date,1,7) AS month,count(*) AS count,'
                    'sum(base_cents) AS base_cents,sum(tax_cents) AS tax_cents,sum(total_cents) AS total_cents '
                    'FROM documents d WHERE ' + clause + ' GROUP BY month ORDER BY month DESC', (first, last))]
            cash = [dict(row) for row in conn.execute('SELECT substr(p.paid_on,1,7) AS month,p.method,count(*) AS count,'
                    'sum(CASE WHEN p.amount_cents>0 THEN p.amount_cents ELSE 0 END) AS received_cents,'
                    'sum(CASE WHEN p.amount_cents<0 THEN -p.amount_cents ELSE 0 END) AS returned_cents,'
                    'sum(p.amount_cents) AS net_cents,sum(CASE WHEN p.reversal_of IS NOT NULL THEN 1 ELSE 0 END) AS reversals '
                    'FROM payments p JOIN documents d ON d.id=p.document_id WHERE p.paid_on BETWEEN ? AND ? '
                    "AND d.status!='import_reverted' AND p.method IN (" + ','.join('?' for _ in METHODS) +
                    ') GROUP BY month,p.method ORDER BY month DESC,p.method', (first, last, *METHODS))]
            collected = {key: sum(row[key] for row in cash) for key in ('count', 'received_cents', 'returned_cents', 'net_cents', 'reversals')}
            adjustments = dict(conn.execute("SELECT count(*) AS count,coalesce(sum(p.amount_cents),0) AS amount_cents "
                    "FROM payments p JOIN documents d ON d.id=p.document_id WHERE p.method='opening_adjustment' "
                    "AND d.status!='import_reverted' AND p.paid_on BETWEEN ? AND ?", (first, last)).fetchone())
            opening = dict(conn.execute('SELECT count(*) AS count,coalesce(sum(b.paid_cents),0) AS paid_cents '
                    "FROM document_payment_baselines b JOIN documents d ON d.id=b.document_id WHERE d.status='historical' "
                    'AND d.issue_date BETWEEN ? AND ?', (first, last)).fetchone())
            debts = dict(conn.execute('SELECT count(*) AS documents,'
                    'coalesce(sum(CASE WHEN balance>0 THEN balance ELSE 0 END),0) AS receivable_cents,'
                    'coalesce(sum(CASE WHEN balance<0 THEN -balance ELSE 0 END),0) AS refund_due_cents,'
                    "coalesce(sum(CASE WHEN balance>0 AND due_date!='' AND due_date<? THEN balance ELSE 0 END),0) AS overdue_cents "
                    'FROM (SELECT d.total_cents-' + PAID_SQL + ' AS balance,d.due_date FROM documents d WHERE ' + clause +
                    ' AND ' + PAYMENT_KNOWN_SQL + ')', (today(), first, last)).fetchone())
            unknown = conn.execute('SELECT count(*) FROM documents d WHERE ' + clause + ' AND NOT ' + PAYMENT_KNOWN_SQL,
                                   (first, last)).fetchone()[0]
            work = [dict(row) for row in conn.execute("SELECT kind,status,count(*) AS count,coalesce(sum(total_cents),0) AS total_cents "
                    "FROM documents WHERE kind IN ('quote','order') AND issue_date BETWEEN ? AND ? GROUP BY kind,status ORDER BY kind,status",
                    (first, last))]
            products = [dict(row) for row in conn.execute('SELECT p.*,s.name AS supplier_name,s.phone AS supplier_phone FROM products p '
                    'LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE p.archived=0 AND p.track_stock=1 ORDER BY p.name')]
            low = [{**row, 'units_to_minimum': str(max(Decimal(row['min_stock']) - Decimal(row['stock']), Decimal(0)))}
                   for row in products if Decimal(row['stock']) <= Decimal(row['min_stock'])]
            dashboard = {'customers': conn.execute('SELECT count(*) FROM customers WHERE archived=0').fetchone()[0],
                         'active_orders': conn.execute("SELECT count(*) FROM documents WHERE kind='order' AND status NOT IN ('draft','delivered')").fetchone()[0],
                         'pending_cents': debts['receivable_cents'], 'refund_due_cents': debts['refund_due_cents'],
                         'unknown_payment_documents': unknown, 'low_stock': len(low)}
        return {'period': {'start': start, 'end': end}, 'as_of': today(), 'months': months, 'billing': totals,
                'cash': collected, 'cash_months': cash, 'opening_adjustments': adjustments, 'opening_balances': opening,
                'receivables': {**debts, 'unknown_documents': unknown}, 'work': work, 'low_stock': low, 'dashboard': dashboard,
                'notice': 'Resumen operativo, no contabilidad ni declaración tributaria. Los documentos de prueba se identifican. '
                          'Cobros por fecha de pago; saldos y trabajos muestran el estado actual de los documentos del período. '
                          'Los mínimos corresponden a las existencias actuales.'}

    @staticmethod
    def _columns(conn, table):
        return [dict(row) for row in conn.execute('PRAGMA table_info("' + table + '")')]

    def _make_export(self, writer, name, mime):
        with tempfile.TemporaryDirectory(prefix='.portable-work-', dir=self.db.root) as temporary:
            private_directory(temporary)
            path = Path(temporary)/name
            with path.open('xb') as output:
                os.chmod(path, 0o600)
                writer(_FileWriter(output))
                output.flush()
                os.fsync(output.fileno())
            return self.backups.register_export(path, name, mime)

    def export(self, kind='customers', start='', end=''):
        if kind == 'portable':
            return self.portable()
        first, last = _range(start, end)
        require(kind in CSV_TABLES or kind in ('document_lines', 'billing', 'cash', 'low_stock', 'work'), 'Exportación no admitida.')
        name = kind+'-'+today()+'.csv'
        if kind in ('billing', 'cash', 'low_stock', 'work'):
            data = self.summary(start, end)
            key = {'billing':'months', 'cash':'cash_months'}.get(kind, kind)
            rows = data[key]
            defaults = {'billing':['month','count','base_cents','tax_cents','total_cents'],
                        'cash':['month','method','count','received_cents','returned_cents','net_cents','reversals'],
                        'low_stock':['id','sku','name','stock','min_stock','supplier_name','supplier_phone','units_to_minimum'],
                        'work':['kind','status','count','total_cents']}
            fields = list(rows[0]) if rows else defaults[kind]
            return self._make_export(lambda output:_csv_write(output, rows, fields), name, 'text/csv')
        with self.db.lock, self.db.read() as conn:
            conn.execute('BEGIN')
            if kind == 'document_lines':
                documents = conn.execute('SELECT * FROM documents WHERE issue_date BETWEEN ? AND ? ORDER BY issue_date,id', (first, last))
                rows = (line for row in documents for line in _lines([dict(row)]))
                fields = LINE_FIELDS
            else:
                table = CSV_TABLES[kind]
                condition, params = '', ()
                if kind == 'invoices':
                    condition, params = " WHERE kind='invoice' AND issue_date BETWEEN ? AND ?", (first, last)
                elif kind == 'payments':
                    condition, params = ' WHERE paid_on BETWEEN ? AND ?', (first, last)
                rows = (dict(row) for row in conn.execute('SELECT * FROM '+table+condition+' ORDER BY rowid', params))
                fields = [column['name'] for column in self._columns(conn, table) if column['name']!='search_text']
            return self._make_export(lambda output:_csv_write(output, rows, fields), name, 'text/csv')

    def portable(self):
        with self.db.lock, self.db.read() as conn, tempfile.TemporaryDirectory(prefix='.portable-work-', dir=self.db.root) as temporary:
            private_directory(temporary)
            conn.execute('BEGIN')
            present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            require(present<=set(EXPORT_TABLES)|{'settings'}, 'Hay una tabla nueva que aún no está descrita en el formato portable. No se ha omitido.')
            tables = [table for table in EXPORT_TABLES if table in present]
            schema = {table:{'columns':self._columns(conn, table),
                      'foreign_keys':[dict(row) for row in conn.execute('PRAGMA foreign_key_list("'+table+'")')]} for table in tables}
            config = self.settings.get(conn)
            allowed_fiscal = ('mode','producer_name','producer_tax_id','system_id','installation_id','declaration_text')
            public_settings = {key:config[key] for key in ('company','billing','appearance','agenda')}
            public_settings['fiscal'] = {key:config['fiscal'].get(key) for key in allowed_fiscal}
            metadata = {'format':'canamo-portable-v1','created_at':now(),'application_version':__version__,
                        'schema_version':SCHEMA_VERSION,'settings':public_settings}
            files, counts, canonical, skipped = {}, {}, set(), []
            total = 0
            name = 'exportacion-portable-'+today()+'.zip'
            path = Path(temporary)/name
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                os.chmod(path, 0o600)
                def account(size):
                    nonlocal total
                    total += size
                    require(total<=MAX_BYTES, 'La exportación portable supera 8 GiB descomprimidos. No se ha omitido ningún dato.')
                def add(filename, writer):
                    key = unicodedata.normalize('NFC', filename).casefold()
                    require(key not in canonical and len(files)+1<MAX_FILES, 'La exportación supera 50.000 archivos o contiene nombres repetidos para Windows.')
                    canonical.add(key)
                    with archive.open(filename, 'w', force_zip64=True) as member:
                        output = _FileWriter(member, account)
                        writer(output)
                    files[filename] = {'sha256':output.digest.hexdigest(),'bytes':output.size}
                encoder = json.JSONEncoder(ensure_ascii=False, separators=(',', ':'), sort_keys=True, default=_json)
                def write_json(output, value):
                    for part in encoder.iterencode(value):
                        output.write(part.encode('utf-8'))
                def write_data(output):
                    output.write(b'{')
                    for key, value in metadata.items():
                        output.write(json_bytes(key)+b':')
                        write_json(output, value)
                        output.write(b',')
                    output.write(b'"tables":{')
                    for index, table in enumerate(tables):
                        if index:
                            output.write(b',')
                        output.write(json_bytes(table)+b':[')
                        count = 0
                        for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid'):
                            if count:
                                output.write(b',')
                            write_json(output, dict(row))
                            count += 1
                        counts[table] = count
                        output.write(b']')
                    output.write(b'}}')
                add('data.json', write_data)
                add('schema.json', lambda output:write_json(output, schema))
                for table in tables:
                    fields = [column['name'] for column in schema[table]['columns'] if column['name'] not in ('search_text','content')]
                    rows = (dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid'))
                    add('csv/'+table+'.csv', lambda output:_csv_write(output, rows, fields))
                rows = (line for row in conn.execute('SELECT * FROM documents ORDER BY rowid') for line in _lines([dict(row)]))
                add('csv/document_lines.csv', lambda output:_csv_write(output, rows, LINE_FIELDS))
                for folder in ('assets','pdfs','imports'):
                    directory = self.db.root/folder
                    require(not directory.is_symlink(), 'Una carpeta de recursos es un enlace. No se ha exportado.')
                    if not directory.exists():
                        continue
                    for resource in directory.rglob('*'):
                        require(not resource.is_symlink(), 'No se exportan enlaces dentro de los recursos.')
                        if resource.is_dir():
                            continue
                        require(resource.is_file(), 'Hay un recurso que no es un archivo regular.')
                        relative = resource.relative_to(self.db.root).as_posix()
                        _valid_name(relative)
                        if folder=='imports' and resource.name.startswith('simulation.'):
                            skipped.append(relative)
                            continue
                        before = resource.stat()
                        require(before.st_size+total<=MAX_BYTES, 'Los recursos superan 8 GiB; no se ha truncado la exportación.')
                        def copy_resource(output):
                            with resource.open('rb') as source:
                                while chunk := source.read(CHUNK_BYTES):
                                    output.write(chunk)
                            after = resource.stat()
                            require(output.size==before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns,
                                    'Un recurso cambió durante la exportación. Vuelve a intentarlo.')
                        add('resources/'+relative, copy_resource)
                logos = {config['billing'].get('logo_id')}
                for row in conn.execute('SELECT payload FROM documents'):
                    logos.add(json.loads(row['payload']).get('branding', {}).get('logo_id'))
                require(all('resources/assets/'+logo in files for logo in logos if logo), 'Falta una imagen referenciada; la exportación no está completa.')
                if 'import_batches' in tables:
                    for batch in conn.execute('SELECT id,source_digest FROM import_batches'):
                        prefix = 'resources/imports/'+batch['id']+'/'
                        require(all(prefix+filename in files for filename in ('source.bin','upload.json','diagnostic.json','staging.sqlite')),
                                'Faltan originales o diagnósticos de una importación; no se ha exportado.')
                        require(files[prefix+'source.bin']['sha256']==batch['source_digest'], 'La huella del original importado no coincide.')
                add('LEEME.txt', lambda output:output.write(PORTABLE_README.encode('utf-8')))
                manifest = {'format':'canamo-portable-v1','export_id':uid(),'created_at':metadata['created_at'],
                            'schema_version':SCHEMA_VERSION,'counts':counts,
                            'excluded':['secure/','backups/','operational SQLite','private configuration',*skipped],
                            'files':files}
                encoded = json_bytes(manifest)
                require(len(encoded)<=16*1024**2, 'El manifiesto portable supera 16 MiB.')
                account(len(encoded))
                archive.writestr('manifest.json', encoded)
            result = self.backups.register_export(path, name, 'application/zip')
        try:
            with self.db.transaction() as audit:
                self.db.audit(audit, 'data.export_portable', manifest['export_id'], {'sha256':result['sha256'],'counts':counts})
        except Exception:
            self.backups.release_download(result['capability'])
            raise
        return result


PORTABLE_README = """EXPORTACIÓN PORTABLE DE EL CÁÑAMO — formato canamo-portable-v1

Este ZIP permite consultar o trasladar datos a otros programas. No es una copia
operativa restaurable: no autoriza emitir, retomar colas fiscales ni trasladar el PC.
Para recuperar el programa utiliza Copias y traslado, con activación exclusiva.

El archivo no está cifrado y contiene datos del taller. Guárdalo bajo tu control.
No contiene certificados, claves, secure/, contraseñas, motores de asistencia ni
rutas privadas de configuración. No se envía a servicios externos.

data.json conserva todas las filas, identificadores, snapshots y payloads originales,
incluidas históricas revertidas, auditoría, series, fiscalidad, cobros y ajustes.
Las columnas JSON de SQLite siguen como cadenas originales. Los BLOB se representan
como {$binary:{encoding:"base64",sha256:...,data:...}} para recuperar sus bytes exactos.
schema.json describe columnas, claves primarias y relaciones. Los importes *_cents
son céntimos enteros; cantidades y precios decimales permanecen como texto exacto.
JSON distingue cero, null y texto vacío.

csv/ contiene vistas UTF-8 con BOM, separador punto y coma y cabeceras aunque no haya
filas. Las cadenas que podrían ejecutar fórmulas o perder ceros iniciales llevan
un apóstrofo de protección: sus valores originales están en data.json.
La vista document_lines.csv permite consultar las líneas con su original completo.

resources/ conserva logos, PDF existentes y originales y diagnósticos de importación.
No se genera un PDF que no estuviera guardado. staging.sqlite conserva campos no
mapeados. Las simulaciones desechables se excluyen. El manifiesto tiene conteos y
SHA-256 de cada archivo; verifica esas huellas antes de utilizar el conjunto.

El ZIP y sus recursos se escriben por bloques; JSON y CSV se recorren por filas.
Límites explícitos: 8 GiB descomprimidos, 50.000 archivos y manifiesto de 16 MiB.
Ningún resultado operativo sustituye la contabilidad ni una declaración tributaria.
"""
