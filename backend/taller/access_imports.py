"""Coordinator for the Access wizard. All paths remain under the user's data directory."""
import base64
import csv
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import zipfile

from .access import CHUNK_BYTES, MAX_FILE_BYTES, Staging, decode_chunk, digest_file, extract_access, json_write, jsonl_rows
from .access_mapping import CUSTOMER_FIELDS, VEHICLE_FIELDS, ENTITIES, canonical_historical, fingerprint, map_tables, source_key, suggested_profile
from .access_writer import AccessWriter
from .db import uid, dumps
from .errors import AppError, require
from .validation import plate, now

PAGE_SIZE = 50
MAX_STEP = 500


class Imports(AccessWriter):
    def __init__(self, db, contacts, backups):
        self.db, self.contacts, self.backups = db, contacts, backups
        self.root = db.root / 'imports'
        self.root.mkdir(exist_ok=True)

    def _folder(self, identifier):
        require(isinstance(identifier, str) and re.fullmatch(r'[a-f0-9-]{36}', identifier), 'Identificador de importación no válido.')
        return self.root / identifier

    def sources(self):
        with self.db.read() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM import_sources ORDER BY created_at')]

    def source_save(self, name, identifier=None):
        require(isinstance(name, str) and 1 <= len(name.strip()) <= 200, 'Da un nombre al origen, por ejemplo Access del taller.')
        identifier = identifier or uid(); self._folder(identifier)
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO import_sources VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name', (identifier, name.strip(), now()))
        return {'id': identifier, 'name': name.strip()}

    def profiles(self):
        with self.db.read() as conn:
            return [{**dict(row), 'profile': json.loads(row['profile'])} for row in conn.execute('SELECT * FROM import_profiles ORDER BY name')]

    def profile_save(self, name, profile, identifier=None):
        require(isinstance(name, str) and 1 <= len(name.strip()) <= 200 and isinstance(profile, dict) and profile.get('version') == 1, 'Nombre o perfil no válido.')
        require(len(dumps(profile)) < 1_000_000, 'El perfil es demasiado grande.')
        identifier = identifier or uid(); self._folder(identifier)
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO import_profiles VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,profile=excluded.profile,updated_at=excluded.updated_at', (identifier, name.strip(), dumps(profile), now()))
        return {'id': identifier, 'name': name.strip()}

    def upload_start(self, name, size, source_id):
        require(isinstance(name, str) and Path(name).name == name and len(name) <= 240, 'Nombre de copia no válido.')
        require(Path(name).suffix.lower() in ('.mdb', '.accdb', '.csv', '.json', '.zip'), 'Selecciona MDB, ACCDB, CSV, JSON o paquete ZIP intermedio.')
        require(isinstance(size, int) and not isinstance(size, bool) and 0 < size <= MAX_FILE_BYTES, 'La copia debe ocupar entre 1 byte y 2 GiB.')
        with self.db.read() as conn:
            require(conn.execute('SELECT 1 FROM import_sources WHERE id=?', (source_id,)).fetchone(), 'Selecciona el mismo origen para todas las copias de este Access.')
        identifier = uid(); folder = self._folder(identifier); folder.mkdir()
        json_write(folder / 'upload.json', {'name': name, 'size': size, 'source_id': source_id, 'suffix': Path(name).suffix.lower()})
        (folder / 'source.bin').touch()
        return {'upload_id': identifier, 'chunk_bytes': CHUNK_BYTES, 'received': 0}

    def upload_status(self, upload_id):
        folder = self._folder(upload_id)
        require((folder / 'upload.json').is_file(), 'No se encuentra la carga.', 'not_found')
        meta = json.loads((folder / 'upload.json').read_text(encoding='utf-8'))
        return {**meta, 'upload_id': upload_id, 'received': (folder / 'source.bin').stat().st_size, 'chunk_bytes': CHUNK_BYTES}

    def upload_chunk(self, upload_id, offset, content):
        chunk = decode_chunk(content)
        with self.db.lock:
            meta = self.upload_status(upload_id)
            require(isinstance(offset, int) and not isinstance(offset, bool) and 0 <= offset <= meta['received'] and offset + len(chunk) <= meta['size'], 'Posición de fragmento no válida. Consulta el progreso antes de repetir.', 'conflict')
            with (self._folder(upload_id) / 'source.bin').open('r+b') as target:
                target.seek(offset)
                if offset < meta['received']:
                    require(target.read(len(chunk)) == chunk, 'Este fragmento no coincide con la copia ya recibida.', 'conflict')
                else:
                    target.write(chunk); target.flush(); os.fsync(target.fileno())
        return self.upload_status(upload_id)

    def _batch(self, identifier, conn=None):
        if conn is None:
            with self.db.read() as current:
                return self._batch(identifier, current)
        row = conn.execute('SELECT * FROM import_batches WHERE id=?', (identifier,)).fetchone()
        require(row, 'No se encuentra el lote.', 'not_found')
        return {**dict(row), 'profile': json.loads(row['profile']), 'summary': json.loads(row['summary'])}

    def capacity(self, batch_id=None):
        from .backups import MAX_BYTES, MAX_FILES
        with self.db.read() as conn:
            database_bytes = conn.execute('PRAGMA page_count').fetchone()[0] * conn.execute('PRAGMA page_size').fetchone()[0]
        projected = False
        if batch_id:
            simulated = self._batch(batch_id)['summary'].get('simulation', {}).get('database_bytes', 0)
            if simulated > database_bytes:
                database_bytes = simulated; projected = True
        size, count = database_bytes, 1
        for folder in ('assets', 'pdfs', 'imports'):
            directory = self.db.root / folder
            if not directory.exists(): continue
            for path in directory.rglob('*'):
                require(not path.is_symlink(), 'Hay un enlace en los recursos locales. Revisa la carpeta de datos.')
                if path.is_file() and not (folder == 'imports' and path.name.startswith('simulation.')):
                    size += path.stat().st_size; count += 1
        return {'used_bytes': size, 'limit_bytes': MAX_BYTES, 'files': count, 'file_limit': MAX_FILES,
                'within_limit': size <= MAX_BYTES and count < MAX_FILES, 'projected_after_import': projected}

    def discard(self, upload_id, reason):
        require(isinstance(reason, str) and reason.strip(), 'Indica por qué descartas este ensayo.')
        folder = self._folder(upload_id)
        with self.db.lock:
            require(folder.is_dir() and not folder.is_symlink(), 'No se encuentra la carga local.', 'not_found')
            with self.db.transaction() as conn:
                batch = conn.execute('SELECT * FROM import_batches WHERE id=?', (upload_id,)).fetchone()
                require(not batch or batch['cursor'] == 0 and batch['status'] in ('diagnosed', 'previewed', 'simulated'), 'Este lote tiene cambios aplicados; usa Revertir. Su evidencia se conserva.')
                require(not conn.execute('SELECT 1 FROM import_changes WHERE batch_id=?', (upload_id,)).fetchone(), 'El lote ya tiene cambios aplicados.')
                self.db.audit(conn, 'import.discard', upload_id, {'reason': reason.strip(), 'source_digest': batch['source_digest'] if batch else None})
                conn.execute('DELETE FROM import_batches WHERE id=?', (upload_id,))
            shutil.rmtree(folder)
        return {'discarded': True, 'external_original_untouched': True}

    def batches(self, source_id=None, page=0):
        page = max(0, int(page))
        with self.db.read() as conn:
            condition, parameters = (' WHERE source_id=?', (source_id,)) if source_id else ('', ())
            total = conn.execute('SELECT count(*) FROM import_batches' + condition, parameters).fetchone()[0]
            rows = conn.execute('SELECT * FROM import_batches' + condition + ' ORDER BY created_at DESC LIMIT 50 OFFSET ?', (*parameters, page * 50))
            return {'items': [{**dict(row), 'summary': json.loads(row['summary']), 'profile': json.loads(row['profile'])} for row in rows], 'total': total, 'page': page}

    def diagnose(self, upload_id, encoding='utf-8-sig', delimiter='auto'):
        require(encoding in ('utf-8-sig', 'cp1252', 'utf-16'), 'Codificación CSV no admitida.')
        require(delimiter in ('auto', ';', ',', '\t'), 'Separador CSV no admitido.')
        with self.db.lock:
            meta = self.upload_status(upload_id)
            require(meta['received'] == meta['size'], 'La carga está incompleta; reanúdala antes del diagnóstico.')
            folder = self._folder(upload_id); source = folder / 'source.bin'; stage = Staging(folder)
            with self.db.read() as conn:
                if conn.execute('SELECT 1 FROM import_batches WHERE id=?', (upload_id,)).fetchone():
                    return self.review(upload_id)
            if meta['suffix'] in ('.mdb', '.accdb'):
                extracted = folder / 'extracted'
                if extracted.exists(): shutil.rmtree(extracted)
                manifest = extract_access(source, extracted); stage.load_extracted(manifest, extracted)
                profile = suggested_profile(manifest)
            elif meta['suffix'] == '.csv':
                manifest = self._csv(source, stage, encoding, delimiter); profile = suggested_profile(manifest)
            elif meta['suffix'] == '.zip':
                manifest = self._package(source, stage); profile = suggested_profile(manifest)
            else:
                require(meta['size'] <= 64 * 1024 * 1024, 'Los paquetes JSON admiten 64 MiB; usa ZIP de tablas JSONL para archivos mayores.')
                try: bundle = json.loads(source.read_text(encoding='utf-8-sig'))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise AppError('Paquete JSON no válido.') from exc
                require(isinstance(bundle, dict) and bundle.get('format') in ('canamo-import-v1', 'canamo-import-v2'), 'Formato JSON no reconocido; usa la plantilla del importador.')
                self._canonical(stage, bundle)
                manifest = {'format': bundle['format'], 'tables': [], 'records': {entity: len(bundle.get(entity, [])) for entity in ENTITIES}, 'engine': 'Paquete de migración explícito', 'original_preserved': True}
                profile = {'version': 1, 'canonical': True}
            manifest.update({'source_sha256': digest_file(source), 'name': meta['name'], 'source_bytes': meta['size']})
            json_write(folder / 'diagnostic.json', manifest)
            with self.db.transaction() as conn:
                conn.execute('INSERT INTO import_batches(id,source_id,source_digest,status,profile,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (upload_id, meta['source_id'], manifest['source_sha256'], 'diagnosed', dumps(profile), now(), now()))
            return self.map(upload_id, profile) if profile.get('canonical') else self.review(upload_id)

    def _csv(self, source, stage, encoding, delimiter):
        try:
            with source.open(encoding=encoding, newline='') as stream:
                sample = stream.read(65536); stream.seek(0)
                if delimiter == 'auto':
                    try: dialect = csv.Sniffer().sniff(sample, delimiters=';,\t')
                    except csv.Error: dialect = csv.excel
                    reader = csv.DictReader(stream, dialect=dialect)
                else: reader = csv.DictReader(stream, delimiter=delimiter)
                columns = reader.fieldnames or []
                require(columns and len(columns) == len(set(columns)) and all(columns), 'El CSV necesita cabeceras únicas y no vacías.')
                count = 0; conn = stage.connect()
                try:
                    conn.execute('DELETE FROM raw_rows')
                    for count, row in enumerate(reader, 1):
                        require(None not in row and all(value is not None for value in row.values()), f'CSV fila {count+1}: número de columnas incorrecto.')
                        conn.execute('INSERT INTO raw_rows VALUES(?,?,?)', ('csv', count, dumps(row)))
                    conn.commit()
                finally: conn.close()
        except UnicodeDecodeError as exc: raise AppError('No se puede leer el texto. Selecciona Windows-1252 o UTF-16 si corresponde.') from exc
        except csv.Error as exc: raise AppError('El CSV no está bien formado; revisa comillas y separadores.') from exc
        return {'format': 'csv', 'encoding': encoding, 'engine': 'CSV explícito', 'original_preserved': True, 'tables': [{'name': 'csv', 'linked': False, 'rows': count, 'columns': [{'name': name, 'type': 'TEXT'} for name in columns], 'primary_key': []}]}

    def _package(self, source, stage):
        # ZipFile loads the full central directory immediately. Bound its metadata
        # before constructing it, then apply this format's stricter local rules.
        from .backups import _preflight_zip
        _preflight_zip(source)
        try:
            with zipfile.ZipFile(source) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)) and 'manifest.json' in names and len(names) <= 10001, 'Paquete incompleto o con entradas duplicadas.')
                require(all(Path(name).name == name and '\\' not in name and not name.startswith('.') for name in names), 'El paquete contiene rutas no permitidas.')
                require(sum(item.file_size for item in archive.infolist()) <= 4 * MAX_FILE_BYTES, 'El paquete supera 8 GiB descomprimidos.')
                require(archive.getinfo('manifest.json').file_size <= 4_000_000, 'Manifiesto demasiado grande.')
                manifest = json.loads(archive.read('manifest.json'))
                require(manifest.get('format') == 'canamo-access-raw-v1', 'El ZIP no es un paquete de tablas Access.')
                conn = stage.connect()
                try:
                    conn.execute('DELETE FROM raw_rows')
                    for table in manifest['tables']:
                        if table.get('linked'): continue
                        filename = table['file']
                        require(filename in names and filename.startswith('table-') and filename.endswith('.jsonl'), 'Falta el archivo de una tabla.')
                        count = 0
                        with archive.open(filename) as stream:
                            for count, value in jsonl_rows(stream):
                                conn.execute('INSERT INTO raw_rows VALUES(?,?,?)', (table['name'], count, dumps(value)))
                        require(count == table['rows'], 'El paquete no concilia las filas declaradas.')
                    conn.commit()
                finally: conn.close()
                return {**manifest, 'engine': 'Paquete intermedio; lectura nativa no ejecutada aquí', 'original_preserved': True}
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc: raise AppError('Paquete intermedio dañado o incompleto.') from exc

    def _canonical(self, stage, bundle):
        require(all(isinstance(bundle.get(entity, []), list) for entity in ENTITIES), 'Clientes, vehículos y facturas deben ser listas.')
        conn = stage.connect()
        try:
            conn.execute('DELETE FROM records'); conn.execute('DELETE FROM incidents')
            conn.execute('DELETE FROM row_decisions')
            customers = bundle.get('customers', []); vehicles = list(bundle.get('vehicles', []))
            for customer in customers:
                require(isinstance(customer, dict), 'Cliente no válido.')
                if customer.get('plate'): vehicles.append({'legacy_customer_code': customer.get('legacy_code'), **{key: customer.get(key, '') for key in VEHICLE_FIELDS}})
            for entity, records in (('customers', customers), ('vehicles', vehicles), ('invoices', bundle.get('invoices', []))):
                for index, raw in enumerate(records):
                    key = 'row:' + str(index + 1)
                    try:
                        require(isinstance(raw, dict), 'Registro no válido.')
                        if entity == 'customers':
                            key = source_key(raw, ['legacy_code']); value = {key: str(raw.get(key, '') or '') for key in CUSTOMER_FIELDS}
                            require(value['name'].strip(), 'Falta el nombre del cliente.')
                        elif entity == 'vehicles':
                            key = source_key(raw, ['legacy_customer_code', 'plate']); value = {key: raw.get(key, '') for key in VEHICLE_FIELDS}
                            value['customer_key'] = source_key(raw, ['legacy_customer_code']); value['km'] = int(raw.get('km') or 0)
                            require(value['km'] >= 0 and 3 <= len(plate(value['plate'])) <= 15, 'Matrícula o kilómetros no válidos.')
                        else:
                            key = source_key(raw, ['legacy_key']); value = canonical_historical(raw, legacy_v1=bundle['format'] == 'canamo-import-v1')
                            value['customer_key'] = source_key(raw, ['legacy_customer_code'])
                        conn.execute('INSERT INTO records(entity,source_key,source_hash,payload,original) VALUES(?,?,?,?,?)', (entity, key, fingerprint(raw), dumps(value), dumps(raw)))
                    except (AppError, ValueError, TypeError) as exc:
                        conn.execute('INSERT INTO incidents(level,entity,source_key,message) VALUES(?,?,?,?)', ('error', entity, key, str(exc)))
                        conn.execute('INSERT INTO records(entity,source_key,source_hash,payload,original) VALUES(?,?,?,?,?)', (entity, key, fingerprint(raw), dumps({'invalid': True}), dumps(raw)))
            for duplicate in conn.execute('SELECT entity,source_key,count(*) AS n FROM records GROUP BY entity,source_key HAVING n>1'):
                conn.execute('INSERT INTO incidents(level,entity,source_key,message) VALUES(?,?,?,?)', ('error', duplicate['entity'], duplicate['source_key'], 'Clave de origen duplicada.'))
            conn.commit()
        finally: conn.close()

    def map(self, batch_id, profile, resolutions=None):
        with self.db.lock:
            batch = self._batch(batch_id)
            require(batch['cursor'] == 0 and batch['status'] not in ('running', 'completed', 'reverted'), 'El lote ya tiene cambios. Continúa o revierte antes de cambiar su mapeo.')
            folder = self._folder(batch_id); stage = Staging(folder)
            require(isinstance(profile, dict), 'Perfil no válido.')
            if profile.get('canonical'):
                self._canonical(stage, json.loads((folder / 'source.bin').read_text(encoding='utf-8-sig')))
            else: map_tables(stage, profile, json.loads((folder / 'diagnostic.json').read_text(encoding='utf-8')))
            resolutions = resolutions or {}; require(isinstance(resolutions, dict), 'Resoluciones no válidas.')
            self._classify(batch, stage, resolutions)
            for name in ('simulation.sqlite', 'simulation.json'): (folder / name).unlink(missing_ok=True)
            with self.db.transaction() as conn:
                conn.execute("UPDATE import_batches SET profile=?,status='previewed',summary=?,updated_at=? WHERE id=?", (dumps(profile), dumps({'resolutions': resolutions}), now(), batch_id))
            return self.review(batch_id)

    def review(self, batch_id, page=0, level='all'):
        batch = self._batch(batch_id); folder = self._folder(batch_id)
        require(level in ('all', 'error', 'warning'), 'Filtro de incidencias no válido.')
        page = max(0, int(page)); conn = Staging(folder).connect()
        try:
            counts = {entity: conn.execute('SELECT count(*) FROM records WHERE entity=?', (entity,)).fetchone()[0] for entity in ENTITIES}
            actions = {row['action']: row['n'] for row in conn.execute('SELECT action,count(*) AS n FROM records GROUP BY action')}
            incident_counts = {key: conn.execute('SELECT count(*) FROM incidents WHERE level=?', (key,)).fetchone()[0] for key in ('error', 'warning')}
            incident_groups = [dict(row) for row in conn.execute('SELECT level,entity,message,count(*) AS count FROM incidents GROUP BY level,entity,message ORDER BY level,count(*) DESC')]
            decisions = [dict(row) for row in conn.execute('SELECT entity,table_name,disposition,rule,count(*) AS count FROM row_decisions GROUP BY entity,table_name,disposition,rule ORDER BY entity,rule')]
            quarantine_groups = [dict(row) for row in conn.execute("SELECT entity,json_extract(payload,'$.quarantine_reason') AS reason,count(*) AS count FROM records WHERE action='quarantine' GROUP BY entity,reason ORDER BY entity,reason")]
            clause, params = ('', ()) if level == 'all' else (' WHERE level=?', (level,))
            incidents = [dict(row) for row in conn.execute('SELECT * FROM incidents' + clause + ' ORDER BY CASE level WHEN \'error\' THEN 0 ELSE 1 END,id LIMIT ? OFFSET ?', (*params, PAGE_SIZE, page * PAGE_SIZE))]
            samples = [{**dict(row), 'payload': json.loads(row['payload'])} for row in conn.execute('SELECT position,entity,source_key,payload,action FROM records ORDER BY position LIMIT 12')]
            return {'batch_id': batch_id, 'token': batch_id, 'status': batch['status'], 'source_id': batch['source_id'], 'cursor': batch['cursor'],
                    'diagnostic': json.loads((folder / 'diagnostic.json').read_text(encoding='utf-8')), 'profile': batch['profile'], 'summary': batch['summary'], 'counts': counts, 'actions': actions,
                    'incident_counts': incident_counts, 'incidents': incidents, 'page': page, 'page_size': PAGE_SIZE,
                    'incident_groups': incident_groups, 'row_decisions': decisions, 'quarantine_groups': quarantine_groups,
                    'errors': [row['message'] for row in incidents if row['level'] == 'error'], 'warnings': [row['message'] for row in incidents if row['level'] == 'warning'],
                    'sample': [row['payload'] for row in samples if row['entity'] == 'customers'], 'records': samples,
                    'capacity': self.capacity(batch_id),
                    'note': 'Las series nuevas y la cola fiscal no se modifican. El original y todas las incidencias se conservan.'}
        finally: conn.close()

    def records(self, batch_id, page=0, entity='all'):
        self._batch(batch_id); require(entity in (*ENTITIES, 'all'), 'Entidad no válida.')
        conn = Staging(self._folder(batch_id)).connect(); page = max(0, int(page))
        try:
            clause, args = ('', ()) if entity == 'all' else (' WHERE entity=?', (entity,))
            count = conn.execute('SELECT count(*) FROM records' + clause, args).fetchone()[0]
            rows = conn.execute('SELECT * FROM records' + clause + ' ORDER BY position LIMIT 50 OFFSET ?', (*args, page * 50))
            return {'items': [{**dict(row), 'payload': json.loads(row['payload']), 'original': json.loads(row['original']), 'resolution': json.loads(row['resolution'])} for row in rows], 'total': count, 'page': page}
        finally: conn.close()

    def raw_table(self, batch_id, table, page=0):
        self._batch(batch_id); conn = Staging(self._folder(batch_id)).connect(); page = max(0, int(page))
        try:
            count = conn.execute('SELECT count(*) FROM raw_rows WHERE table_name=?', (table,)).fetchone()[0]
            return {'items': [{'row_number': row['row_number'], 'data': json.loads(row['data'])} for row in conn.execute('SELECT row_number,data FROM raw_rows WHERE table_name=? ORDER BY row_number LIMIT 50 OFFSET ?', (table, page * 50))], 'total': count, 'page': page}
        finally: conn.close()

    def preview(self, text, format='csv', source_id=None):
        require(isinstance(text, str) and len(text.encode()) <= 64 * 1024 * 1024, 'Utiliza la carga por fragmentos para más de 64 MiB.')
        require(format in ('csv', 'json'), 'Selecciona CSV o paquete JSON.')
        if source_id is None:
            with self.db.read() as conn:
                source = conn.execute("SELECT id FROM import_sources WHERE name='Importación CSV/JSON' ORDER BY created_at LIMIT 1").fetchone()
            source_id = source['id'] if source else self.source_save('Importación CSV/JSON')['id']
        data = text.encode('utf-8'); upload = self.upload_start('importacion.' + format, len(data), source_id)
        for offset in range(0, len(data), CHUNK_BYTES): self.upload_chunk(upload['upload_id'], offset, base64.b64encode(data[offset:offset + CHUNK_BYTES]).decode())
        result = self.diagnose(upload['upload_id'])
        if result['status'] == 'diagnosed': result = self.map(result['batch_id'], result['profile'])
        result['already_imported'] = bool(result['actions'].get('unchanged') and not any(result['actions'].get(action) for action in ('insert', 'replace', 'link')) and not result['incident_counts']['error'])
        return result

    def execute(self, token):
        review = self.review(token)
        require(not review['incident_counts']['error'], 'Corrige los errores de la vista previa antes de importar.')
        if self._batch(token)['status'] in ('previewed', 'simulated'):
            while not self.simulate(token, MAX_STEP, acknowledge_warnings=True)['done']: pass
        while True:
            result = self.run(token, MAX_STEP)
            if result['done']: return result['summary']['counts']
