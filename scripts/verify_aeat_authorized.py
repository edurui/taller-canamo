"""Run explicitly authorized AEAT tests against existing records in an isolated DB.

The default `check` command never starts a service or opens the network. `run`
uses the exact Windows sidecar over JSONL, with its background timer disabled.
This maintainer script neither creates invoices nor installs a certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'scripts'))

from taller import __version__
from taller.backups import _restore_lock
from taller.certificates import private_directory
from taller.db import SCHEMA_VERSION
from taller.errors import AppError,require
from taller.files import atomic_write
from taller.fiscal import TEST_ENDPOINT,parse_response,validate_stored_record,verify_schema_files,validate_official_xml,_xml_values
from taller.fiscal_query import QUERY,xml_query,parse_query_response,compare_query_record
from taller.settings import DEFAULTS
from taller.validation import valid_tax_id
from verify_sidecar import Service

MARKER='authorized-aeat-workspace.json'
PURPOSE='isolated_authorized_aeat_test'
ACTIVE=('pending','retry','uncertain','duplicate_review','sending','invalid_local','reconciliation_conflict')
TERMINAL=('accepted','accepted_with_errors','rejected')
SAFE_ID=re.compile(r'[A-Za-z0-9_-]{1,128}')


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(path,limit=1_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=limit,
            'Falta un archivo normal o supera el límite del ensayo.','aeat_guard')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read_json(path):
    digest(path)
    value=json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value,dict),'El JSON debe contener un objeto.','aeat_guard')
    return value


def isolated_paths(data,operational):
    require(data.is_absolute() and operational.is_absolute(),'Utiliza rutas absolutas.','aeat_guard')
    data,operational=data.resolve(),operational.resolve()
    require(not (data.is_relative_to(operational) or operational.is_relative_to(data)),
            'La carpeta de ensayo y la operativa deben estar separadas, sin contenerse.','aeat_guard')
    require(not (data.is_relative_to(ROOT) or ROOT.is_relative_to(data)),
            'El ensayo y sus evidencias privadas deben quedar fuera del proyecto.','aeat_guard')
    return data,operational


def initialize(data,operational):
    data,operational=isolated_paths(data,operational)
    require(not data.exists(),'El ensayo debe comenzar en una carpeta nueva; no se adopta una base existente.','aeat_guard')
    data.mkdir(parents=True,mode=0o700)
    private_directory(str(data))
    marker={'format_version':1,'purpose':PURPOSE,'workspace_id':str(uuid4()),
            'data_directory':str(data),'operational_directory':str(operational),'created_at':stamp()}
    atomic_write(data/MARKER,json.dumps(marker,ensure_ascii=False,indent=2).encode())
    return {'ok':True,'workspace_id':marker['workspace_id'],'database_created':False,
            'network_attempted':False,'production_activated':False}


@contextmanager
def connection(data):
    path=data/'taller.sqlite3'
    require(path.is_file() and not path.is_symlink(),'Falta la base de ensayo existente. El verificador no la crea.','aeat_guard')
    conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        require(conn.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION,
                'Abre primero la edición correspondiente para completar su migración.','aeat_guard')
        yield conn
    finally:
        conn.close()


def preflight(data,manifest_path,sidecar):
    data=data.resolve()
    marker=read_json(data/MARKER)
    require(marker.get('format_version')==1 and marker.get('purpose')==PURPOSE,
            'Falta el marcador creado por init para una carpeta nueva.','aeat_guard')
    actual,_=isolated_paths(Path(marker['data_directory']),Path(marker['operational_directory']))
    require(actual==data,'El marcador pertenece a otra carpeta.','aeat_guard')
    require(not (data/'.restore-journal.json').exists(),'Termina la recuperación pendiente antes del ensayo.','aeat_guard')
    require(not (data/'secure'/'release-evidence'/'manifest.json').exists(),
            'El ensayo no admite una instalación con expediente de liberación. Usa la cuenta aislada de pruebas.','aeat_guard')
    manifest=read_json(manifest_path)
    expected={'format_version','workspace_id','installation_id','issuer_nif','producer_nif',
              'system_id','certificate_fingerprint','sidecar_sha256','steps'}
    require(set(manifest)==expected and type(manifest['format_version']) is int and manifest['format_version']==1,
            'El manifiesto tiene un formato o campos no admitidos.','aeat_guard')
    require(manifest['workspace_id']==marker['workspace_id'],'El manifiesto pertenece a otro ensayo.','aeat_guard')
    require(sidecar.is_absolute() and sidecar.suffix.lower()=='.exe','Selecciona el ejecutable Windows exacto.','aeat_guard')
    binary_hash=digest(sidecar,2*1024**3)
    require(binary_hash==manifest['sidecar_sha256'],'El ejecutable difiere del indicado en el manifiesto.','aeat_guard')
    steps=manifest['steps']
    require(isinstance(steps,list) and 1<=len(steps)<=20,'Incluye entre 1 y 20 operaciones existentes.','aeat_guard')
    seen=set()
    for step in steps:
        require(isinstance(step,dict) and set(step)=={'record_id','record_hash','operation','expected_status'},
                'Operación del manifiesto no válida.','aeat_guard')
        require(isinstance(step['record_id'],str) and SAFE_ID.fullmatch(step['record_id'])
                and isinstance(step['record_hash'],str) and re.fullmatch('[0-9A-F]{64}',step['record_hash'])
                and step['operation'] in ('send','query')
                and step['expected_status'] in (*TERMINAL,'retry','reconciliation_conflict'),
                'ID, huella, operación o resultado esperado no admitido.','aeat_guard')
        pair=(step['record_id'],step['operation'])
        require(pair not in seen,'La misma operación aparece repetida en el manifiesto.','aeat_guard')
        seen.add(pair)
    selected={step['record_id'] for step in steps}
    with connection(data) as conn:
        stored=json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        config={**DEFAULTS,**stored,**{
            key:{**value,**stored.get(key,{})} for key,value in DEFAULTS.items() if isinstance(value,dict)}}
        fiscal=config['fiscal']
        require(fiscal['mode']=='aeat_test','Solo se admite el modo oficial de pruebas aeat_test.','aeat_guard')
        require(config['company']['legal_name'] and valid_tax_id(config['company']['tax_id'])
                and fiscal['producer_name'] and valid_tax_id(fiscal['producer_tax_id'])
                and fiscal['declaration_text'].strip(),'Completa emisor, productor y declaración antes del ensayo.','aeat_guard')
        require((fiscal['installation_id'],config['company']['tax_id'],fiscal['producer_tax_id'],fiscal['system_id'])==
                tuple(manifest[key] for key in ('installation_id','issuer_nif','producer_nif','system_id')),
                'La identidad de la instalación difiere del manifiesto.','aeat_guard')
        certificate=fiscal.get('certificate_info') or {}
        require(re.fullmatch('[0-9A-F]{64}',str(manifest['certificate_fingerprint']))
                and certificate.get('fingerprint')==manifest['certificate_fingerprint']
                and (data/'secure'/'certificate.dpapi').is_file(),
                'Falta el certificado protegido y su huella coincidente. Instálalo mediante la aplicación.','aeat_guard')
        expiry=datetime.fromisoformat(certificate.get('expires',''))
        require(expiry.utcoffset() is not None and expiry>datetime.now(timezone.utc),'El certificado no está vigente.','aeat_guard')
        require(conn.execute('SELECT COUNT(*) FROM import_batches').fetchone()[0]==0,
                'La base contiene una importación; no se admite como ensayo aislado.','aeat_guard')
        require(conn.execute("SELECT COUNT(*) FROM documents WHERE status IN ('historical','import_reverted') OR legacy_key IS NOT NULL OR (status!='draft' AND coalesce(json_extract(payload,'$.test_document'),0)!=1)").fetchone()[0]==0,
                'La base contiene documentos operativos, históricos o sin marca de prueba.','aeat_guard')
        rows=conn.execute('SELECT * FROM fiscal_records ORDER BY seq').fetchall()
        require(len(rows)<=500,'Este guion admite hasta 500 registros en una instalación de ensayo.','aeat_guard')
        previous=None
        records={}
        for row in rows:
            require(row['environment']=='aeat_test','Hay registros de otro entorno en la base.','aeat_guard')
            require(datetime.fromisoformat(row['created_at'])>=datetime.fromisoformat(marker['created_at']),
                    'Hay registros anteriores a la creación de la carpeta de ensayo.','aeat_guard')
            payload=validate_stored_record(row,previous)
            require(payload['issuer_nif']==manifest['issuer_nif'] and payload['producer']['nif']==manifest['producer_nif']
                    and payload['producer']['system_id']==manifest['system_id']
                    and payload['producer'].get('version')==__version__,
                    'Un registro corresponde a otra identidad o versión.','aeat_guard')
            previous={**payload,'hash':row['hash']}
            records[row['id']]=dict(row)
        require(selected<=records.keys(),'Falta un registro indicado en el manifiesto.','aeat_guard')
        require(all(records[step['record_id']]['hash']==step['record_hash'] for step in steps),
                'La huella de un registro no coincide con el manifiesto.','aeat_guard')
        pending={row[0] for row in conn.execute('SELECT record_id FROM fiscal_outbox WHERE status IN ('+','.join('?' for _ in ACTIVE)+')',ACTIVE)}
        require(pending<=selected,'Hay registros pendientes fuera del manifiesto; no se enviará una cola no revisada.','aeat_guard')
    verify_schema_files()
    return {'manifest':manifest,'marker':marker,'binary_sha256':binary_hash,'config':config}


def _is_windows():
    return os.name=='nt'


def _export(data,destination,record_id,fingerprint):
    """Preserve exact receipts, including failures; never fabricate wire rows."""
    with connection(data) as conn:
        record=dict(conn.execute('SELECT * FROM fiscal_records WHERE id=?',(record_id,)).fetchone())
        outbox=dict(conn.execute('SELECT * FROM fiscal_outbox WHERE record_id=?',(record_id,)).fetchone())
        attempts=[dict(row) for row in conn.execute('SELECT * FROM fiscal_attempts WHERE record_id=? ORDER BY rowid',(record_id,))]
        queries=[dict(row) for row in conn.execute('SELECT * FROM fiscal_reconciliations WHERE record_id=? ORDER BY rowid',(record_id,))]
        wires=[dict(row) for row in conn.execute('SELECT * FROM fiscal_wire_evidence WHERE record_id=? ORDER BY rowid',(record_id,))]
    folder=destination/record_id
    folder.mkdir(exist_ok=True)
    artifacts={}
    def save(name,content):
        require(SAFE_ID.fullmatch(name.rsplit('.',1)[0]),'Nombre de evidencia no válido.','aeat_guard')
        raw=content.encode('utf-8')
        atomic_write(folder/name,raw)
        artifacts[str((folder/name).relative_to(destination))]=hashlib.sha256(raw).hexdigest()
    save('request.xml',record['xml'])
    entries={}
    for attempt in attempts:
        save('attempt-'+attempt['id']+'.xml',attempt['response'])
        entries[attempt['id']]=('supply',record['xml'],attempt['response'])
    for query in queries:
        save('query-'+query['id']+'-request.xml',query['request_xml'])
        save('query-'+query['id']+'-response.xml',query['response_xml'])
        entries[query['id']]=('query',query['request_xml'],query['response_xml'])
    authenticated=[]
    for wire in wires:
        entry=entries.get(wire['evidence_id'])
        if not entry or wire['operation']!=entry[0] or wire['endpoint']!=TEST_ENDPOINT or wire['certificate_fingerprint']!=fingerprint:
            continue
        if (hashlib.sha256(entry[1].encode()).hexdigest()!=wire['request_sha256']
                or hashlib.sha256(entry[2].encode()).hexdigest()!=wire['response_sha256']):
            continue
        try:
            payload=json.loads(record['payload'])
            if entry[0]=='supply':
                status=parse_response(entry[2],payload,record['kind'])['status']
            else:
                request=validate_official_xml(entry[1],'ConsultaLR.xsd',QUERY,'ConsultaFactuSistemaFacturacion')
                expected=validate_official_xml(xml_query(payload),'ConsultaLR.xsd',QUERY,'ConsultaFactuSistemaFacturacion')
                require(_xml_values(request)==_xml_values(expected),'La consulta no corresponde a la identidad solicitada.','aeat_guard')
                rows,cursor=parse_query_response(entry[2],payload)
                require(cursor is None and len(rows)<=1,'La consulta requiere revisión de sus páginas.','aeat_guard')
                status=compare_query_record(rows[0],record['xml'],record['kind'])['status'] if rows else 'retry'
            authenticated.append({'evidence_id':wire['evidence_id'],'operation':wire['operation'],'status':status})
        except (AppError,ValueError,TypeError,KeyError):
            continue
    save('state.json',json.dumps({'record':record,'outbox':outbox,'attempts':attempts,
                                'queries':queries,'wires':wires},ensure_ascii=False,indent=2))
    return {'status':outbox['status'],'authenticated':authenticated,'artifacts':artifacts}


def _next(data,record_id,operation):
    with connection(data) as conn:
        current=dict(conn.execute('SELECT * FROM fiscal_outbox WHERE record_id=?',(record_id,)).fetchone())
        channel=conn.execute("SELECT * FROM fiscal_channels WHERE environment='aeat_test'").fetchone()
        if operation=='send' and current['status'] not in TERMINAL:
            require(current['status'] in ('pending','retry'),
                    'Un resultado incierto necesita primero una operación query; no se reenvía a ciegas.','aeat_guard')
            head=conn.execute('SELECT r.id FROM fiscal_records r JOIN fiscal_outbox o ON r.id=o.record_id WHERE o.status IN ('+','.join('?' for _ in ACTIVE)+') ORDER BY r.seq LIMIT 1',ACTIVE).fetchone()
            require(head and head['id']==record_id,'El ID solicitado no es el primero de la cola. Reordena el manifiesto.','aeat_guard')
        if operation=='query':
            require(current['status'] not in ('pending','local_only','sending'),
                    'El registro aún no permite consultar un resultado de envío.','aeat_guard')
        due=max(current['next_attempt'],channel['next_allowed_at'] if channel else '')
        if channel and channel['claim_token']:
            due=max(due,channel['claim_until'])
        return current,max(0,(datetime.fromisoformat(due)-datetime.now(timezone.utc)).total_seconds())


def execute(data,manifest_path,sidecar,*,authorized=False,max_wait=0):
    require(authorized,'run requiere --authorized para confirmar el acceso legítimo al entorno de pruebas.','aeat_guard')
    require(_is_windows(),'El ensayo autenticado utiliza el certificado DPAPI y el candidato Windows.','aeat_guard')
    initial=preflight(data,manifest_path,sidecar)
    data=data.resolve()
    manifest=initial['manifest']
    folder=data/'authorized-aeat-evidence'/str(uuid4())
    folder.mkdir(parents=True,mode=0o700)
    private_directory(str(folder))
    report={'format_version':1,'started_at':stamp(),'ok':False,'endpoint':TEST_ENDPOINT,
            'application_version':__version__,'sidecar_sha256':initial['binary_sha256'],
            'verifier_sha256':digest(Path(__file__).resolve()),
            'network_attempted':False,'production_activated':False,'release_approved':False,
            'steps':[],'artifacts':{}}
    atomic_write(folder/'input-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode())
    report['artifacts']['input-manifest.json']=digest(folder/'input-manifest.json')
    service=None
    started=time.monotonic()
    try:
        service=Service([str(sidecar)],data)
        boot=service.call('bootstrap')
        require(Path(boot['data_directory']).resolve()==data and boot['version']==__version__,
                'El servicio abrió otra carpeta o versión.','aeat_guard')
        require(boot['settings']==initial['config'],'La configuración cambió al abrir el servicio.','aeat_guard')
        readiness=service.call('fiscal.readiness')
        require(readiness['test_endpoint']==TEST_ENDPOINT and readiness['build_policy']['candidate_build'] is True
                and readiness['production_ready'] is False,
                'Se necesita el candidato Windows y su endpoint oficial de pruebas.','aeat_guard')
        report['build_policy']=readiness['build_policy']
        require(service.call('fiscal.check')['ok'],'La cadena fiscal no supera la comprobación.','aeat_guard')
        with _restore_lock(data):
            for step in manifest['steps']:
                with connection(data) as conn:
                    previous_evidence={row[0] for row in conn.execute('SELECT evidence_id FROM fiscal_wire_evidence WHERE record_id=?',(step['record_id'],))}
                while True:
                    current=preflight(data,manifest_path,sidecar)
                    require(current['manifest']==manifest and current['config']==initial['config'],
                            'La selección o configuración cambió durante el ensayo.','aeat_guard')
                    row,delay=_next(data,step['record_id'],step['operation'])
                    if step['operation']=='send' and row['status'] in TERMINAL:
                        result={'status':row['status'],'record_id':step['record_id'],'reused_existing_receipt':True}
                        break
                    if delay>0:
                        remaining=max_wait-(time.monotonic()-started)
                        require(remaining>0,'La espera fiscal sigue vigente. Conserva el informe y repite después; no se acorta.','aeat_wait')
                        time.sleep(min(delay,remaining,1))
                        continue
                    report['network_attempted']=True
                    result=service.call('fiscal.send' if step['operation']=='send' else 'fiscal.reconcile',
                                        {} if step['operation']=='send' else {'record_id':step['record_id']})
                    require(result.get('record_id')==step['record_id'],
                            'La acción no devolvió el registro seleccionado. Revisa su estado antes de repetir.','aeat_guard')
                    break
                evidence=_export(data,folder,step['record_id'],manifest['certificate_fingerprint'])
                report['artifacts'].update(evidence['artifacts'])
                operation='supply' if step['operation']=='send' else 'query'
                matched=any(item['operation']==operation and item['status']==step['expected_status']
                            and (result.get('reused_existing_receipt') or item['evidence_id'] not in previous_evidence)
                            for item in evidence['authenticated'])
                ok=result['status']==step['expected_status'] and matched
                report['steps'].append({**step,'result':result,'verified_result':ok,'authenticated_evidence':evidence['authenticated']})
                require(ok,'El resultado esperado no tiene un acuse/consulta mTLS coincidente. No se atribuye aceptación.','aeat_result')
        require(digest(sidecar,2*1024**3)==initial['binary_sha256'],'El ejecutable cambió durante el ensayo.','aeat_guard')
        report['ok']=True
    except Exception as exc:
        report['error']={'code':exc.code,'message':str(exc)} if isinstance(exc,AppError) else {
            'code':'aeat_run','message':'El servicio no completó el ensayo. Se conservan los estados y respuestas disponibles; revisa antes de repetir.'}
    finally:
        if service is not None:
            try:
                service.shutdown()
            except Exception:
                service.abort()
                report['ok']=False
                report['shutdown_error']='El servicio no confirmó el cierre. Comprueba la cola al reabrir.'
        for record_id in {step['record_id'] for step in manifest['steps']}:
            try:
                report['artifacts'].update(_export(data,folder,record_id,manifest['certificate_fingerprint'])['artifacts'])
            except Exception:
                report['ok']=False
                report['export_error']='No se pudo exportar todo el estado. Conserva la base de ensayo.'
        report['finished_at']=stamp()
        atomic_write(folder/'result.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    return {'ok':report['ok'],'report':str(folder/'result.json'),'steps_completed':len(report['steps']),
            'network_attempted':report['network_attempted'],'production_activated':False,'release_approved':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','check','run'),nargs='?',default='check')
    parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--operational-data',type=Path)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--sidecar',type=Path)
    parser.add_argument('--authorized',action='store_true')
    parser.add_argument('--max-wait-seconds',type=int,default=0)
    args=parser.parse_args(argv)
    try:
        require(0<=args.max_wait_seconds<=3600,'La espera máxima debe estar entre 0 y 3600 segundos.','aeat_guard')
        if args.command=='init':
            require(args.operational_data is not None,'init requiere --operational-data; solo se compara su ruta, nunca se abre.','aeat_guard')
            result=initialize(args.data,args.operational_data)
        else:
            require(args.manifest is not None and args.sidecar is not None,'Indica --manifest y --sidecar.','aeat_guard')
            if args.command=='run':
                result=execute(args.data,args.manifest,args.sidecar,authorized=args.authorized,max_wait=args.max_wait_seconds)
            else:
                checked=preflight(args.data,args.manifest,args.sidecar)
                result={'ok':True,'steps_checked':len(checked['manifest']['steps']),'network_attempted':False,
                        'service_started':False,'production_activated':False,'release_approved':False}
    except (AppError,OSError,sqlite3.DatabaseError,ValueError,TypeError,KeyError) as exc:
        result={'ok':False,'error':{'code':getattr(exc,'code','aeat_guard'),'message':str(exc) if isinstance(exc,AppError) else 'Archivo, formato o configuración de ensayo no válido.'},
                'network_attempted':False,'production_activated':False,'release_approved':False}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
