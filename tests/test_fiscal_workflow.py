"""Real SQLite workflow, migrations and synthetic responses using official XSDs.

No fixture below is an AEAT acknowledgement and no test opens a network socket.
"""
import copy
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from taller.app import App
from taller.db import Database, SCHEMA, SCHEMA_VERSION, migrate_connection
from taller.errors import AppError
from taller.fiscal import Fiscal, SF, LR, SOAP, xml_record
from taller.fiscal_query import QUERY, QUERY_RESPONSE, xml_query, parse_query_response
from taller.migrations import upgrade, v0002_fiscal, v0003_import_history
from taller import fiscal, fiscal_release
from taller.fiscal_release import WINDOWS_CHECKS, verify_release_dossier
from taller.validation import now

from test_fiscal_official import enable_injected_transport, issue, record_data, response


def add(parent,name,value=None,ns=QUERY_RESPONSE):
    node = ET.SubElement(parent,'{'+ns+'}'+name)
    if value is not None:
        node.text = value
    return node


def query_reply(record, *, empty=False, state='Correcto', mutate=None):
    """Synthetic consulta shaped by RespuestaConsultaLR.xsd; source is local XML."""
    data = record['payload'] if isinstance(record['payload'],dict) else json.loads(record['payload'])
    envelope = ET.Element('{'+SOAP+'}Envelope')
    message = add(add(envelope,'Body',ns=SOAP),'RespuestaConsultaFactuSistemaFacturacion')
    header = add(message,'Cabecera')
    add(header,'IDVersion','1.0',SF)
    issuer = add(header,'ObligadoEmision',ns=SF)
    add(issuer,'NombreRazon',data['issuer_name'],SF); add(issuer,'NIF',data['issuer_nif'],SF)
    year,month = (data.get('operation_date') or data['date']).split('-')[2],(data.get('operation_date') or data['date']).split('-')[1]
    tax_period = add(message,'PeriodoImputacion')
    add(tax_period,'Ejercicio',year); add(tax_period,'Periodo',month)
    add(message,'IndicadorPaginacion','N'); add(message,'ResultadoConsulta','SinDatos' if empty else 'ConDatos')
    if not empty:
        row = add(message,'RegistroRespuestaConsultaFactuSistemaFacturacion')
        identity = add(row,'IDFactura')
        for name,key in [('IDEmisorFactura','issuer_nif'),('NumSerieFactura','number'),('FechaExpedicionFactura','date')]:
            add(identity,name,data[key],SF)
        fields = add(row,'DatosRegistroFacturacion')
        local = ET.fromstring(record['xml']).find('.//{'+LR+'}RegistroFactura')[0]
        # Consulta places NombreRazonEmisor before RefExterna (supply reverses them).
        ordered = sorted(local,key=lambda field:0 if field.tag.rsplit('}',1)[-1]=='NombreRazonEmisor' else 1)
        for field in ordered:
            name = field.tag.rsplit('}',1)[-1]
            if name in ('IDVersion','IDFactura'):
                continue
            cloned = copy.deepcopy(field)
            cloned.tag = '{'+QUERY_RESPONSE+'}'+name
            if name in ('Destinatarios','FacturasRectificadas','FacturasSustituidas','Encadenamiento'):
                for nested in cloned:
                    nested.tag = '{'+QUERY_RESPONSE+'}'+nested.tag.rsplit('}',1)[-1]
            fields.append(cloned)
        presentation = add(row,'DatosPresentacion')
        add(presentation,'NIFPresentador',data['issuer_nif'],SF)
        add(presentation,'TimestampPresentacion',data['timestamp'],SF)
        add(presentation,'IdPeticion','SYNTHETIC-QUERY',SF)
        status = add(row,'EstadoRegistro')
        add(status,'TimestampUltimaModificacion',data['timestamp'])
        add(status,'EstadoRegistro',state)
        if mutate:
            mutate(fields)
    return ET.tostring(envelope,encoding='unicode')


def latest(app):
    with app.db.read() as conn:
        identifier = conn.execute('SELECT id FROM fiscal_records ORDER BY seq DESC LIMIT 1').fetchone()[0]
    return app.fiscal.details(identifier)


def due(app):
    """Advance just the persisted due deadlines for deterministic queue tests."""
    with app.db.transaction() as conn:
        conn.execute('UPDATE fiscal_channels SET next_allowed_at=?',(now(),))
        conn.execute('UPDATE fiscal_outbox SET next_attempt=?',(now(),))


def acknowledge(app, state='Correcto'):
    record = latest(app)
    due(app)
    return app.fiscal.send_next(transport=lambda _:response(record['payload'],state=state,kind=record['kind']))


def test_corrections_are_repeated_immutable_idempotent_and_keep_snapshots(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issued = issue(app,customer)
    original = latest(app)
    assert acknowledge(app,'AceptadoConErrores')['status'] == 'accepted_with_errors'
    first = app.fiscal.correct(original['id'],{'description':'Descripción subsanada'},'Error del registro','first-correction')
    assert first['kind'] == 'subsanacion'
    assert first['correction_of_id'] == original['id']
    assert first['payload']['rejection_previous'] == 'N'
    assert acknowledge(app)['status'] == 'accepted'
    second = app.fiscal.correct(first['id'],{'customer_name':'CLIENTE SINTÉTICO CORREGIDO'},'Segundo error de registro','second-correction')
    assert second['correction_of_id'] == first['id']
    assert second['previous_hash'] == first['hash']
    assert app.fiscal.correct(original['id'],{'description':'Descripción subsanada'},'Error del registro','first-correction')['id'] == first['id']
    with pytest.raises(AppError,match='clave'):
        app.fiscal.correct(original['id'],{'description':'Otra cosa'},'Error del registro','first-correction')
    with pytest.raises(AppError,match='posterior'):
        app.fiscal.correct(original['id'],{'description':'Otra cosa'},'Error del registro','third-correction')
    assert app.fiscal.details(original['id'])['xml'] == original['xml']
    assert app.documents.get(issued['id'])['payload'] == issued['payload']
    assert app.fiscal.verify_chain() == {'ok':True,'checked':3}


def test_correction_after_rejected_initial_uses_x_and_later_rejection_uses_s(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    original = latest(app)
    assert acknowledge(app,'Incorrecto')['status'] == 'rejected'
    corrected = app.fiscal.correct(original['id'],{'description':'Corregida'},'Corregir rechazo','reject-1')
    assert corrected['payload']['rejection_previous'] == 'X'
    assert acknowledge(app)['status'] == 'accepted'
    second = app.fiscal.correct(corrected['id'],{'description':'Segunda'},'Nuevo error de registro','reject-2')
    assert acknowledge(app,'Incorrecto')['status'] == 'rejected'
    third = app.fiscal.correct(second['id'],{'description':'Tercera'},'Corregir subsanación rechazada','reject-3')
    assert third['payload']['rejection_previous'] == 'S'


def test_same_correction_request_from_concurrent_callers_creates_one_record(app, customer):
    issue(app,customer)
    record = latest(app)
    def correct(_):
        return app.fiscal.correct(record['id'],{'description':'Dato corregido'},'Corrección sintética','shared-key')['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(correct,range(8)))
    assert len(set(results)) == 1
    assert len(app.fiscal.records()) == 2


def test_money_cannot_be_changed_through_record_correction(app, customer):
    issue(app,customer)
    with pytest.raises(AppError) as failure:
        app.fiscal.correct(latest(app)['id'],{'total':'1.00'},'Cambio comercial','change-total')
    assert failure.value.code == 'requires_rectification'
    assert len(app.fiscal.records()) == 1


def test_rejected_cancellation_can_be_corrected_without_altering_void_document(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    document = issue(app,customer)
    assert acknowledge(app)['status'] == 'accepted'
    app.documents.void(document['id'],'Factura generada por error','ANULAR')
    cancellation = latest(app)
    assert cancellation['kind'] == 'anulacion'
    assert acknowledge(app,'Incorrecto')['status'] == 'rejected'
    corrected = app.fiscal.correct(cancellation['id'],{},'Subsanar la anulación rechazada','cancel-reject')
    assert corrected['kind'] == 'anulacion'
    assert corrected['payload']['rejection_previous'] == 'S'
    assert corrected['payload']['no_previous_record'] == 'N'
    assert app.documents.get(document['id'])['status'] == 'void'
    assert acknowledge(app)['status'] == 'accepted'


@pytest.mark.parametrize('tax_kind',['E2','E3','E5'])
def test_unsupported_exempt_regime_blocks_emission_atomically(app, customer, tax_kind):
    draft = app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Exención sintética',
        'quantity':'1','unit_price':'100','tax_rate':'0','tax_kind':tax_kind,'tax_reason':'Causa ficticia'}]})
    series = app.settings.list_series()
    with pytest.raises(AppError) as failure:
        app.documents.publish(draft['id'])
    assert failure.value.code == 'unsupported_tax_regime'
    assert app.documents.get(draft['id'])['status'] == 'draft'
    assert app.settings.list_series() == series
    assert app.fiscal.records() == []


def test_query_request_and_synthetic_response_match_official_schema():
    data = record_data()
    xml,digest = xml_record(data)
    query = xml_query(data)
    root = ET.fromstring(query)
    assert root.findtext('.//{'+QUERY+'}NumSerieFactura') == data['number']
    rows,cursor = parse_query_response(query_reply({'payload':data,'xml':xml}),data)
    assert len(rows) == 1 and cursor is None
    assert rows[0].findtext('{'+QUERY_RESPONSE+'}DatosRegistroFacturacion/{'+QUERY_RESPONSE+'}Huella') == digest


def test_unknown_submission_is_confirmed_only_by_exact_official_query(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    assert app.fiscal.send_next(transport=lambda _: (_ for _ in ()).throw(TimeoutError('Synthetic timeout')))['status'] == 'uncertain'
    with pytest.raises(AppError,match='pendiente'):
        app.fiscal.correct(record['id'],{'description':'Nueva'},'No debe permitir corrección incierta','uncertain-correction')
    due(app)
    requests = []
    result = app.fiscal.send_next(transport=lambda xml:requests.append(xml) or query_reply(record))
    assert 'ConsultaFactuSistemaFacturacion' in requests[0]
    assert result['status'] == 'accepted' and result['verified_by'] == 'query'
    details = app.fiscal.details(record['id'])
    assert details['csv'] == ''
    assert len(details['attempt_history']) == 1
    assert len(details['reconciliations']) == 1
    assert json.loads(details['reconciliations'][0]['result'])['remote_request_id'] == 'SYNTHETIC-QUERY'


def test_not_found_query_precedes_retry_of_identical_xml(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    sent = []
    def lost(xml):
        sent.append(xml)
        raise TimeoutError('Synthetic timeout')
    assert app.fiscal.send_next(transport=lost)['status'] == 'uncertain'
    due(app)
    assert app.fiscal.send_next(transport=lambda _:query_reply(record,empty=True))['status'] == 'retry'
    due(app)
    assert app.fiscal.send_next(transport=lambda xml:sent.append(xml) or response(record['payload']))['status'] == 'accepted'
    assert sent == [record['xml'],record['xml']]


def test_unknown_correction_queries_prior_version_before_retrying_same_xml(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    original = latest(app)
    assert acknowledge(app)['status'] == 'accepted'
    corrected = app.fiscal.correct(original['id'],{'description':'Descripción nueva'},'Cambio en el registro','prior-still-present')
    due(app)
    assert app.fiscal.send_next(transport=lambda _:(_ for _ in ()).throw(TimeoutError()))['status'] == 'uncertain'
    due(app)
    result = app.fiscal.send_next(transport=lambda _:query_reply(original))
    assert result['status'] == 'retry' and result['previous_record_id'] == original['id']
    assert app.fiscal.details(corrected['id'])['xml'] == corrected['xml']
    assert acknowledge(app)['status'] == 'accepted'


def test_query_of_accepted_history_preserves_ack_when_known_correction_is_current(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    original = latest(app)
    assert acknowledge(app)['status'] == 'accepted'
    corrected = app.fiscal.correct(original['id'],{'description':'Descripción corregida'},'Corregir el registro','known-current')
    assert acknowledge(app)['status'] == 'accepted'
    due(app)
    result = app.fiscal.reconcile(original['id'],transport=lambda _:query_reply(corrected))
    assert result['status'] == 'accepted' and result['current_record_id'] == corrected['id']
    assert result['verified_by'] == 'query_history'
    assert app.fiscal.details(original['id'])['csv']


def test_cancellation_after_lost_reply_is_confirmed_by_exact_anulado_query(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    document = issue(app,customer)
    assert acknowledge(app)['status'] == 'accepted'
    app.documents.void(document['id'],'Duplicidad sintética','ANULAR')
    cancellation = latest(app)
    due(app)
    assert app.fiscal.send_next(transport=lambda _:(_ for _ in ()).throw(TimeoutError()))['status'] == 'uncertain'
    due(app)
    result = app.fiscal.send_next(transport=lambda _:query_reply(cancellation,state='Anulado'))
    assert result['status'] == 'accepted' and result['remote_state'] == 'Anulado'
    assert app.fiscal.details(cancellation['id'])['csv'] == ''


def test_certificate_setup_failure_does_not_claim_a_remote_result(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    monkeypatch.setattr(app.certificates,'context',lambda:(_ for _ in ()).throw(AppError('Clave bloqueada','certificate')))
    assert app.fiscal.send_next()['status'] == 'retry'
    record = latest(app)
    assert record['reconciliations'] == [] and record['attempt_history'][0]['response'] == ''
    assert 'No se ha iniciado el envío' in record['last_error']


def test_timezone_missing_in_schema_valid_query_remains_uncertain(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    assert app.fiscal.send_next(transport=lambda _:(_ for _ in ()).throw(TimeoutError()))['status'] == 'uncertain'
    def mutate(fields):
        fields.find('{'+QUERY_RESPONSE+'}FechaHoraHusoGenRegistro').text = '2026-09-23T10:00:00'
    raw = query_reply(record,mutate=mutate)
    due(app)
    assert app.fiscal.send_next(transport=lambda _:raw)['status'] == 'uncertain'
    assert app.fiscal.details(record['id'])['reconciliations'][0]['response_xml'] == raw


def test_chain_and_send_detect_xml_tampering_even_when_hash_fields_are_unchanged(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    # Deliberate offline corruption of a synthetic DB, bypassing its normal trigger.
    with app.db.transaction() as conn:
        conn.execute('DROP TRIGGER fiscal_no_update')
        conn.execute('UPDATE fiscal_records SET xml=? WHERE id=?',(
            record['xml'].replace('Trabajo sintético','Descripción alterada'),record['id']))
    assert app.fiscal.verify_chain()['ok'] is False
    assert app.fiscal.send_next(transport=lambda _:pytest.fail('Corrupt XML must not leave the process'))['status'] == 'invalid_local'


@pytest.mark.parametrize('field,value',[('Huella','A'*64),('DescripcionOperacion','Otro trabajo'),('ImporteTotal','999.00')])
def test_query_mismatch_never_becomes_acceptance_and_blocks_following_sends(app, customer, monkeypatch, field, value):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    app.fiscal.send_next(transport=lambda _: '<html>proxy sintético</html>')
    def mutate(node):
        node.find('{'+QUERY_RESPONSE+'}'+field).text = value
    due(app)
    result = app.fiscal.reconcile(record['id'],transport=lambda _:query_reply(record,mutate=mutate))
    assert result['status'] == 'reconciliation_conflict'
    issue(app,customer)
    due(app)
    assert app.fiscal.send_next(transport=lambda _:pytest.fail('No puede saltar un conflicto'))['status'] == 'reconciliation_conflict'


def test_duplicate_requires_query_and_conserves_original_acknowledgement(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    duplicate = response(record['payload'],state='Incorrecto',duplicate=True)
    assert app.fiscal.send_next(transport=lambda _:duplicate)['status'] == 'duplicate_review'
    due(app)
    assert app.fiscal.send_next(transport=lambda _:query_reply(record))['status'] == 'accepted'
    details = app.fiscal.details(record['id'])
    assert details['attempt_history'][0]['response'] == duplicate
    assert details['reconciliations'][0]['request_xml']


def test_global_wait_survives_restart_and_new_invoice(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    result = app.fiscal.send_next(transport=lambda _:response(record['payload'],wait='9999'))
    restarted = App(app.db.root)
    enable_injected_transport(restarted,monkeypatch)
    issue(restarted,customer)
    assert latest(restarted)['next_attempt'] == result['next_attempt']
    assert restarted.fiscal.send_next(transport=lambda _:pytest.fail('Global wait lost'))['status'] == 'idle'


def test_separate_service_objects_cannot_send_the_same_record_twice(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    another = Fiscal(app.db,app.settings,app.certificates)
    started,release = threading.Event(),threading.Event()
    def blocked(xml):
        started.set()
        assert release.wait(5)
        return response(record['payload'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(app.fiscal.send_next,blocked)
        assert started.wait(5)
        another.recover_interrupted()
        assert another.send_next(transport=lambda _:pytest.fail('Duplicate send'))['status'] == 'busy'
        release.set()
        assert first.result()['status'] == 'accepted'


def test_expired_sending_lease_becomes_uncertain_without_rewinding_global_wait(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    with app.db.transaction() as conn:
        conn.execute("UPDATE fiscal_outbox SET status='sending'")
        conn.execute("UPDATE fiscal_channels SET claimed_record_id=?,claim_token='dead-process',claim_until='2000-01-01T00:00:00+00:00',next_allowed_at='2099-01-01T00:00:00+00:00'",(record['id'],))
    app.fiscal.recover_interrupted()
    assert app.fiscal.details(record['id'])['status'] == 'uncertain'
    assert app.fiscal.send_next(transport=lambda _:pytest.fail('Wait ignored'))['next_attempt'] == '2099-01-01T00:00:00+00:00'


def create_v1(path):
    conn = sqlite3.connect(path,isolation_level=None)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)
    conn.execute('PRAGMA user_version=1')
    data = record_data()
    xml,digest = xml_record(data)
    stamp = now()
    conn.execute('INSERT INTO customers(id,name,search_text,created_at,updated_at) VALUES(?,?,?,?,?)',('c','Sintético','sintetico',stamp,stamp))
    conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
        base_cents,tax_cents,total_cents,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
        ('d','invoice','issued','c','2026-09-23','LEGACY-1','{}',10000,2100,12100,stamp,stamp))
    conn.execute('''INSERT INTO fiscal_records(seq,id,document_id,kind,environment,payload,xml,hash,previous_hash,created_at)
        VALUES(17,'r','d','alta','aeat_test',?,?,?,'',?)''',(json.dumps(data),xml,digest,stamp))
    conn.execute('INSERT INTO fiscal_outbox(record_id,status,next_attempt,updated_at) VALUES(?,?,?,?)',('r','uncertain',stamp,stamp))
    conn.execute('INSERT INTO fiscal_attempts VALUES(?,?,?,?,?)',('a','r','uncertain','synthetic lost response',stamp))
    return conn


def test_upgrade_v1_preserves_every_existing_record_and_foreign_key(tmp_path):
    root = tmp_path/'old';root.mkdir()
    conn = create_v1(root/'taller.sqlite3')
    before = conn.execute('SELECT * FROM fiscal_records').fetchall()
    attempts = conn.execute('SELECT * FROM fiscal_attempts').fetchall()
    conn.close()
    db = Database(root)
    assert db.migration_result == {'from_version':1,'to_version':SCHEMA_VERSION,'applied':list(range(2,SCHEMA_VERSION+1))}
    with db.read() as upgraded:
        rows = upgraded.execute('SELECT seq,id,document_id,kind,environment,payload,xml,hash,previous_hash,created_at FROM fiscal_records').fetchall()
        assert [tuple(row) for row in rows] == before
        assert [tuple(row) for row in upgraded.execute('SELECT * FROM fiscal_attempts')] == attempts
        assert not upgraded.execute('PRAGMA foreign_key_check').fetchall()
        assert upgraded.execute('SELECT idempotency_key FROM fiscal_records').fetchone()[0] == 'legacy:r'
        with pytest.raises(sqlite3.IntegrityError,match='inalterable'):
            upgraded.execute("UPDATE fiscal_records SET xml='changed'")
    snapshots = list((root/'backups').glob('pre-migration-v1-*.sqlite3'))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0] == 1
        assert old.execute('SELECT * FROM fiscal_records').fetchall() == before
    assert Database(root).migration_result['applied'] == []


def test_failed_upgrade_rolls_back_ddl_rows_version_and_restores_fk(tmp_path):
    conn = create_v1(tmp_path/'old.sqlite3')
    before = conn.execute('SELECT * FROM fiscal_records').fetchall()
    broken = SimpleNamespace(VERSION=2,NAME='injected-failure',SQL=v0002_fiscal.SQL+'\nINSERT INTO nonexistent_table VALUES(1);\n')
    with pytest.raises(sqlite3.OperationalError):
        upgrade(conn,SCHEMA,migrations=(broken,))
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
    assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert conn.execute('SELECT * FROM fiscal_records').fetchall() == before
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='fiscal_channels'").fetchone() is None
    assert migrate_connection(conn)['applied'] == list(range(2,SCHEMA_VERSION+1))
    conn.close()


def test_v3_allows_historical_numbers_without_weakening_issued_invoices(tmp_path):
    conn = create_v1(tmp_path/'old.sqlite3')
    upgrade(conn,SCHEMA,migrations=(v0002_fiscal,))
    original = conn.execute('SELECT * FROM documents WHERE id=?',('d',)).fetchone()
    assert migrate_connection(conn)['applied'] == list(range(3,SCHEMA_VERSION+1))
    assert conn.execute('SELECT * FROM documents WHERE id=?',('d',)).fetchone() == original
    stamp = now()
    for identifier,status in [('history-a','historical'),('history-b','historical'),('reverted-c','import_reverted')]:
        conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
            base_cents,tax_cents,total_cents,legacy_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (identifier,'invoice',status,'c','2026-09-23','LEGACY-1','{}',10000,2100,12100,identifier,stamp,stamp))
    with pytest.raises(sqlite3.IntegrityError,match='UNIQUE'):
        conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
            base_cents,tax_cents,total_cents,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('duplicate','invoice','issued','c','2026-09-23','LEGACY-1','{}',1,0,1,stamp,stamp))
    with pytest.raises(sqlite3.IntegrityError,match='editable'):
        conn.execute("UPDATE documents SET status='draft' WHERE id='d'")
    with pytest.raises(sqlite3.IntegrityError,match='modificar'):
        conn.execute("UPDATE documents SET payload='changed' WHERE id='reverted-c'")
    conn.execute('INSERT INTO document_payment_baselines VALUES(?,?,?,?,?)',('history-a',1000,'Evidencia sintética','baseline-1',stamp))
    with pytest.raises(sqlite3.IntegrityError,match='inalterable'):
        conn.execute('DELETE FROM document_payment_baselines')
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    conn.close()


def test_failure_during_document_rebuild_preserves_v2_and_all_references(tmp_path):
    conn = create_v1(tmp_path/'v2.sqlite3')
    upgrade(conn,SCHEMA,migrations=(v0002_fiscal,))
    original = conn.execute('SELECT * FROM documents').fetchall()
    broken = SimpleNamespace(VERSION=3,NAME='injected-v3-failure',SQL=v0003_import_history.SQL+'\nINSERT INTO nonexistent_table VALUES(1);\n')
    with pytest.raises(sqlite3.OperationalError):
        upgrade(conn,SCHEMA,migrations=(v0002_fiscal,broken))
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
    assert conn.execute('SELECT * FROM documents').fetchall() == original
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert conn.execute('SELECT document_id FROM fiscal_records').fetchone()[0] == 'd'
    assert migrate_connection(conn)['applied'] == list(range(3,SCHEMA_VERSION+1))
    conn.close()


def test_readiness_and_production_gate_never_call_network(app, monkeypatch):
    monkeypatch.setattr(app.certificates,'context',lambda:pytest.fail('Readiness opened a certificate'))
    result = app.fiscal.readiness()
    assert result['network_called'] is False
    assert result['production_ready'] is False
    assert {'issuer','producer','certificate','release'} <= {x['code'] for x in result['problems']}
    with pytest.raises(AppError) as failure:
        app.fiscal._endpoint('production')
    assert failure.value.code == 'production_blocked'


def test_changing_release_flag_does_not_replace_release_evidence(app, monkeypatch):
    monkeypatch.setattr(fiscal,'PRODUCTION_RELEASED',True)
    result = app.fiscal.readiness()
    assert result['production_ready'] is False
    assert any(item['code']=='release_evidence' for item in result['problems'])
    with pytest.raises(AppError,match='Producción bloqueada'):
        app.fiscal._endpoint('production')


def synthetic_release_dossier(app, record, monkeypatch):
    """Artificial artifact fixture only; never represents Windows or AEAT evidence."""
    folder = app.db.root/'secure'/'release-evidence'
    folder.mkdir()
    binary = folder/'synthetic-binary.txt'
    binary.write_text('SYNTHETIC UNIT TEST — NOT A RELEASE',encoding='utf-8')
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    monkeypatch.setattr(fiscal_release,'_runtime_binary',lambda:binary)
    config = app.settings.get()
    config['fiscal']['certificate_info'] = {'fingerprint':'A'*64}
    windows = {'platform':'Windows','application_version':fiscal.__version__,'sidecar_sha256':digest,
               'checks':{name:{'result':'passed','artifacts':[{'path':binary.name,'sha256':digest}]} for name in WINDOWS_CHECKS}}
    report = folder/'synthetic-windows.json'
    report.write_text(json.dumps(windows),encoding='utf-8')
    dossier = {'format_version':1,'application_version':fiscal.__version__,'producer_nif':config['fiscal']['producer_tax_id'],
               'system_id':config['fiscal']['system_id'],'sidecar_sha256':digest,'reviewer':'SYNTHETIC UNIT TEST',
               'reviewed_at':now(),'declaration_sha256':hashlib.sha256(config['fiscal']['declaration_text'].encode()).hexdigest(),
               'schemas':{name:meta['sha256'] for name,meta in fiscal.schema_manifest()['files'].items()},
               'windows':{'path':report.name,'sha256':hashlib.sha256(report.read_bytes()).hexdigest()},
               'aeat':{name:record['id'] for name in ('alta','subsanacion','anulacion','consulta')}}
    (folder/'manifest.json').write_text(json.dumps(dossier),encoding='utf-8')
    return config,report


def test_valid_injected_acceptance_never_counts_as_authenticated_release(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    record = latest(app)
    assert acknowledge(app)['status'] == 'accepted'
    config,_ = synthetic_release_dossier(app,record,monkeypatch)
    result = verify_release_dossier(app.db,config)
    assert result['ok'] is False and 'intercambio mTLS' in result['error']
    with app.db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fiscal_wire_evidence').fetchone()[0] == 0


def test_release_dossier_rejects_altered_evidence_bytes(app, customer, monkeypatch):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    config,report = synthetic_release_dossier(app,latest(app),monkeypatch)
    report.write_text('{}',encoding='utf-8')
    result = verify_release_dossier(app.db,config)
    assert result['ok'] is False and 'Huella distinta' in result['error']


def test_release_verifier_accepts_runtime_size_over_100mb_without_accepting_fake_evidence(app,customer,monkeypatch,tmp_path):
    enable_injected_transport(app,monkeypatch)
    issue(app,customer)
    config,report=synthetic_release_dossier(app,latest(app),monkeypatch)
    binary=tmp_path/'synthetic-sparse-runtime.bin'
    with binary.open('wb') as stream:
        stream.truncate(fiscal_release.MAX_ARTIFACT_SIZE+1)
    with binary.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    monkeypatch.setattr(fiscal_release,'_runtime_binary',lambda:binary)
    windows=json.loads(report.read_text())
    windows['sidecar_sha256']=digest
    report.write_text(json.dumps(windows),encoding='utf-8')
    manifest=report.parent/'manifest.json'
    dossier=json.loads(manifest.read_text())
    dossier['sidecar_sha256']=digest
    dossier['windows']['sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(dossier),encoding='utf-8')
    result=verify_release_dossier(app.db,config)
    assert result['ok'] is False and 'intercambio mTLS' in result['error']
