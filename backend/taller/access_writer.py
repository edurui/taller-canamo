"""Import transactions, idempotency and reversal without restoring over later work."""
import base64
import json
import os
import sqlite3

from .access import CHUNK_BYTES, Staging, json_write
from .access_mapping import CUSTOMER_FIELDS, VEHICLE_FIELDS, ENTITIES, fingerprint
from .db import uid, dumps
from .errors import AppError, require
from .validation import normalized, plate, now

TABLES = {'customers': 'customers', 'vehicles': 'vehicles', 'invoices': 'documents'}


class AccessWriter:
    def _classify(self, batch, stage, resolutions):
        conn = stage.connect()
        try:
            def incident(level, entity, key, message):
                conn.execute('INSERT INTO incidents(level,entity,source_key,message) VALUES(?,?,?,?)', (level, entity, key, message))
            # Normalized plates are indexed once. Comparing every pair would be quadratic on real lots.
            conn.execute('DROP TABLE IF EXISTS plate_keys')
            conn.execute('CREATE TEMP TABLE plate_keys(source_key TEXT,plate TEXT)')
            conn.execute('CREATE INDEX plate_value ON plate_keys(plate)')
            for row in conn.execute("SELECT source_key,payload FROM records WHERE entity='vehicles'"):
                value = json.loads(row['payload'])
                if not value.get('invalid'): conn.execute('INSERT INTO plate_keys VALUES(?,?)', (row['source_key'], plate(value['plate'])))
            with self.db.read() as target:
                for record in conn.execute('SELECT * FROM records ORDER BY position'):
                    entity, key = record['entity'], record['source_key']; value = json.loads(record['payload'])
                    resolution = resolutions.get(entity + ':' + key, {})
                    require(isinstance(resolution, dict), 'Resolución no válida.')
                    action = 'insert'
                    old = target.execute('SELECT * FROM import_records WHERE source_id=? AND entity=? AND source_key=? AND active=1', (batch['source_id'], entity, key)).fetchone()
                    if resolution.get('skip'):
                        require(str(resolution.get('reason', '')).strip(), 'Indica por qué se excluye el registro.')
                        action = 'skip'
                        conn.execute('DELETE FROM incidents WHERE entity=? AND source_key=?', (entity, key))
                        incident('warning', entity, key, 'Excluido explícitamente: ' + str(resolution['reason']))
                    elif value.get('invalid'):
                        continue
                    elif old and old['source_hash'] == record['source_hash']:
                        action = 'unchanged'
                    elif old:
                        action = 'replace'
                        if not resolution.get('replace') or not str(resolution.get('reason', '')).strip():
                            incident('error', entity, key, 'El origen ha cambiado. Confirma la sustitución documentada o excluye este registro.')
                        elif json.loads(old['imported_state']) != self._state(target, entity, old['target_id']):
                            incident('error', entity, key, 'Hay actividad posterior en destino; no se sobrescribirá. Revisa la ficha y conserva ambas evidencias.')
                    elif resolution.get('link'):
                        require(entity in ('customers', 'vehicles') and str(resolution.get('reason', '')).strip(), 'Solo se vinculan fichas con una razón documentada.')
                        require(target.execute('SELECT 1 FROM ' + TABLES[entity] + ' WHERE id=? AND archived=0', (resolution['link'],)).fetchone(), 'La ficha seleccionada no existe o está archivada.')
                        action = 'link'
                    if action in ('insert', 'replace'):
                        if entity == 'customers':
                            conflict = target.execute('SELECT id FROM customers WHERE legacy_code=?', (value['legacy_code'],)).fetchone()
                            if conflict and (not old or conflict['id'] != old['target_id']):
                                incident('error', entity, key, 'El código ya existe en otra ficha/origen. Vincula explícitamente o excluye; no se fusiona por nombre/NIF.')
                            duplicate = conn.execute("SELECT source_key FROM records WHERE entity='customers' AND json_extract(payload,'$.legacy_code')=? AND source_key!=?", (value['legacy_code'], key)).fetchone()
                            if duplicate: incident('error', entity, key, 'Varios clientes tienen el mismo código. Resuelve la identidad antes de importar.')
                            if value.get('tax_id'):
                                matches = target.execute('SELECT id FROM customers WHERE tax_id=? AND archived=0', (plate(value['tax_id']),)).fetchall()
                                if any(not old or item['id'] != old['target_id'] for item in matches): incident('warning', entity, key, 'Hay otra ficha con este NIF. Se conserva separada salvo vinculación explícita.')
                        elif entity == 'vehicles':
                            conflict = target.execute('SELECT id FROM vehicles WHERE plate_normalized=?', (plate(value['plate']),)).fetchone()
                            if conflict and (not old or conflict['id'] != old['target_id']): incident('error', entity, key, 'Matrícula ya registrada. Revisa titularidad y vincula explícitamente; no se transfiere automáticamente.')
                            if conn.execute('SELECT 1 FROM plate_keys WHERE plate=? AND source_key!=?', (plate(value['plate']), key)).fetchone(): incident('error', entity, key, 'Matrícula compartida por varias filas; resuelve la titularidad.')
                        if entity != 'customers':
                            customer = conn.execute("SELECT position FROM records WHERE entity='customers' AND source_key=? AND action!='skip'", (value['customer_key'],)).fetchone()
                            existing = target.execute("SELECT target_id FROM import_records WHERE source_id=? AND entity='customers' AND source_key=? AND active=1", (batch['source_id'], value['customer_key'])).fetchone()
                            if not customer and not existing: incident('error', entity, key, 'Cliente de origen no encontrado; mapea su clave o vincula una ficha explícitamente.')
                        if entity == 'invoices':
                            if any(line['quantity'] is None or line['unit_price'] is None for line in value['lines']): incident('warning', entity, key, 'Cantidad o precio no conservados en alguna línea; se mostrará No consta y se mantendrá su importe original.')
                            if any(value['amount_differences'].values()) and not resolution.get('accept_difference'): incident('error', entity, key, 'Los importes históricos presentan diferencias. Acepta conservarlas con una explicación; nunca se corrigen automáticamente.')
                            if resolution.get('accept_difference'):
                                require(str(resolution.get('reason', '')).strip(), 'Documenta la razón para conservar la discrepancia histórica.')
                                incident('warning', entity, key, 'Diferencia histórica conservada: ' + str(resolution['reason']))
                            for part, certainty in value['snapshot_certainty'].items():
                                if certainty == 'unknown': incident('warning', entity, key, 'Datos originales de ' + {'customer':'receptor','issuer':'emisor','vehicle':'vehículo'}[part] + ' desconocidos; no se copiará la ficha actual.')
                            if value['payment_state'] == 'unknown': incident('warning', entity, key, 'Cobro no documentado: no se convierte en deuda pendiente.')
                            if value.get('legacy_v1_derived'): incident('warning', entity, key, 'Paquete v1: desglose reconstruido según su contrato antiguo; conserva el original y contrasta totales.')
                    conn.execute('UPDATE records SET action=?,resolution=? WHERE position=?', (action, dumps(resolution), record['position']))
                mapped_entities = {row['entity'] for row in conn.execute('SELECT DISTINCT entity FROM records')}
                for old in target.execute('SELECT entity,source_key FROM import_records WHERE source_id=? AND active=1', (batch['source_id'],)):
                    if old['entity'] in mapped_entities and not conn.execute('SELECT 1 FROM records WHERE entity=? AND source_key=?', (old['entity'], old['source_key'])).fetchone():
                        incident('warning', old['entity'], old['source_key'], 'Este registro importado anteriormente no aparece en la copia actual. Se conserva en destino; no se elimina por omisión.')
            conn.commit()
        finally: conn.close()

    def _state(self, conn, entity, identifier):
        row = conn.execute('SELECT * FROM ' + TABLES[entity] + ' WHERE id=?', (identifier,)).fetchone()
        if not row: return None
        value = {'row': dict(row)}
        if entity == 'vehicles': value['owners'] = [dict(row) for row in conn.execute('SELECT * FROM vehicle_owners WHERE vehicle_id=? ORDER BY id', (identifier,))]
        if entity == 'invoices':
            for table in ('payments', 'document_payment_baselines', 'stock_movements', 'fiscal_records'):
                value[table] = [dict(row) for row in conn.execute('SELECT * FROM ' + table + ' WHERE document_id=?', (identifier,))]
            value['references'] = [dict(row) for row in conn.execute('SELECT id,version,status FROM documents WHERE reference_id=? OR origin_id=? ORDER BY id', (identifier, identifier))]
        return value

    def _owner(self, conn, source_id, key):
        row = conn.execute("SELECT target_id FROM import_records WHERE source_id=? AND entity='customers' AND source_key=? AND active=1", (source_id, key)).fetchone()
        require(row and conn.execute('SELECT 1 FROM customers WHERE id=? AND archived=0', (row['target_id'],)).fetchone(), 'Falta el cliente de origen o está archivado.', 'conflict')
        return row['target_id']

    def _write(self, conn, batch, record):
        entity, key = record['entity'], record['source_key']; value = json.loads(record['payload']); resolution = json.loads(record['resolution'])
        old = conn.execute('SELECT * FROM import_records WHERE source_id=? AND entity=? AND source_key=? AND active=1', (batch['source_id'], entity, key)).fetchone()
        if record['action'] == 'skip': return 'skipped'
        if old and old['source_hash'] == record['source_hash']: return 'unchanged'
        require(record['action'] != 'unchanged', 'El destino ha cambiado desde la vista previa. Vuelve a simular.', 'conflict')
        require(not old or record['action'] == 'replace' and resolution.get('replace') and resolution.get('reason'), 'Conflicto de identidad: vuelve a revisar el lote.', 'conflict')
        if old: require(json.loads(old['imported_state']) == self._state(conn, entity, old['target_id']), 'El registro tiene actividad posterior; no se sobrescribe.', 'conflict')
        identifier = old['target_id'] if old and entity != 'invoices' else uid(); previous_target_after = None
        if record['action'] == 'link':
            identifier = resolution['link']
            require(entity in ('customers', 'vehicles') and conn.execute('SELECT 1 FROM ' + TABLES[entity] + ' WHERE id=? AND archived=0', (identifier,)).fetchone(), 'La ficha vinculada ha cambiado.', 'conflict')
            if entity == 'vehicles': require(conn.execute('SELECT customer_id FROM vehicles WHERE id=?', (identifier,)).fetchone()[0] == self._owner(conn, batch['source_id'], value['customer_key']), 'La matrícula pertenece a otro cliente; usa transferencia de titularidad fuera de la importación.', 'conflict')
        elif entity == 'customers':
            fields = {key: str(value.get(key, '') or '') for key in CUSTOMER_FIELDS}
            fields['tax_id'] = plate(fields['tax_id']); fields['country'] = fields['country'] or 'ES'
            fields['search_text'] = normalized(' '.join(fields.values())) + ' ' + plate(fields['phone']) + ' ' + plate(fields['phone2'])
            if old: conn.execute('UPDATE customers SET ' + ','.join(key + '=?' for key in fields) + ',updated_at=?,version=version+1 WHERE id=?', (*fields.values(), now(), identifier))
            else: conn.execute('INSERT INTO customers(id,' + ','.join(fields) + ',created_at,updated_at) VALUES(' + ','.join('?' for _ in range(len(fields) + 3)) + ')', (identifier, *fields.values(), now(), now()))
        elif entity == 'vehicles':
            owner = self._owner(conn, batch['source_id'], value['customer_key'])
            fields = {key: value.get(key, '') for key in VEHICLE_FIELDS}; fields['plate_normalized'] = plate(fields['plate'])
            if old:
                require(conn.execute('SELECT customer_id FROM vehicles WHERE id=?', (identifier,)).fetchone()[0] == owner, 'El cambio de propietario requiere transferencia documentada, no reimportación.')
                conn.execute('UPDATE vehicles SET ' + ','.join(key + '=?' for key in fields) + ',updated_at=?,version=version+1 WHERE id=?', (*fields.values(), now(), identifier))
            else:
                conn.execute('INSERT INTO vehicles(id,customer_id,' + ','.join(fields) + ',created_at,updated_at) VALUES(' + ','.join('?' for _ in range(len(fields) + 4)) + ')', (identifier, owner, *fields.values(), now(), now()))
                conn.execute('INSERT INTO vehicle_owners(id,vehicle_id,customer_id,from_date,reason) VALUES(?,?,?,?,?)', (uid(), identifier, owner, now(), 'Importación: ' + batch['id']))
        else:
            if old:
                conn.execute("UPDATE documents SET status='import_reverted',updated_at=?,version=version+1 WHERE id=?", (now(), old['target_id']))
                previous_target_after = self._state(conn, entity, old['target_id'])
            owner = self._owner(conn, batch['source_id'], value['customer_key']); vehicle_id = None
            if value.get('vehicle_key'):
                vehicle = conn.execute("SELECT target_id FROM import_records WHERE source_id=? AND entity='vehicles' AND source_key=? AND active=1", (batch['source_id'], value['vehicle_key'])).fetchone()
                require(vehicle, 'No se encuentra el vehículo de origen.'); vehicle_id = vehicle['target_id']
            payload = {key: value[key] for key in ('lines', 'taxes', 'base_cents', 'tax_cents', 'total_cents', 'payment_state', 'snapshot_certainty', 'amount_differences')}
            payload.update({'customer': value['customer_snapshot'], 'issuer': value['issuer_snapshot'], 'vehicle': value.get('vehicle_snapshot'), 'historical': True, 'test_document': False,
                            'invoice_type': value.get('invoice_type', 'F1'), 'source': 'Access/intermedio', 'branding': {}, 'notes': value.get('notes', ''), 'kilometres': value.get('kilometres'),
                            'footer': 'Documento histórico importado. Conserve el original.', 'import_provenance': {'source_id': batch['source_id'], 'source_key': key, 'source_hash': record['source_hash'], 'batch_id': batch['id'], 'calculation_evidence': value.get('calculation_evidence'), 'difference_evidence': resolution.get('reason') if resolution.get('accept_difference') else None}})
            legacy_key = 'access:' + fingerprint([batch['source_id'], key, batch['id']])
            conn.execute('INSERT INTO documents(id,kind,status,customer_id,vehicle_id,issue_date,full_number,payload,base_cents,tax_cents,total_cents,legacy_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (identifier, 'invoice', 'historical', owner, vehicle_id, value['issue_date'], str(value['full_number']), dumps(payload), value['base_cents'], value['tax_cents'], value['total_cents'], legacy_key, now(), now()))
            if value.get('paid_cents') is not None:
                conn.execute('INSERT INTO document_payment_baselines VALUES(?,?,?,?,?)', (identifier, value['paid_cents'], 'Saldo explícito del origen ' + batch['source_id'] + ' / ' + key, 'import:' + identifier, now()))
        state = self._state(conn, entity, identifier)
        current = {'source_id': batch['source_id'], 'entity': entity, 'source_key': key, 'source_hash': record['source_hash'], 'target_id': identifier, 'batch_id': batch['id'], 'original_json': record['original'], 'imported_state': dumps(state), 'active': 1}
        conn.execute('INSERT INTO import_records(' + ','.join(current) + ') VALUES(' + ','.join('?' for _ in current) + ') ON CONFLICT(source_id,entity,source_key) DO UPDATE SET source_hash=excluded.source_hash,target_id=excluded.target_id,batch_id=excluded.batch_id,original_json=excluded.original_json,imported_state=excluded.imported_state,active=1', tuple(current.values()))
        action = 'link' if record['action'] == 'link' else 'replace' if old else 'insert'
        conn.execute('INSERT INTO import_changes(batch_id,entity,source_key,action,before_record,after_record,created_at) VALUES(?,?,?,?,?,?,?)', (batch['id'], entity, key, action, dumps(dict(old)) if old else None, dumps({'record': current, 'prior_target_after': previous_target_after}), now()))
        return action

    def _step(self, conn, batch, start, limit):
        stage_conn = Staging(self._folder(batch['id'])).connect()
        try:
            rows = stage_conn.execute('SELECT * FROM records WHERE position>? ORDER BY position LIMIT ?', (start, limit)).fetchall()
            results = {}; counts = {entity: 0 for entity in ENTITIES}
            for record in rows:
                action = self._write(conn, batch, record); results[action] = results.get(action, 0) + 1
                if action in ('insert', 'replace', 'link'): counts[record['entity']] += 1
            cursor = rows[-1]['position'] if rows else start
            remaining = stage_conn.execute('SELECT count(*) FROM records WHERE position>?', (cursor,)).fetchone()[0]
            return {'cursor': cursor, 'remaining': remaining, 'done': remaining == 0, 'actions': results, 'counts': counts}
        finally: stage_conn.close()

    def simulate(self, batch_id, limit=250, acknowledge_warnings=False):
        require(isinstance(limit, int) and 1 <= limit <= 500, 'La simulación admite de 1 a 500 registros por paso.')
        with self.db.lock:
            review = self.review(batch_id); batch = self._batch(batch_id)
            require(batch['status'] in ('previewed', 'simulated'), 'Revisa el mapeo antes de simular.')
            require(not review['incident_counts']['error'], 'Resuelve todas las incidencias bloqueantes antes de simular.')
            folder = self._folder(batch_id); simulation_path = folder / 'simulation.sqlite'
            if not simulation_path.exists():
                require(acknowledge_warnings or not review['incident_counts']['warning'], 'Confirma que has revisado las advertencias y los datos desconocidos.')
                with self.db.read() as original:
                    temporary = simulation_path.with_suffix('.tmp'); temporary.unlink(missing_ok=True)
                    clone = sqlite3.connect(temporary); original.backup(clone); clone.close(); os.replace(temporary, simulation_path)
            conn = sqlite3.connect(simulation_path); conn.row_factory = sqlite3.Row
            try:
                conn.execute('PRAGMA foreign_keys=ON'); conn.execute('BEGIN IMMEDIATE')
                saved = self._batch(batch_id, conn)
                info = saved['summary'].get('simulation', {'cursor': 0, 'done': False, 'counts': {entity: 0 for entity in ENTITIES}, 'actions': {}})
                if not info['done']:
                    result = self._step(conn, batch, saved['cursor'], limit)
                    info.update({'cursor': result['cursor'], 'remaining': result['remaining'], 'done': result['done']})
                    for field in ('counts', 'actions'):
                        for key, count in result[field].items(): info[field][key] = info[field].get(key, 0) + count
                    conn.execute('UPDATE import_batches SET cursor=?,summary=? WHERE id=?', (result['cursor'], dumps({**saved['summary'], 'simulation': info}), batch_id))
                conn.commit()
                info['database_bytes'] = conn.execute('PRAGMA page_count').fetchone()[0] * conn.execute('PRAGMA page_size').fetchone()[0]
            except sqlite3.IntegrityError as exc:
                conn.rollback(); raise AppError('La simulación detectó un conflicto de identidad/relación. Revisa códigos y matrículas; la base principal no ha cambiado.', 'conflict') from exc
            finally: conn.close()
            if info['done']:
                with self.db.transaction() as real:
                    summary = {**batch['summary'], 'simulation': info, 'warnings_acknowledged': True}
                    real.execute("UPDATE import_batches SET status='simulated',summary=?,updated_at=? WHERE id=?", (dumps(summary), now(), batch_id))
            return info

    def run(self, batch_id, limit=250):
        require(isinstance(limit, int) and 1 <= limit <= 500, 'El lote admite de 1 a 500 registros por paso.')
        with self.db.lock:
            batch = self._batch(batch_id)
            if batch['status'] == 'completed': return {'done': True, 'cursor': batch['cursor'], 'remaining': 0, 'summary': batch['summary']}
            require(batch['status'] in ('simulated', 'running', 'paused'), 'Completa la simulación antes de importar.')
            capacity = self.capacity(batch_id)
            require(capacity['within_limit'], f"El conjunto de base y originales supera la capacidad de la copia previa ({capacity['limit_bytes'] // (1024 * 1024)} MiB o {capacity['file_limit']} archivos). No se aplicará este paso. Descarta ensayos sin importar o prepara un conjunto menor conservando los originales fuera de la aplicación; no se ha truncado ningún registro.", 'backup_capacity', capacity)
            if not batch['summary'].get('backup'):
                backup = self.backups.create()
                with self.db.transaction() as conn:
                    summary = {**batch['summary'], 'backup': backup, 'counts': {entity: 0 for entity in ENTITIES}, 'actions': {}}
                    conn.execute("UPDATE import_batches SET status='running',summary=?,updated_at=? WHERE id=?", (dumps(summary), now(), batch_id))
            try:
                with self.db.transaction() as conn:
                    batch = self._batch(batch_id, conn); result = self._step(conn, batch, batch['cursor'], limit); summary = batch['summary']
                    for field in ('counts', 'actions'):
                        for key, count in result[field].items(): summary[field][key] = summary[field].get(key, 0) + count
                    conn.execute('UPDATE import_batches SET cursor=?,status=?,summary=?,updated_at=? WHERE id=?', (result['cursor'], 'completed' if result['done'] else 'running', dumps(summary), now(), batch_id))
                    self.db.audit(conn, 'import.step', batch_id, {'source_id': batch['source_id'], **result})
                    if result['done']: conn.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?,?)', (uid(), batch['source_digest'], dumps(summary['counts']), now()))
                return {**result, 'summary': summary}
            except sqlite3.IntegrityError as exc: raise AppError('Este paso se ha revertido por un conflicto de identidad. Conserva el lote y revisa el destino; los pasos anteriores siguen identificados.', 'conflict') from exc

    def pause(self, batch_id):
        with self.db.transaction() as conn:
            require(self._batch(batch_id, conn)['status'] in ('running', 'paused'), 'Solo se pausa un lote en curso.')
            conn.execute("UPDATE import_batches SET status='paused',updated_at=? WHERE id=?", (now(), batch_id))
        return self.review(batch_id)

    def reconcile(self, batch_id, page=0):
        batch = self._batch(batch_id); stage_conn = Staging(self._folder(batch_id)).connect(); page = max(0, int(page))
        totals = {key: 0 for key in ('source_invoices', 'destination_invoices', 'source_lines', 'destination_lines', 'source_base_cents', 'source_tax_cents', 'source_total_cents', 'destination_base_cents', 'destination_tax_cents', 'destination_total_cents', 'unknown_payment', 'differences', 'excluded')}
        items = []
        try:
            with self.db.read() as conn:
                for index, row in enumerate(stage_conn.execute("SELECT * FROM records WHERE entity='invoices' ORDER BY position")):
                    value = json.loads(row['payload']); current = conn.execute("SELECT * FROM import_records WHERE source_id=? AND entity='invoices' AND source_key=? AND active=1", (batch['source_id'], row['source_key'])).fetchone()
                    destination = conn.execute('SELECT * FROM documents WHERE id=? AND status=\'historical\'', (current['target_id'],)).fetchone() if current else None
                    delta = {}; excluded = row['action'] == 'skip'
                    if excluded or value.get('invalid'):
                        totals['excluded'] += int(excluded)
                        totals['differences'] += int(not excluded)
                        if page * 50 <= index < (page + 1) * 50: items.append({'source_key': row['source_key'], 'full_number': value.get('full_number', ''), 'excluded': excluded, 'differences': {'invalid': int(not excluded)}})
                        continue
                    else:
                        totals['source_invoices'] += 1; totals['source_lines'] += len(value['lines'])
                        for key in ('base_cents', 'tax_cents', 'total_cents'): totals['source_' + key] += value[key]
                        if destination:
                            payload = json.loads(destination['payload']); totals['destination_invoices'] += 1; totals['destination_lines'] += len(payload['lines'])
                            for key in ('base_cents', 'tax_cents', 'total_cents'):
                                totals['destination_' + key] += destination[key]; delta[key] = destination[key] - value[key]
                            delta['lines'] = len(payload['lines']) - len(value['lines']); delta['source_changed'] = int(current['source_hash'] != row['source_hash'])
                            delta['line_content'] = int(fingerprint(payload['lines']) != fingerprint(value['lines']))
                            delta['tax_breakdown'] = int(fingerprint(payload['taxes']) != fingerprint(value['taxes']))
                            if payload.get('payment_state') == 'unknown' and not conn.execute('SELECT 1 FROM document_payment_baselines WHERE document_id=?', (destination['id'],)).fetchone(): totals['unknown_payment'] += 1
                        else: delta['missing'] = 1
                        if any(delta.values()): totals['differences'] += 1
                    if page * 50 <= index < (page + 1) * 50: items.append({'source_key': row['source_key'], 'full_number': value['full_number'], 'target_id': destination['id'] if destination else None, 'excluded': excluded, 'differences': delta, 'source_internal_differences': value['amount_differences']})
                changes = conn.execute('SELECT count(*) FROM import_changes WHERE batch_id=?', (batch_id,)).fetchone()[0]
                entity_counts = {}
                for entity in ENTITIES:
                    count = {'source': 0, 'destination': 0, 'excluded': 0, 'missing_keys': 0}
                    for row in stage_conn.execute('SELECT * FROM records WHERE entity=?', (entity,)):
                        if row['action'] == 'skip': count['excluded'] += 1; continue
                        count['source'] += 1
                        target = conn.execute('SELECT target_id FROM import_records WHERE source_id=? AND entity=? AND source_key=? AND active=1', (batch['source_id'], entity, row['source_key'])).fetchone()
                        present = bool(target and conn.execute('SELECT 1 FROM ' + TABLES[entity] + (' WHERE id=? AND status=\'historical\'' if entity == 'invoices' else ' WHERE id=? AND archived=0'), (target['target_id'],)).fetchone())
                        count['destination'] += int(present); count['missing_keys'] += int(not present)
                    entity_counts[entity] = count
            return {'batch_id': batch_id, 'status': batch['status'], 'totals': totals, 'items': items, 'page': page, 'page_size': 50, 'changes': changes,
                    'entity_counts': entity_counts, 'balanced': batch['status'] == 'completed' and totals['differences'] == 0 and all(not count['missing_keys'] for count in entity_counts.values()), 'original_sha256': batch['source_digest'], 'series_changed': False, 'fiscal_enqueued': False}
        finally: stage_conn.close()

    def rollback(self, batch_id, reason):
        require(isinstance(reason, str) and reason.strip(), 'Documenta el motivo de la reversión.')
        with self.db.lock:
            batch = self._batch(batch_id)
            if batch['status'] == 'reverted': return {'reverted': True, 'already_reverted': True}
            require(batch['status'] in ('completed', 'running', 'paused'), 'El lote no tiene cambios reversibles.')
            backup = self.backups.create()
            with self.db.transaction() as conn:
                changes = [dict(row) for row in conn.execute('SELECT * FROM import_changes WHERE batch_id=? ORDER BY id DESC', (batch_id,))]
                target_ids = {json.loads(change['after_record'])['record']['target_id'] for change in changes}
                for change in changes:
                    after = json.loads(change['after_record']); record = after['record']; entity = change['entity']
                    current = conn.execute('SELECT * FROM import_records WHERE source_id=? AND entity=? AND source_key=?', (record['source_id'], entity, record['source_key'])).fetchone()
                    require(current and current['batch_id'] == batch_id and current['target_id'] == record['target_id'], 'Otro lote ha reutilizado este registro. Revierte primero los lotes posteriores.', 'conflict')
                    if change['action'] != 'link': require(self._state(conn, entity, record['target_id']) == json.loads(record['imported_state']), 'Hay actividad posterior en una ficha/factura. No se revierte el lote.', 'conflict')
                    if after.get('prior_target_after'):
                        prior = json.loads(change['before_record']); require(self._state(conn, entity, prior['target_id']) == after['prior_target_after'], 'El histórico sustituido tiene actividad posterior.', 'conflict')
                    if change['action'] == 'insert' and entity in ('customers', 'vehicles'):
                        column = 'customer_id' if entity == 'customers' else 'vehicle_id'
                        for table in ('documents', 'events'):
                            references = conn.execute('SELECT id FROM ' + table + ' WHERE ' + column + '=?', (record['target_id'],)).fetchall()
                            require(all(row['id'] in target_ids for row in references), 'La ficha se ha usado después de importar; no se borrará actividad.', 'conflict')
                        if entity == 'customers':
                            references = conn.execute('SELECT id FROM vehicles WHERE customer_id=?', (record['target_id'],)).fetchall()
                            require(all(row['id'] in target_ids for row in references), 'El cliente tiene vehículos añadidos después; no se revierte el lote.', 'conflict')
                for change in changes:
                    after = json.loads(change['after_record']); record = after['record']; entity = change['entity']; before = json.loads(change['before_record']) if change['before_record'] else None
                    if change['action'] != 'link':
                        if entity == 'invoices':
                            conn.execute("UPDATE documents SET status='import_reverted',updated_at=?,version=version+1 WHERE id=?", (now(), record['target_id']))
                            if before: conn.execute("UPDATE documents SET status='historical',updated_at=?,version=version+1 WHERE id=?", (now(), before['target_id']))
                        elif before:
                            fields = {key: value for key, value in json.loads(before['imported_state'])['row'].items() if key not in ('id', 'version', 'updated_at')}
                            conn.execute('UPDATE ' + TABLES[entity] + ' SET ' + ','.join(key + '=?' for key in fields) + ',version=version+1,updated_at=? WHERE id=?', (*fields.values(), now(), record['target_id']))
                        else: conn.execute('UPDATE ' + TABLES[entity] + ' SET archived=1,version=version+1,updated_at=? WHERE id=?', (now(), record['target_id']))
                    if before:
                        before['imported_state'] = dumps(self._state(conn, entity, before['target_id']))
                        fields = {key: value for key, value in before.items() if key not in ('source_id', 'entity', 'source_key')}
                        conn.execute('UPDATE import_records SET ' + ','.join(key + '=?' for key in fields) + ' WHERE source_id=? AND entity=? AND source_key=?', (*fields.values(), record['source_id'], entity, record['source_key']))
                    else: conn.execute('UPDATE import_records SET active=0 WHERE source_id=? AND entity=? AND source_key=?', (record['source_id'], entity, record['source_key']))
                summary = {**batch['summary'], 'rollback': {'reason': reason.strip(), 'backup': backup, 'at': now(), 'changes': len(changes)}}
                conn.execute("UPDATE import_batches SET status='reverted',summary=?,updated_at=? WHERE id=?", (dumps(summary), now(), batch_id)); self.db.audit(conn, 'import.rollback', batch_id, summary['rollback'])
            return {'reverted': True, 'changes': len(changes), 'originals_retained': True}

    def export_report_chunk(self, batch_id, offset=0):
        self._batch(batch_id); require(isinstance(offset, int) and offset >= 0, 'Posición no válida.')
        path = self._folder(batch_id) / 'report.jsonl'
        if offset == 0:
            temporary = path.with_suffix('.tmp'); conn = Staging(self._folder(batch_id)).connect()
            try:
                with temporary.open('w', encoding='utf-8') as output:
                    output.write(dumps({'type': 'review', 'value': self.review(batch_id)}) + '\n')
                    for table in ('incidents', 'records', 'raw_rows'):
                        for row in conn.execute('SELECT * FROM ' + table): output.write(dumps({'type': table, 'value': dict(row)}) + '\n')
                    output.write(dumps({'type': 'reconciliation', 'value': self.reconcile(batch_id)}) + '\n'); output.flush(); os.fsync(output.fileno())
                os.replace(temporary, path)
            finally: conn.close(); temporary.unlink(missing_ok=True)
        require(path.exists() and offset <= path.stat().st_size, 'Informe no disponible; inicia la descarga desde cero.')
        with path.open('rb') as source: source.seek(offset); content = source.read(CHUNK_BYTES)
        return {'name': 'importacion-' + batch_id + '.jsonl', 'offset': offset, 'next_offset': offset + len(content), 'size': path.stat().st_size, 'content': base64.b64encode(content).decode(), 'done': offset + len(content) == path.stat().st_size}
