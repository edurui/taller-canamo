"""Local maintainer tool for existing evidence; never emits or invents results."""
import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .certificates import private_directory
from .db import SCHEMA_VERSION,uid
from .errors import AppError,require
from .fiscal_release import build_policy,_verify_release_dossier,_artifact,WINDOWS_CHECKS
from .settings import DEFAULTS


class _ReadOnlyDatabase:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.path=self.root/'taller.sqlite3'
        require(self.path.is_file(),'No existe la base local seleccionada. Esta herramienta no crea ni migra datos.','release_evidence')

    @contextmanager
    def read(self):
        conn=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        conn.row_factory=sqlite3.Row
        try:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA trusted_schema=OFF')
            require(conn.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION,
                    'Abre primero esta versión de la aplicación para revisar una migración pendiente.','release_evidence')
            yield conn
        finally:
            conn.close()


def _configuration(db):
    with db.read() as conn:
        row=conn.execute('SELECT data FROM settings WHERE id=1').fetchone()
        require(row is not None,'Falta la configuración de la instalación.','release_evidence')
        stored=json.loads(row['data'])
    return {**DEFAULTS,**stored,**{
        key:{**value,**stored.get(key,{})} for key,value in DEFAULTS.items() if isinstance(value,dict)}}


def verify(root):
    db=_ReadOnlyDatabase(root)
    policy=build_policy()
    result=_verify_release_dossier(db,_configuration(db),db.root/'secure'/'release-evidence')
    return {'ok':bool(policy['candidate_build'] and result['ok']),'build_policy':policy,
            'release_evidence':result,'production_activated':False,'network_called':False}


def _copy_dossier(source,destination):
    """Copy only referenced evidence. Validation is repeated before installation."""
    manifest=source/'manifest.json'
    require(manifest.is_file() and manifest.stat().st_size<=1_000_000,'Manifiesto ausente o demasiado grande.','release_evidence')
    dossier=json.loads(manifest.read_text(encoding='utf-8'))
    report=_artifact(source,dossier['windows'])
    windows=json.loads(report.read_text(encoding='utf-8'))
    paths={manifest.resolve(),report}
    for name in WINDOWS_CHECKS:
        for spec in windows['checks'][name]['artifacts']:
            paths.add(_artifact(source,spec))
    destination.mkdir()
    private_directory(str(destination))
    for path in sorted(paths):
        relative=path.relative_to(source.resolve())
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        with target.open('rb') as stream:
            os.fsync(stream.fileno())


def install(root,source):
    db=_ReadOnlyDatabase(root)
    policy=build_policy()
    require(policy['candidate_build'],policy['error'],'release_build')
    source=Path(source).resolve()
    require(source.is_dir(),'Selecciona la carpeta del expediente existente.','release_evidence')
    config=_configuration(db)
    result=_verify_release_dossier(db,config,source)
    require(result['ok'],result.get('error','El expediente no se ha verificado.'),'release_evidence')
    secure=db.root/'secure'
    require(secure.is_dir() and not secure.is_symlink(),'No existe el almacén local seguro.','release_evidence')
    destination=secure/'release-evidence'
    previous=secure/('release-evidence.previous-'+uid())
    # The same OS lock also prevents a simultaneous restore from replacing the
    # installation while its evidence is copied. No SQLite connection is shared.
    from .backups import _restore_lock
    with _restore_lock(db.root),tempfile.TemporaryDirectory(prefix='.release-install-',dir=secure) as temporary:
        staged=Path(temporary)/'dossier'
        _copy_dossier(source,staged)
        result=_verify_release_dossier(db,_configuration(db),staged)
        require(result['ok'],result.get('error','El expediente cambió durante la copia.'),'release_evidence')
        moved=False
        try:
            if destination.exists():
                require(destination.is_dir() and not destination.is_symlink(),'El expediente instalado no es una carpeta normal.','release_evidence')
                os.replace(destination,previous)
                moved=True
            os.replace(staged,destination)
        except Exception:
            if moved and not destination.exists():
                os.replace(previous,destination)
            raise
    return {'ok':True,'installed':True,'previous_preserved':previous.name if previous.exists() else None,
            'release_evidence':result,'production_activated':False,'network_called':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Verificar o instalar evidencias reales; no genera acuses ni activa producción.')
    parser.add_argument('--data',required=True,type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-release-evidence',action='store_true')
    mode.add_argument('--install-release-evidence',type=Path,metavar='FOLDER')
    args=parser.parse_args(argv)
    try:
        result=install(args.data,args.install_release_evidence) if args.install_release_evidence else verify(args.data)
    except (AppError,OSError,sqlite3.DatabaseError,ValueError,TypeError,KeyError) as exc:
        result={'ok':False,'error':str(exc)[:1500],'production_activated':False,'network_called':False}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
