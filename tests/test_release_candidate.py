"""Local release-policy tests; no assertion represents external acceptance."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from taller import __version__, fiscal_release, release_tools
from taller.documents import _is_test_document
from taller.errors import AppError
from taller.fiscal import Fiscal
from taller.fiscal_release import MAX_ARTIFACT_SIZE, MAX_RUNTIME_SIZE, WINDOWS_CHECKS


@pytest.mark.parametrize('edition,packaged,expected', [
    ('development',False,False),('development',True,False),
    ('release_candidate',False,False),('release_candidate',True,True)])
def test_embedded_policy_requires_packaged_windows(tmp_path,monkeypatch,edition,packaged,expected):
    policy=tmp_path/'release-policy.json'
    policy.write_text(json.dumps({'format_version':1,'application_version':__version__,'edition':edition}),encoding='utf-8')
    monkeypatch.setattr(fiscal_release,'POLICY_FILE',policy)
    monkeypatch.setattr(fiscal_release,'_packaged_windows',lambda:packaged)
    result=fiscal_release.build_policy()
    assert result['candidate_build'] is expected
    assert result['policy_sha256']==hashlib.sha256(policy.read_bytes()).hexdigest()


@pytest.mark.parametrize('policy', [
    {'format_version':True,'application_version':__version__,'edition':'release_candidate'},
    {'format_version':1,'application_version':'another-version','edition':'release_candidate'},
    {'format_version':1,'application_version':__version__,'edition':'release_candidate','approved':True},
    [],None])
def test_malformed_policy_fails_closed(tmp_path,monkeypatch,policy):
    path=tmp_path/'release-policy.json'
    path.write_text(json.dumps(policy),encoding='utf-8')
    monkeypatch.setattr(fiscal_release,'POLICY_FILE',path)
    monkeypatch.setattr(fiscal_release,'_packaged_windows',lambda:True)
    result=fiscal_release.build_policy()
    assert result['candidate_build'] is False and result['error']


def test_candidate_configuration_uses_private_readiness_and_still_needs_evidence(app,monkeypatch):
    monkeypatch.setattr(fiscal_release,'build_policy',lambda:{'candidate_build':True,'error':''})
    observed=[]
    original=Fiscal._readiness
    def capture(self,config):
        observed.append(config)
        return original(self,config)
    monkeypatch.setattr(Fiscal,'_readiness',capture)
    with pytest.raises(AppError,match='expediente') as failure:
        app.dispatch('settings.save',{'section':'fiscal','values':{
            'mode':'production','producer_name':'SYNTHETIC TEST',
            'producer_tax_id':'12345678Z','declaration_text':'SYNTHETIC UNIT TEST ONLY'}})
    assert failure.value.code=='production_blocked'
    assert observed[-1]['fiscal']['mode']=='production'
    assert observed[-1]['fiscal']['producer_tax_id']=='12345678Z'
    assert app.settings.get()['fiscal']['mode']=='local_test'
    with pytest.raises(AppError):
        app.dispatch('fiscal.readiness',{'config':observed[-1]})
    with pytest.raises(AppError) as missing:
        app.dispatch('fiscal._readiness',{'config':observed[-1]})
    assert missing.value.code=='not_found'


@pytest.mark.parametrize('mode,expected',[('local_test',True),('aeat_test',True),('production',False)])
def test_document_mark_is_pure_environment_metadata(mode,expected):
    assert _is_test_document(mode) is expected


@pytest.mark.parametrize('kind',['invoice','quote','order'])
def test_altering_configuration_cannot_publish_production(app,customer,monkeypatch,kind):
    document=app.documents.save({'kind':kind,'customer_id':customer['id'],
                                'lines':[{'description':'SYNTHETIC TEST','quantity':'1','unit_price':'10','tax_rate':'21'}]})
    series=app.settings.list_series()
    app.settings.internal_update('fiscal','mode','production')
    monkeypatch.setattr(app.certificates,'context',lambda:pytest.fail('Must fail before opening the certificate'))
    with pytest.raises(AppError) as failure:
        app.documents.publish(document['id'])
    assert failure.value.code=='production_blocked'
    stored=app.documents.get(document['id'])
    assert stored['status']=='draft' and stored['full_number'] is None
    assert stored['payload']==document['payload']
    assert app.settings.list_series()==series
    with app.db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fiscal_records').fetchone()[0]==0


def test_runtime_hash_streams_over_100mb_but_artifact_limit_is_preserved(tmp_path):
    path=tmp_path/'synthetic-sparse-runtime.bin'
    with path.open('wb') as stream:
        stream.truncate(MAX_ARTIFACT_SIZE+1)
    with path.open('rb') as stream:
        expected=hashlib.file_digest(stream,'sha256').hexdigest()
    assert fiscal_release._digest(path,max_size=MAX_RUNTIME_SIZE)==expected
    with pytest.raises(AppError,match='demasiado grande'):
        fiscal_release._digest(path)
    with path.open('wb') as stream:
        stream.truncate(MAX_RUNTIME_SIZE+1)
    with pytest.raises(AppError,match='demasiado grande'):
        fiscal_release._digest(path,max_size=MAX_RUNTIME_SIZE)


def test_cli_never_creates_missing_database(tmp_path,capsys):
    root=tmp_path/'missing-installation'
    assert release_tools.main(['--data',str(root),'--verify-release-evidence'])==1
    result=json.loads(capsys.readouterr().out)
    assert result['ok'] is False and result['production_activated'] is False
    assert not root.exists()


def test_tools_do_not_activate_or_mutate_database(app,tmp_path):
    with app.db.read() as conn:
        before=[tuple(row) for row in conn.execute('SELECT * FROM audit ORDER BY seq')]
    result=release_tools.verify(app.db.root)
    assert result['ok'] is False and result['network_called'] is False
    assert result['production_activated'] is False
    with pytest.raises(AppError):
        release_tools.install(app.db.root,tmp_path/'absent')
    with app.db.read() as conn:
        assert [tuple(row) for row in conn.execute('SELECT * FROM audit ORDER BY seq')]==before
    assert app.settings.get()['fiscal']['mode']=='local_test'
    assert not (app.db.root/'secure'/'release-evidence').exists()


def test_copy_preserves_results_and_only_referenced_evidence(tmp_path):
    # This exercises file copying only. These not_run observations cannot pass
    # the real verifier and do not represent Windows tests.
    source=tmp_path/'source'
    source.mkdir()
    artifact=source/'synthetic.txt'
    artifact.write_text('SYNTHETIC COPY FIXTURE',encoding='utf-8')
    spec={'path':artifact.name,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}
    report=source/'windows-report.json'
    report.write_text(json.dumps({'checks':{name:{'result':'not_run','artifacts':[spec]} for name in WINDOWS_CHECKS}}),encoding='utf-8')
    manifest=source/'manifest.json'
    manifest.write_text(json.dumps({'windows':{'path':report.name,'sha256':hashlib.sha256(report.read_bytes()).hexdigest()}}),encoding='utf-8')
    (source/'unreferenced-private-content.txt').write_text('not part of dossier',encoding='utf-8')
    destination=tmp_path/'copied'
    release_tools._copy_dossier(source,destination)
    assert sorted(item.name for item in destination.iterdir())==['manifest.json','synthetic.txt','windows-report.json']
    assert (destination/'windows-report.json').read_bytes()==report.read_bytes()
    assert all(value['result']=='not_run' for value in json.loads(report.read_text())['checks'].values())


def test_installer_restores_previous_folder_if_atomic_placement_fails(app,tmp_path,monkeypatch):
    # Filesystem compensation test only. The verifier result is an explicit
    # stub; this test neither creates nor attests a successful fiscal dossier.
    source=tmp_path/'incoming'
    source.mkdir()
    destination=app.db.root/'secure'/'release-evidence'
    destination.mkdir()
    (destination/'original-marker').write_text('old private evidence',encoding='utf-8')
    monkeypatch.setattr(release_tools,'build_policy',lambda:{'candidate_build':True,'error':''})
    monkeypatch.setattr(release_tools,'_verify_release_dossier',lambda *args:{'ok':True,'synthetic_stub':True})
    def staged_copy(source,staged):
        staged.mkdir()
        (staged/'new-marker').write_text('synthetic filesystem test',encoding='utf-8')
    monkeypatch.setattr(release_tools,'_copy_dossier',staged_copy)
    original=release_tools.os.replace
    def fail_placement(source,target):
        if source.name=='dossier':
            raise OSError('synthetic placement failure')
        return original(source,target)
    monkeypatch.setattr(release_tools.os,'replace',fail_placement)
    with pytest.raises(OSError,match='placement'):
        release_tools.install(app.db.root,source)
    assert (destination/'original-marker').read_text()=='old private evidence'
    assert not (destination/'new-marker').exists()
    assert app.settings.get()['fiscal']['mode']=='local_test'


def test_standalone_entry_verifies_without_initializing_app_or_writing_db(app):
    with app.db.read() as conn:
        before='\n'.join(conn.iterdump())
    result=subprocess.run([sys.executable,'-m','taller.release_tools','--data',str(app.db.root),
                           '--verify-release-evidence'],cwd=Path(fiscal_release.__file__).resolve().parent.parent,
                          capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and result.stderr==''
    output=json.loads(result.stdout)
    assert output['ok'] is False and output['network_called'] is False
    assert output['production_activated'] is False
    with app.db.read() as conn:
        assert '\n'.join(conn.iterdump())==before
