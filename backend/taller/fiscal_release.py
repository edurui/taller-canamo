"""Offline release dossier verification. No dossier is shipped as approved.

External observations remain the responsibility of the named reviewer. This
checks their artifacts against the installed build and actual stored exchanges;
it never turns a synthetic response or a settings checkbox into acceptance.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .errors import AppError, require

WINDOWS_CHECKS = ('install','upgrade','reinstall','launch','dpapi','single_instance',
                  'backup_restore','physical_print')
MAX_ARTIFACT_SIZE = 100_000_000
MAX_RUNTIME_SIZE = 2*1024**3
POLICY_FILE = Path(__file__).resolve().parent/'release-policy.json'


def _packaged_windows():
    return os.name=='nt' and bool(getattr(sys,'frozen',False))


def build_policy():
    """The build is only eligible for review; this never approves production."""
    result={'edition':'development','candidate_build':False,'packaged_windows':_packaged_windows(),
            'application_version':__version__,'policy_sha256':'','error':''}
    try:
        require(POLICY_FILE.is_file() and POLICY_FILE.stat().st_size<=4096,
                'Falta la política de la edición empaquetada.','release_build')
        content=POLICY_FILE.read_bytes()
        policy=json.loads(content)
        require(isinstance(policy,dict) and set(policy)=={'format_version','application_version','edition'}
                and type(policy['format_version']) is int and policy['format_version']==1
                and policy['application_version']==__version__
                and policy['edition'] in ('development','release_candidate'),
                'La política de edición no corresponde a esta versión.','release_build')
        result.update(edition=policy['edition'],policy_sha256=hashlib.sha256(content).hexdigest())
        require(result['packaged_windows'] and policy['edition']=='release_candidate',
                'Esta edición de desarrollo no permite producción. Se necesita el candidato Windows empaquetado, ensayado y su expediente.','release_build')
        result['candidate_build']=True
    except (AppError,OSError,ValueError,TypeError,KeyError) as exc:
        result['error']=str(exc)[:700]
    return result


def _digest(path, max_size=MAX_ARTIFACT_SIZE):
    require(path.is_file() and path.stat().st_size <= max_size,
            'Artefacto ausente o demasiado grande.', 'release_evidence')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1_048_576),b''):
            digest.update(block)
    return digest.hexdigest()


def _artifact(folder, spec):
    path = (folder/spec['path']).resolve()
    require(path.is_relative_to(folder.resolve()) and path != folder.resolve(),
            'Un artefacto sale de la carpeta del expediente.', 'release_evidence')
    require(_digest(path) == spec['sha256'], 'Huella distinta en un artefacto del expediente.', 'release_evidence')
    return path


def _runtime_binary():
    require(os.name == 'nt' and getattr(sys,'frozen',False),
            'La liberación exige el servicio Windows empaquetado que se ensayó.', 'release_evidence')
    return Path(sys.executable)


def _wire_matches(conn, record, operation, fingerprint):
    from .fiscal import TEST_ENDPOINT, parse_response, _xml_values, validate_official_xml
    from .fiscal_query import QUERY, xml_query, parse_query_response, compare_query_record
    wires = conn.execute('SELECT * FROM fiscal_wire_evidence WHERE record_id=? AND operation=?',
                         (record['id'],operation)).fetchall()
    data = json.loads(record['payload'])
    for wire in wires:
        if wire['endpoint'] != TEST_ENDPOINT or wire['certificate_fingerprint'] != fingerprint:
            continue
        try:
            if operation == 'supply':
                evidence = conn.execute('SELECT * FROM fiscal_attempts WHERE id=? AND record_id=?',
                                        (wire['evidence_id'],record['id'])).fetchone()
                if not evidence:
                    continue
                request,response = record['xml'],evidence['response']
                result = parse_response(response,data,record['kind'])
            else:
                evidence = conn.execute('SELECT * FROM fiscal_reconciliations WHERE id=? AND record_id=?',
                                        (wire['evidence_id'],record['id'])).fetchone()
                if not evidence:
                    continue
                request,response = evidence['request_xml'],evidence['response_xml']
                expected = validate_official_xml(xml_query(data),'ConsultaLR.xsd',QUERY,'ConsultaFactuSistemaFacturacion')
                actual = validate_official_xml(request,'ConsultaLR.xsd',QUERY,'ConsultaFactuSistemaFacturacion')
                require(_xml_values(actual) == _xml_values(expected), 'Consulta de liberación distinta de la solicitada.')
                rows,cursor = parse_query_response(response,data)
                require(len(rows) == 1 and cursor is None, 'Consulta de liberación incompleta.')
                result = compare_query_record(rows[0],record['xml'],record['kind'])
            if (hashlib.sha256(request.encode()).hexdigest() == wire['request_sha256']
                    and hashlib.sha256(response.encode()).hexdigest() == wire['response_sha256']
                    and result['status'] in ('accepted','accepted_with_errors')):
                return True
        except (AppError,ValueError,TypeError,KeyError):
            continue
    return False


def verify_release_dossier(db, config):
    return _verify_release_dossier(db,config,db.root/'secure'/'release-evidence')


def _verify_release_dossier(db, config, folder):
    """Internal staging entry; the public checker always uses the installed path."""
    from .fiscal import verify_schema_files
    manifest = folder/'manifest.json'
    try:
        require(manifest.is_file(), 'Falta el expediente de liberación de esta versión.', 'release_evidence')
        require(manifest.stat().st_size <= 1_000_000, 'Expediente de liberación demasiado grande.', 'release_evidence')
        dossier = json.loads(manifest.read_text(encoding='utf-8'))
        require(dossier['format_version'] == 1 and dossier['application_version'] == __version__,
                'El expediente corresponde a otra versión del programa.', 'release_evidence')
        require(dossier['producer_nif'] == config['fiscal']['producer_tax_id']
                and dossier['system_id'] == config['fiscal']['system_id'],
                'El expediente no corresponde al productor/sistema configurado.', 'release_evidence')
        require(dossier['declaration_sha256'] == hashlib.sha256(config['fiscal']['declaration_text'].encode()).hexdigest(),
                'La declaración responsable difiere de la revisada.', 'release_evidence')
        require(isinstance(dossier['reviewer'],str) and len(dossier['reviewer'].strip()) >= 3,
                'Falta el responsable de la revisión.', 'release_evidence')
        require(datetime.fromisoformat(dossier['reviewed_at']).utcoffset() is not None,
                'La revisión debe registrar fecha y huso horario.', 'release_evidence')
        binary_hash = _digest(_runtime_binary(),max_size=MAX_RUNTIME_SIZE)
        require(dossier['sidecar_sha256'] == binary_hash, 'El binario instalado difiere del ensayado.', 'release_evidence')
        schemas = verify_schema_files()
        require(dossier['schemas'] == {name:meta['sha256'] for name,meta in schemas['files'].items()},
                'El expediente no cubre estos esquemas oficiales.', 'release_evidence')
        windows = json.loads(_artifact(folder,dossier['windows']).read_text(encoding='utf-8'))
        require(windows['platform'] == 'Windows' and windows['application_version'] == __version__
                and windows['sidecar_sha256'] == binary_hash,
                'El informe Windows no corresponde al binario instalado.', 'release_evidence')
        for check in WINDOWS_CHECKS:
            evidence = windows['checks'][check]
            require(evidence['result'] == 'passed' and bool(evidence['artifacts']),
                    'Falta evidencia Windows: '+check, 'release_evidence')
            for artifact in evidence['artifacts']:
                _artifact(folder,artifact)
        fingerprint = (config['fiscal'].get('certificate_info') or {}).get('fingerprint','')
        require(re.fullmatch('[0-9A-F]{64}',fingerprint), 'Falta la huella del certificado ensayado.', 'release_evidence')
        with db.read() as conn:
            for scenario in ('alta','subsanacion','anulacion','consulta'):
                record = conn.execute('SELECT * FROM fiscal_records WHERE id=?',(dossier['aeat'][scenario],)).fetchone()
                require(record is not None and record['environment'] == 'aeat_test',
                        'Falta un registro oficial de pruebas para '+scenario+'.', 'release_evidence')
                data = json.loads(record['payload'])
                require(data['issuer_nif'] == config['company']['tax_id']
                        and data['producer']['nif'] == dossier['producer_nif']
                        and data['producer']['system_id'] == dossier['system_id']
                        and data['producer'].get('version') == __version__,
                        'La prueba autenticada corresponde a otro emisor/productor/versión.', 'release_evidence')
                require(scenario == 'consulta' or record['kind'] == scenario,
                        'La prueba autenticada no corresponde a la operación declarada.', 'release_evidence')
                require(_wire_matches(conn,record,'query' if scenario=='consulta' else 'supply',fingerprint),
                        'Falta un intercambio mTLS verificable para '+scenario+'. Las respuestas inyectadas no sirven.', 'release_evidence')
        return {'ok':True,'reviewer':dossier['reviewer'],'reviewed_at':dossier['reviewed_at'],
                'manifest_sha256':_digest(manifest),'network_called':False}
    except (AppError,OSError,ValueError,KeyError,TypeError) as exc:
        return {'ok':False,'error':str(exc)[:700],'network_called':False}
