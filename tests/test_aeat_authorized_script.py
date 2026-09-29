"""Offline guards and explicitly simulated RPC; no real AEAT acceptance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_aeat_authorized as verifier
from taller.app import App
from taller.errors import AppError
from test_fiscal_official import enable_injected_transport,issue,response
from test_fiscal_workflow import query_reply


@pytest.fixture
def trial(tmp_path,monkeypatch):
    data=tmp_path/'isolated-test-account'
    initialized=verifier.initialize(data,tmp_path/'operational-never-opened')
    app=App(data)
    app.settings.save('company',{'legal_name':'SYNTHETIC LOCAL TEST','tax_id':'89890001K'})
    customer=app.contacts.save_customer({'name':'SYNTHETIC LOCAL CUSTOMER','tax_id':'12345678Z',
                                        'address':'Synthetic address','postal_code':'41300','city':'Synthetic city'})
    enable_injected_transport(app,monkeypatch)
    (data/'secure'/'certificate.dpapi').write_bytes(b'SYNTHETIC PLACEHOLDER - NOT A CERTIFICATE')
    app.settings.internal_update('fiscal','certificate_info',{'fingerprint':'A'*64,'expires':'2099-01-01T00:00:00+00:00'})
    app.settings.save('fiscal',{'declaration_text':'SYNTHETIC UNIT TEST DECLARATION; NOT A RELEASE'})
    document=issue(app,customer)
    record=app.fiscal.details(document['payload']['fiscal']['record_id'])
    binary=tmp_path/'synthetic-not-a-windows-program.exe'
    binary.write_bytes(b'SYNTHETIC UNIT TEST - NEVER EXECUTE')
    config=app.settings.get()
    manifest={'format_version':1,'workspace_id':initialized['workspace_id'],
              'installation_id':config['fiscal']['installation_id'],'issuer_nif':'89890001K',
              'producer_nif':'12345678Z','system_id':'EC','certificate_fingerprint':'A'*64,
              'sidecar_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
              'steps':[{'record_id':record['id'],'record_hash':record['hash'],'operation':'send','expected_status':'accepted'}]}
    path=data/'selection.json'
    path.write_text(json.dumps(manifest),encoding='utf-8')
    return SimpleNamespace(app=app,data=data,customer=customer,record=record,manifest=manifest,path=path,binary=binary)


def test_init_creates_only_marker_and_never_opens_operational_directory(tmp_path):
    operational=tmp_path/'operational'
    operational.mkdir()
    original=operational/'taller.sqlite3'
    original.write_bytes(b'UNREAD OPERATING-DATA SENTINEL')
    root=tmp_path/'isolated'
    result=verifier.initialize(root,operational)
    assert result['database_created'] is False and result['network_attempted'] is False
    assert [p.name for p in root.iterdir()]==[verifier.MARKER]
    assert original.read_bytes()==b'UNREAD OPERATING-DATA SENTINEL'
    with pytest.raises(AppError,match='carpeta nueva'):
        verifier.initialize(root,operational)
    with pytest.raises(AppError,match='separadas'):
        verifier.initialize(operational/'nested',operational)
    with pytest.raises(AppError,match='fuera del proyecto'):
        verifier.initialize(verifier.ROOT/'forbidden-private-test',operational)


def test_default_cli_checks_without_starting_service_or_modifying_database(trial,monkeypatch,capsys):
    monkeypatch.setattr(verifier,'Service',lambda *args:pytest.fail('Default check must not start a service'))
    with trial.app.db.read() as conn:
        before='\n'.join(conn.iterdump())
    assert verifier.main(['--data',str(trial.data),'--manifest',str(trial.path),'--sidecar',str(trial.binary)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['network_attempted'] is False and result['service_started'] is False
    assert result['release_approved'] is False
    with trial.app.db.read() as conn:
        assert '\n'.join(conn.iterdump())==before


def test_standalone_cli_and_authorization_guard(trial):
    command=[sys.executable,str(verifier.ROOT/'scripts'/'verify_aeat_authorized.py')]
    flags=['--data',str(trial.data),'--manifest',str(trial.path),'--sidecar',str(trial.binary)]
    checked=subprocess.run([*command,'check',*flags],capture_output=True,text=True,timeout=15)
    assert checked.returncode==0 and json.loads(checked.stdout)['network_attempted'] is False
    refused=subprocess.run([*command,'run',*flags],capture_output=True,text=True,timeout=15)
    assert refused.returncode==1 and '--authorized' in json.loads(refused.stdout)['error']['message']
    assert not (trial.data/'authorized-aeat-evidence').exists()


@pytest.mark.parametrize('mutation,match',[
    ('production','aeat_test'),('certificate','certificado'),('declaration','declaración'),
    ('binary','ejecutable'),('record_hash','huella'),('other_environment','otro entorno'),('release','liberación'),
    ('other_pending','fuera del manifiesto')])
def test_preflight_guards_fail_before_service_or_tls(trial,monkeypatch,mutation,match):
    if mutation=='production':
        trial.app.settings.internal_update('fiscal','mode','production')
    elif mutation=='certificate':
        (trial.data/'secure'/'certificate.dpapi').unlink()
    elif mutation=='declaration':
        trial.app.settings.save('fiscal',{'declaration_text':''})
    elif mutation=='binary':
        trial.binary.write_bytes(b'CHANGED SYNTHETIC BINARY')
    elif mutation=='record_hash':
        trial.manifest['steps'][0]['record_hash']='B'*64
        trial.path.write_text(json.dumps(trial.manifest),encoding='utf-8')
    elif mutation=='release':
        folder=trial.data/'secure'/'release-evidence'
        folder.mkdir()
        (folder/'manifest.json').write_text('{}',encoding='utf-8')
    elif mutation=='other_environment':
        # Legacy/malformed database fixture only; never an emitted production record.
        with trial.app.db.transaction() as conn:
            conn.execute('DROP TRIGGER fiscal_no_update')
            conn.execute("UPDATE fiscal_records SET environment='production'")
    else:
        issue(trial.app,trial.customer)
    monkeypatch.setattr(verifier,'Service',lambda *args:pytest.fail('Guard must precede service startup'))
    with pytest.raises(AppError,match=match):
        verifier.preflight(trial.data,trial.path,trial.binary)


def simulated_service(trial,monkeypatch):
    """Explicit local substitute. Injected replies create no mTLS evidence."""
    calls=[]
    class SimulatedService:
        def __init__(self,command,data):
            assert command==[str(trial.binary)] and data==trial.data
        def call(self,action,params=None):
            calls.append(action)
            if action=='bootstrap':
                return trial.app.bootstrap()
            if action=='fiscal.readiness':
                return {'test_endpoint':verifier.TEST_ENDPOINT,'production_ready':False,'build_policy':{
                    'candidate_build':True,'fixture':'EXPLICIT SIMULATION; NOT A WINDOWS CANDIDATE'}}
            if action=='fiscal.check':
                return trial.app.fiscal.verify_chain()
            if action=='fiscal.send':
                return trial.app.fiscal.send_next(transport=lambda xml:response(trial.record['payload']))
            if action=='fiscal.reconcile':
                return trial.app.fiscal.reconcile(params['record_id'],transport=lambda xml:query_reply(trial.record))
            pytest.fail('The verifier requested an action outside its bounded flow: '+action)
        def shutdown(self):
            calls.append('simulated.shutdown')
        def abort(self):
            pytest.fail('The simulated service should shut down cleanly')
    monkeypatch.setattr(verifier,'Service',SimulatedService)
    monkeypatch.setattr(verifier,'_is_windows',lambda:True)
    return calls


def test_simulated_send_keeps_exact_receipts_and_refuses_fake_acceptance(trial,monkeypatch):
    calls=simulated_service(trial,monkeypatch)
    result=verifier.execute(trial.data,trial.path,trial.binary,authorized=True)
    assert result['ok'] is False and result['release_approved'] is False
    assert calls==['bootstrap','fiscal.readiness','fiscal.check','fiscal.send','simulated.shutdown']
    report=json.loads(Path(result['report']).read_text())
    assert report['error']['code']=='aeat_result'
    assert report['steps'][0]['result']['status']=='accepted'
    assert report['steps'][0]['verified_result'] is False
    assert report['steps'][0]['authenticated_evidence']==[]
    for path,digest in report['artifacts'].items():
        assert hashlib.sha256((Path(result['report']).parent/path).read_bytes()).hexdigest()==digest
    with trial.app.db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM fiscal_records').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM fiscal_wire_evidence').fetchone()[0]==0


def test_simulated_uncertain_requires_query_and_preserves_query_bytes(trial,monkeypatch):
    trial.app.fiscal.send_next(transport=lambda xml:(_ for _ in ()).throw(TimeoutError('SYNTHETIC TIMEOUT')))
    calls=simulated_service(trial,monkeypatch)
    refused=verifier.execute(trial.data,trial.path,trial.binary,authorized=True)
    assert refused['network_attempted'] is False and 'fiscal.send' not in calls
    assert json.loads(Path(refused['report']).read_text())['error']['code']=='aeat_guard'
    with trial.app.db.transaction() as conn:
        conn.execute("UPDATE fiscal_outbox SET next_attempt='2020-01-01T00:00:00+00:00'")
        conn.execute("UPDATE fiscal_channels SET next_allowed_at='2020-01-01T00:00:00+00:00'")
    trial.manifest['steps'][0]['operation']='query'
    trial.path.write_text(json.dumps(trial.manifest),encoding='utf-8')
    result=verifier.execute(trial.data,trial.path,trial.binary,authorized=True)
    assert result['ok'] is False and 'fiscal.reconcile' in calls
    folder=Path(result['report']).parent/trial.record['id']
    assert list(folder.glob('query-*-request.xml')) and list(folder.glob('query-*-response.xml'))


def test_persistent_wait_is_not_shortened_or_sent(trial,monkeypatch):
    with trial.app.db.transaction() as conn:
        conn.execute("UPDATE fiscal_channels SET next_allowed_at='2099-01-01T00:00:00+00:00'")
    calls=simulated_service(trial,monkeypatch)
    result=verifier.execute(trial.data,trial.path,trial.binary,authorized=True,max_wait=0)
    assert result['network_attempted'] is False and 'fiscal.send' not in calls
    assert json.loads(Path(result['report']).read_text())['error']['code']=='aeat_wait'


def test_queue_order_cannot_send_another_selected_record(trial,monkeypatch):
    document=issue(trial.app,trial.customer)
    later=trial.app.fiscal.details(document['payload']['fiscal']['record_id'])
    trial.manifest['steps'].insert(0,{'record_id':later['id'],'record_hash':later['hash'],
                                    'operation':'send','expected_status':'accepted'})
    trial.path.write_text(json.dumps(trial.manifest),encoding='utf-8')
    calls=simulated_service(trial,monkeypatch)
    result=verifier.execute(trial.data,trial.path,trial.binary,authorized=True)
    assert result['network_attempted'] is False and 'fiscal.send' not in calls
    assert 'primero de la cola' in json.loads(Path(result['report']).read_text())['error']['message']
