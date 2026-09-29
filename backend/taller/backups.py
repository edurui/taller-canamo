"""Consistent SQLite online backups, AES-GCM exports and staged restore."""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import struct
import tempfile
import unicodedata
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag
from .db import SCHEMA_VERSION, dumps, uid, migrate_connection
from .validation import now
from .errors import require, AppError
from .certificates import dpapi, private_directory

MAGIC = b'CANAMO1\0'
MAX_BYTES = 8 * 1024**3
MAX_ARCHIVE_BYTES = 9 * 1024**3
MAX_FILES = 50_000
MAX_MANIFEST_BYTES = 16 * 1024**2
MAX_CENTRAL_BYTES = 32 * 1024**2
CHUNK_BYTES = 1024**2
INLINE_BYTES = 4 * 1024**2
MAX_DOWNLOADS = 32
UPLOAD_LIFETIME = timedelta(hours=24)
MAX_CONTROL_BYTES = 64_000_000
JOURNAL = '.restore-journal.json'
GUARD = '.restore-guard.json'
DEVICE = '.backup-device-id'
COMPONENTS = ('taller.sqlite3','assets','pdfs','imports','secure/certificate.dpapi',GUARD)


def _sync_directory(path):
    # Windows does not expose directory fsync through this API; files are flushed
    # before replacement on both platforms.
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path, content):
    path = Path(path)
    temporary = path.with_name(path.name+'.'+uid()+'.partial')
    try:
        with open(temporary,'xb') as output:
            os.chmod(temporary,0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary,path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _file_hash(path):
    require(path.is_file() and not path.is_symlink(), 'El archivo ya no está disponible o es un enlace.')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source, destination, expected=None):
    """Bounded-memory copy. The previous destination survives any failed write."""
    temporary = destination.with_name(destination.name+'.'+uid()+'.partial')
    digest = hashlib.sha256()
    try:
        with source.open('rb') as incoming, temporary.open('xb') as output:
            os.chmod(temporary, 0o600)
            while chunk := incoming.read(CHUNK_BYTES):
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        require(expected is None or digest.hexdigest()==expected, 'El archivo cambió durante la copia. No se ha reemplazado el destino.')
        os.replace(temporary, destination)
        _sync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _encrypt_file(source, destination, password):
    """CANAMO1 is unchanged: header, salt, nonce, GCM ciphertext, 16-byte tag."""
    require(isinstance(password, str) and 10<=len(password)<=1024, 'La contraseña de copia debe tener entre 10 y 1024 caracteres.')
    salt, nonce = os.urandom(16), os.urandom(12)
    encryptor = Cipher(algorithms.AES(key(password, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    with source.open('rb') as incoming, destination.open('xb') as output:
        os.chmod(destination, 0o600)
        output.write(MAGIC+salt+nonce)
        while chunk := incoming.read(CHUNK_BYTES):
            output.write(encryptor.update(chunk))
        output.write(encryptor.finalize())
        output.write(encryptor.tag)
        output.flush()
        os.fsync(output.fileno())


def _decrypt_file(source, destination, password):
    """Authenticate the whole stream before exposing a ZIP to any parser."""
    temporary = destination.with_name(destination.name+'.partial')
    try:
        with source.open('rb') as incoming:
            if incoming.read(len(MAGIC))!=MAGIC:
                return source
            require(isinstance(password, str) and 0<len(password)<=1024, 'Esta copia está cifrada. Introduce su contraseña.')
            require(source.stat().st_size>=52, 'Contraseña incorrecta o copia dañada.')
            salt, nonce = incoming.read(16), incoming.read(12)
            incoming.seek(-16, os.SEEK_END)
            tag = incoming.read(16)
            remaining = incoming.tell()-52
            incoming.seek(36)
            decryptor = Cipher(algorithms.AES(key(password, salt)), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(MAGIC)
            with temporary.open('xb') as output:
                os.chmod(temporary, 0o600)
                while remaining:
                    chunk = incoming.read(min(CHUNK_BYTES, remaining))
                    require(bool(chunk), 'La copia cifrada está incompleta.')
                    output.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                output.write(decryptor.finalize())
                output.flush()
                os.fsync(output.fileno())
        os.replace(temporary, destination)
        return destination
    except (InvalidTag, ValueError) as exc:
        raise AppError('Contraseña incorrecta o copia dañada.') from exc
    finally:
        temporary.unlink(missing_ok=True)


def _valid_name(name):
    require(isinstance(name, str), 'Ruta de copia no válida.')
    path = PurePosixPath(name)
    require(isinstance(name, str) and name==path.as_posix() and len(name.encode('utf-8'))<=512
            and not path.is_absolute() and '..' not in path.parts and not name.endswith('/')
            and not any(char in name for char in '\\:<>"|?*') and not any(ord(char)<32 for char in name), 'Ruta peligrosa en la copia.')
    require(all(part and part==part.rstrip(' .') and len(part.encode('utf-8'))<=255
                and not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)
                for part in path.parts), 'Nombre de archivo no válido para Windows.')
    require(name in ('taller.sqlite3', 'manifest.json')
            or (len(path.parts)==2 and path.parts[0]=='assets' and path.suffix.lower()=='.png')
            or (len(path.parts)==2 and path.parts[0]=='pdfs' and path.suffix.lower()=='.pdf')
            or (3<=len(path.parts)<=6 and path.parts[0]=='imports' and re.fullmatch(r'[0-9a-f-]{36}', path.parts[1])
                and path.suffix.lower() in ('.bin', '.json', '.jsonl', '.sqlite', '.csv', '.txt')),
            'La copia contiene un archivo no permitido. No se incluyen claves ni certificados.')


def _preflight_zip(path):
    """Bound central metadata before ZipFile allocates its directory/file list.

    PKWARE APPNOTE 4.3.12/4.3.14-16. Our V1/V2 writers produce single-volume ZIPs
    without prepended executables or ZIP64 extensible records.
    """
    size = path.stat().st_size
    require(size>=22, 'El archivo no contiene un ZIP completo.')
    with path.open('rb') as source:
        tail_size = min(size, 65535+22)
        source.seek(size-tail_size)
        tail = source.read(tail_size)
        position = tail.rfind(b'PK\x05\x06')
        require(position>=0 and position+22<=len(tail), 'No se encuentra el cierre del ZIP.')
        _, disk, directory_disk, disk_entries, entries, directory_size, directory_offset, comment = struct.unpack_from('<4s4H2IH', tail, position)
        require(position+22+comment==len(tail), 'El cierre o el comentario del ZIP está incompleto.')
        end = size-tail_size+position
        require(disk==directory_disk==0 and disk_entries==entries, 'No se admiten copias repartidas entre varios ZIP.')
        directory_end = end
        if end>=20:
            source.seek(end-20)
            locator = source.read(20)
            if locator.startswith(b'PK\x06\x07'):
                _, locator_disk, zip64_offset, disks = struct.unpack('<4sIQI', locator)
                require(locator_disk==0 and disks==1 and zip64_offset+56==end-20, 'Cierre ZIP64 no admitido.')
                source.seek(zip64_offset)
                record = source.read(56)
                require(len(record)==56, 'Cierre ZIP64 incompleto.')
                signature, length, _made, _needed, disk, directory_disk, disk_entries, entries, directory_size, directory_offset = struct.unpack('<4sQ2H2I4Q', record)
                require(signature==b'PK\x06\x06' and length==44 and disk==directory_disk==0 and disk_entries==entries,
                        'Metadatos ZIP64 incompatibles o repartidos entre varios discos.')
                directory_end = zip64_offset
        require(0<entries<=MAX_FILES, 'El ZIP anuncia demasiadas entradas o está vacío.')
        require(0<directory_size<=MAX_CENTRAL_BYTES, 'El directorio central del ZIP es demasiado grande (máximo 32 MiB).')
        require(directory_offset+directory_size==directory_end and directory_offset>=0, 'El directorio central del ZIP tiene una posición no válida.')
        source.seek(directory_offset)
        consumed, counted = 0, 0
        while consumed<directory_size:
            header = source.read(46)
            require(len(header)==46 and header[:4]==b'PK\x01\x02', 'Directorio central del ZIP dañado.')
            values = struct.unpack('<4s6H3I5H2I', header)
            name_size, extra_size, comment_size = values[10:13]
            require(0<name_size<=512 and extra_size<=4096 and comment_size<=4096 and values[13]==0,
                    'Los metadatos de una entrada ZIP superan los límites admitidos.')
            consumed += 46+name_size+extra_size+comment_size
            counted += 1
            require(consumed<=directory_size and counted<=MAX_FILES, 'El directorio central contiene demasiadas entradas o tamaños incorrectos.')
            raw_name = source.read(name_size)
            require(len(raw_name)==name_size and not any(byte<32 for byte in raw_name), 'Nombre de entrada ZIP incompleto o con caracteres de control.')
            source.seek(extra_size+comment_size, os.SEEK_CUR)
        require(counted==entries, 'El recuento real de entradas no coincide con el cierre del ZIP.')


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


@contextmanager
def _restore_lock(root):
    """An OS lock survives neither crash nor process exit; stale files are harmless."""
    path = root/'.restore-lock'
    require(not path.is_symlink(),'El bloqueo de restauración no puede ser un enlace.')
    with open(path,'a+b') as handle:
        if handle.tell()==0:
            handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise AppError('Hay otra restauración en curso. Espera a que termine.','restore_busy') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def _read_json(path, limit=MAX_CONTROL_BYTES):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=limit,
            'El archivo de control de recuperación no es válido. Conserva la carpeta de datos.','restore_review_required')
    try:
        value = json.loads(path.read_bytes())
    except (ValueError,UnicodeDecodeError) as exc:
        raise AppError('El archivo de control de recuperación está dañado. Conserva la carpeta de datos.','restore_review_required') from exc
    require(isinstance(value,dict),'El archivo de control de recuperación no es válido.','restore_review_required')
    return value


def _guard(root):
    path = root/GUARD
    if not path.exists():
        return {'version':1,'blocked':False,'known':[]}
    value = _read_json(path)
    require(value.get('version')==1 and isinstance(value.get('blocked'),bool) and isinstance(value.get('known'),list),
            'El control de restauración necesita revisión.','restore_review_required')
    return value


def assert_restore_allows_emission(db):
    require(not (db.root/JOURNAL).exists(),'Hay una restauración pendiente de recuperación. Reinicia la aplicación.','restore_review_required')
    state = _guard(db.root)
    require(not state['blocked'],state.get('message') or 'La restauración necesita revisión antes de volver a emitir.','restore_review_required')


def _recover(root):
    path = root/JOURNAL
    if not path.exists():
        return {'recovered':False,'action':'none'}
    journal = _read_json(path)
    require(journal.get('version')==1 and journal.get('phase') in ('prepared','applying','committed'),
            'El diario de restauración no es válido. Conserva la carpeta de datos.','restore_review_required')
    work_name = journal.get('work','')
    require(isinstance(work_name,str) and re.fullmatch(r'\.restore-work-[0-9a-f-]{36}',work_name),
            'La carpeta de recuperación no es válida.','restore_review_required')
    previous = journal.get('previous')
    require(isinstance(previous,dict) and set(previous) in (set(COMPONENTS),set(COMPONENTS)-{'imports'})
            and all(isinstance(value,bool) for value in previous.values()),'El diario de restauración está incompleto.','restore_review_required')
    work = root/work_name
    require(work.is_dir() and not work.is_symlink(),'Faltan los archivos necesarios para recuperar la restauración.','restore_review_required')
    if journal['phase']!='committed':
        for suffix in ('-wal','-shm'):
            Path(str(root/'taller.sqlite3')+suffix).unlink(missing_ok=True)
        for name in (name for name in reversed(COMPONENTS) if name in previous):
            saved, destination = work/'old'/name, root/name
            require(not saved.is_symlink() and not destination.parent.is_symlink(),'Ruta de recuperación no permitida.','restore_review_required')
            if saved.exists():
                _remove(destination)
                destination.parent.mkdir(parents=True,exist_ok=True)
                os.replace(saved,destination)
                _sync_directory(destination.parent)
            elif not previous[name]:
                _remove(destination)
        action = 'rolled_back'
    else:
        action = 'committed'
    # Remove the marker last. A second recovery can safely repeat these steps.
    # Keep an empty work directory until the marker is gone for that repeat.
    for child in work.iterdir():
        _remove(child)
    path.unlink()
    _sync_directory(root)
    work.rmdir()
    return {'recovered':True,'action':action,'safety_copy':journal.get('safety_copy','')}


def recover_pending_restore(root):
    """Run before Database(root), including its schema creation/migrations."""
    root = Path(root).resolve()
    if not root.exists():
        return {'recovered':False,'action':'none'}
    with _restore_lock(root):
        return _recover(root)


def _anchor(conn):
    config = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
    head = conn.execute('SELECT seq,hash FROM fiscal_records ORDER BY seq DESC LIMIT 1').fetchone()
    return {'installation_id':config['fiscal']['installation_id'],
            'head':dict(head) if head else None,
            'series':[dict(row) for row in conn.execute('SELECT id,next_number,used FROM series WHERE used>0')],
            'outbox':[{'record_id':row['record_id'],'attempts':row['attempts'],'status':row['status'],
                       'response_hash':hashlib.sha256((row['response']+'|'+row['csv']).encode()).hexdigest()}
                      for row in conn.execute('SELECT record_id,attempts,status,response,csv FROM fiscal_outbox')]}


def _covers(conn, anchor):
    current = _anchor(conn)
    if current['installation_id']!=anchor['installation_id']:
        return not anchor.get('head') and not anchor.get('series')
    if anchor.get('head'):
        record = conn.execute('SELECT hash FROM fiscal_records WHERE seq=?',(anchor['head']['seq'],)).fetchone()
        if not record or record['hash']!=anchor['head']['hash']:
            return False
    for old in anchor.get('series',[]):
        present = conn.execute('SELECT next_number,used FROM series WHERE id=?',(old['id'],)).fetchone()
        if not present or present['next_number']<old['next_number'] or present['used']<old['used']:
            return False
    present = {row['record_id']:row for row in current['outbox']}
    for old in anchor.get('outbox',[]):
        latest = present.get(old['record_id'])
        if not latest or latest['attempts']<old['attempts']:
            return False
        if latest['attempts']==old['attempts'] and (latest['status']!=old['status'] or latest['response_hash']!=old['response_hash']):
            return False
    return True


def _inspect_database(path, expected_schema=None, migrate=False):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA trusted_schema=OFF')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        require(1<=version<=SCHEMA_VERSION and (expected_schema is None or version==expected_schema),
                'Esquema de base de datos incompatible o distinto del manifiesto.')
        require([row[0] for row in conn.execute('PRAGMA integrity_check')]==['ok'],'La base de datos de la copia está dañada.')
        require(not conn.execute('PRAGMA foreign_key_check').fetchall(),'La copia contiene relaciones rotas.')
        previous = ''
        for row in conn.execute('SELECT * FROM audit ORDER BY seq'):
            expected = hashlib.sha256((previous+'|'+row['action']+'|'+row['entity_id']+'|'+row['detail']+'|'+row['created_at']).encode()).hexdigest()
            require(row['previous_hash']==previous and row['hash']==expected,'La auditoría de la copia está dañada.')
            previous = row['hash']
        from .fiscal import validate_stored_record
        heads = {}
        for row in conn.execute('SELECT * FROM fiscal_records ORDER BY seq'):
            payload = validate_stored_record(row, heads.get(row['environment']))
            heads[row['environment']] = {**payload, 'hash': row['hash']}
        from .b2b import check_storage
        check_storage(conn)
        migration = migrate_connection(conn) if migrate else {'from_version':version,'to_version':version,'applied':[]}
        if migration['applied']:
            check_storage(conn)
        counts = {table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
                  for table in ('customers','vehicles','documents','fiscal_records','events')}
        return {'counts':counts,'anchor':_anchor(conn),'migration':migration}
    except sqlite3.DatabaseError as exc:
        raise AppError('La copia no contiene una base de datos válida de El Cáñamo.') from exc
    finally:
        conn.close()


def key(password,salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=600000).derive(password.encode('utf-8'))


def encrypt(data,password):
    require(len(password)>=10,'La contrase\u00f1a de copia debe tener al menos 10 caracteres.')
    salt,nonce = os.urandom(16),os.urandom(12)
    return MAGIC+salt+nonce+AESGCM(key(password,salt)).encrypt(nonce,data,MAGIC)


def decrypt(data,password):
    if not data.startswith(MAGIC): return data
    require(password,'Esta copia est\u00e1 cifrada. Introduce su contrase\u00f1a.')
    try:
        salt,nonce,encrypted = data[8:24],data[24:36],data[36:]
        return AESGCM(key(password,salt)).decrypt(nonce,encrypted,MAGIC)
    except (InvalidTag,ValueError) as exc:
        raise AppError('Contrase\u00f1a incorrecta o copia da\u00f1ada.') from exc


class Backups:
    def __init__(self,db,settings):
        self.db,self.settings = db,settings
        self.previews = {}
        self.downloads = {}
        self.export_root = db.root/'.file-exports'
        require(not self.export_root.is_symlink(), 'La carpeta de exportaciones no puede ser un enlace.')
        self.export_root.mkdir(mode=0o700, exist_ok=True)
        private_directory(str(self.export_root))
        self.upload_root = db.root/'.backup-uploads'
        require(not self.upload_root.is_symlink(), 'La carpeta de cargas no puede ser un enlace.')
        self.upload_root.mkdir(mode=0o700, exist_ok=True)
        private_directory(str(self.upload_root))
        # A killed copy/preview may leave private working files. Only our own
        # expired scratch prefixes are removed; restore journals/work are handled
        # separately by recover_pending_restore before Database is opened.
        expired = datetime.now(timezone.utc).timestamp()-UPLOAD_LIFETIME.total_seconds()
        for path in db.root.iterdir():
            if re.fullmatch(r'\.(?:backup-(?:work|input|check)|restore-preview|portable-work)-[A-Za-z0-9_-]{6,32}', path.name) and path.lstat().st_mtime<expired:
                _remove(path)
        for path in self.export_root.iterdir():
            if re.fullmatch(r'[a-f0-9-]{36}\.(?:zip|csv)', path.name) and path.lstat().st_mtime<expired:
                _remove(path)
        if not (db.root/DEVICE).exists():
            _atomic_write(db.root/DEVICE,uid().encode())
        require(not (db.root/DEVICE).is_symlink(),'La identidad local de copias no puede ser un enlace.')
        self.device_id = (db.root/DEVICE).read_text().strip()

    def create(self,password='',automatic=False):
        return self._create(password,automatic)

    def _create(self,password='',automatic=False,transfer=None,backup_name=None,export=True):
        require(isinstance(password, str) and (not password or 10<=len(password)<=1024), 'La contraseña de copia debe tener entre 10 y 1024 caracteres.')
        with self.db.lock, tempfile.TemporaryDirectory(prefix='.backup-work-', dir=self.db.root) as temp:
            require(not (self.db.root/JOURNAL).exists(),'Completa la recuperación pendiente antes de crear otra copia.','restore_review_required')
            private_directory(temp)
            target = Path(temp)/'taller.sqlite3'
            with self.db.read() as source:
                destination = sqlite3.connect(target)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
            _inspect_database(target)
            # Never include secure/, certificate/password, application binaries, or other backups.
            entries = {'taller.sqlite3':target}
            total_bytes = target.stat().st_size
            for folder in ('assets','pdfs','imports'):
                require(not (self.db.root/folder).is_symlink(),'La carpeta de recursos no puede ser un enlace.')
                if not (self.db.root/folder).exists():
                    continue
                paths = (self.db.root/folder).rglob('*') if folder=='imports' else (self.db.root/folder).iterdir()
                for p in paths:
                    require(not p.is_symlink(),'Hay un enlace en los recursos de la copia.')
                    if folder=='imports' and p.is_dir():
                        continue
                    if folder=='imports' and p.name.startswith('simulation.'):
                        continue  # Disposable copy of SQLite, rebuilt by the import wizard.
                    require(p.is_file() and not p.is_symlink(),'Hay un recurso que no es un archivo regular. Revisa '+folder+'.')
                    require(total_bytes+p.stat().st_size<=MAX_BYTES,'Esta copia supera el límite de 8 GiB descomprimidos; no se ha truncado ningún archivo.')
                    name = p.relative_to(self.db.root).as_posix()
                    _valid_name(name)
                    entries[name] = p
                    total_bytes += p.stat().st_size
                    require(len(entries)<MAX_FILES, 'La copia supera 50.000 archivos; no se ha truncado nada.')
            require(len(entries)<MAX_FILES and total_bytes<=MAX_BYTES,'Esta copia supera los límites de 8 GiB o 50.000 archivos; no se ha truncado nada.')
            require(len({unicodedata.normalize('NFC', name).casefold() for name in entries})==len(entries), 'Hay nombres duplicados para Windows en los recursos.')
            require(shutil.disk_usage(self.db.root).free >= total_bytes * (2 if password else 1) + 16*1024**2,
                    'No hay espacio libre suficiente para preparar la copia completa. Libera espacio o traslada copias antiguas.')
            archive_path = Path(temp)/'archive.zip'
            digests = {}
            actual_total = 0
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                os.chmod(archive_path, 0o600)
                for name, path in entries.items():
                    digest, size = hashlib.sha256(), 0
                    before = path.stat()
                    with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
                        while chunk := source.read(CHUNK_BYTES):
                            size += len(chunk)
                            actual_total += len(chunk)
                            require(actual_total<=MAX_BYTES, 'Los recursos crecieron por encima de 8 GiB. No se ha guardado una copia parcial.')
                            output.write(chunk)
                            digest.update(chunk)
                    after = path.stat()
                    require(size==before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns,
                            'Un recurso cambió durante la copia. Vuelve a intentarlo.')
                    digests[name] = digest.hexdigest()
                self._validate_resources(Path(temp), digests)
                manifest = {'format':'canamo-backup-v2','schema':SCHEMA_VERSION,'created_at':now(),
                            'files':digests,'certificate_included':False,'device_id':self.device_id,'transfer':transfer}
                encoded = dumps(manifest).encode('utf-8')
                require(len(encoded)<=MAX_MANIFEST_BYTES and actual_total+len(encoded)<=MAX_BYTES, 'El manifiesto o el contenido de la copia supera los límites.')
                archive.writestr('manifest.json', encoded)
            with archive_path.open('rb') as handle:
                os.fsync(handle.fileno())
            if password:
                encrypted = Path(temp)/'encrypted.canamo'
                _encrypt_file(archive_path, encrypted, password)
                archive_path = encrypted
            require(archive_path.stat().st_size<=MAX_ARCHIVE_BYTES, 'El archivo de copia supera el límite de transporte de 9 GiB.')
            digest = _file_hash(archive_path)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            name = backup_name or ('auto-' if automatic else 'copia-')+timestamp+'.canamo'
            destination = self.db.root/'backups'/name
            if transfer:
                state = _guard(self.db.root)
                state['export_sha256'] = digest
                _atomic_write(self.db.root/GUARD,dumps(state).encode())
            os.replace(archive_path, destination)
            _sync_directory(destination.parent)
            external = self.settings.get()['backup']['external_directory']
            warning = ''
            if external:
                try:
                    path = Path(external)
                    require(not path.is_symlink() and not path.resolve().is_relative_to(self.db.root),'La segunda copia debe estar fuera de la carpeta de trabajo.')
                    path.mkdir(parents=True,exist_ok=True)
                    _atomic_copy(destination, path/name, digest)
                except (OSError,AppError):
                    warning = 'La copia local est\u00e1 guardada, pero la segunda ubicaci\u00f3n no est\u00e1 disponible.'
            self.settings.internal_update('backup','last_success',now())
            self._retention()
            with self.db.transaction() as conn:
                self.db.audit(conn,'backup.create',name,{'encrypted':bool(password),'external_error':bool(warning)})
            result = {'name':name,'mime':'application/octet-stream','encrypted':bool(password),'warning':warning,
                      'bytes':destination.stat().st_size,'sha256':digest}
            return {**result, **self._download_result(destination, digest)} if export and not automatic else result

    @staticmethod
    def _validate_resources(folder,entries):
        with closing(sqlite3.connect(folder/'taller.sqlite3')) as conn:
            config = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
            logos = {config['billing'].get('logo_id')}
            for (payload,) in conn.execute('SELECT payload FROM documents'):
                logos.add(json.loads(payload).get('branding',{}).get('logo_id'))
            require(all('assets/'+logo in entries for logo in logos if logo),'Falta una imagen referenciada por los documentos. La copia no está completa.')
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_batches'").fetchone():
                for identifier,digest in conn.execute('SELECT id,source_digest FROM import_batches'):
                    prefix = 'imports/'+identifier+'/'
                    require(all(prefix+name in entries for name in ('source.bin','upload.json','diagnostic.json','staging.sqlite')),
                            'Faltan originales o diagnósticos de una importación. La copia no está completa.')
                    content = entries[prefix+'source.bin']
                    actual = hashlib.sha256(content).hexdigest() if isinstance(content, bytes) else content
                    require(actual==digest,'El original de una importación no coincide con su huella guardada.')

    def _drop_download(self, token):
        item = self.downloads.pop(token, None)
        if item and item.get('temporary') and not self.export_root.is_symlink() and item['path'].parent==self.export_root:
            item['path'].unlink(missing_ok=True)

    def _expire_downloads(self):
        stamp = datetime.now(timezone.utc)
        for token, item in list(self.downloads.items()):
            if item['expires']<=stamp:
                self._drop_download(token)
        active = {item['path'] for item in self.downloads.values() if item.get('temporary')}
        if not self.export_root.is_symlink():
            for path in self.export_root.iterdir():
                if (path not in active and re.fullmatch(r'[a-f0-9-]{36}\.(?:zip|csv)', path.name)
                        and path.lstat().st_mtime<stamp.timestamp()-3600):
                    _remove(path)

    def register_export(self, path, name, mime):
        """Internal handoff for portable ZIP/CSV; never accepts client paths."""
        require(isinstance(name, str) and Path(name).name==name and Path(name).suffix in ('.zip', '.csv'), 'Nombre de exportación no válido.')
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(self.db.root.resolve()), 'Origen de exportación no válido.')
        require(not self.export_root.is_symlink(), 'La carpeta de exportaciones no puede ser un enlace.')
        size = path.stat().st_size
        require(size<=MAX_ARCHIVE_BYTES, 'La exportación supera el límite de transporte de 9 GiB.')
        digest = _file_hash(path)
        with path.open('rb') as source:
            os.fsync(source.fileno())
        target = self.export_root/(uid()+Path(name).suffix)
        os.replace(path, target)
        _sync_directory(self.export_root)
        try:
            return {'name':name, 'mime':mime, 'bytes':size, 'sha256':digest,
                    **self._download_result(target, digest, temporary=True)}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def _download_result(self, path, digest, temporary=False):
        stamp = datetime.now(timezone.utc)
        self._expire_downloads()
        # Capabilities grant reads of an already selected output, never a path.
        # Revocation has no effect on the retained local backup.
        while len(self.downloads)>=MAX_DOWNLOADS:
            self._drop_download(next(iter(self.downloads)))
        token = secrets.token_urlsafe(32)
        details = path.stat()
        self.downloads[token] = {'path':path, 'sha256':digest,
                'temporary':temporary,
                'identity':(details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns),
                'expires':stamp+timedelta(hours=1)}
        result = {'capability':token, 'chunk_bytes':CHUNK_BYTES}
        if details.st_size<=INLINE_BYTES:
            # V1 RPC clients/tests remain compatible for explicitly small files.
            with path.open('rb') as source:
                result['content'] = base64.b64encode(source.read(INLINE_BYTES+1)).decode()
        return result

    def download_chunk(self, capability, offset, length=CHUNK_BYTES):
        require(isinstance(capability, str), 'Permiso de descarga no válido.')
        require(type(offset) is int and offset>=0 and type(length) is int and 0<length<=CHUNK_BYTES,
                'Posición o tamaño del bloque no válido.')
        with self.db.lock:
            item = self.downloads.get(capability)
            require(item and item['expires']>datetime.now(timezone.utc), 'El permiso de descarga ha caducado. Vuelve a preparar el archivo.', 'not_found')
            path = item['path']
            require(path.is_file() and not path.is_symlink(), 'La copia local ya no está disponible.')
            details = path.stat()
            require((details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)==item['identity'],
                    'El archivo cambió después de prepararlo. Vuelve a seleccionar la copia.')
            require(offset<=details.st_size, 'Posición fuera del archivo.')
            with path.open('rb') as source:
                source.seek(offset)
                chunk = source.read(length)
            item['expires'] = datetime.now(timezone.utc)+timedelta(hours=1)
            return {'content':base64.b64encode(chunk).decode(), 'offset':offset, 'bytes':len(chunk),
                    'total_bytes':details.st_size, 'eof':offset+len(chunk)==details.st_size,
                    'sha256':hashlib.sha256(chunk).hexdigest()}

    def release_download(self, capability):
        require(isinstance(capability, str), 'Permiso de descarga no válido.')
        with self.db.lock:
            self._drop_download(capability)
        return {'released':True}

    def _upload_folder(self, upload_id):
        require(isinstance(upload_id, str) and re.fullmatch(r'[a-f0-9]{64}', upload_id), 'Identificador de carga no válido.')
        require(not self.upload_root.is_symlink(), 'La carpeta de cargas no puede ser un enlace.')
        folder = self.upload_root/upload_id
        require(folder.is_dir() and not folder.is_symlink(), 'La carga no está disponible. Selecciona de nuevo la copia.', 'not_found')
        return folder

    def _clean_uploads(self):
        expiry = datetime.now(timezone.utc).timestamp()-UPLOAD_LIFETIME.total_seconds()
        for folder in self.upload_root.iterdir():
            require(not folder.is_symlink(), 'La carpeta de cargas contiene un enlace.')
            if re.fullmatch(r'[a-f0-9]{64}', folder.name) and folder.stat().st_mtime<expiry:
                _remove(folder)

    def upload_start(self, name, total_bytes):
        require(isinstance(name, str) and 0<len(name)<=240 and '/' not in name and '\\' not in name
                and not any(ord(char)<32 for char in name), 'Nombre de copia no válido.')
        require(type(total_bytes) is int and 0<total_bytes<=MAX_ARCHIVE_BYTES, 'La copia debe ocupar entre 1 byte y 9 GiB.')
        with self.db.lock:
            self._clean_uploads()
            active = [folder for folder in self.upload_root.iterdir() if folder.is_dir()]
            require(len(active)<3, 'Ya hay tres cargas de copia pendientes. Cancela una o retoma su carga.')
            outstanding = 0
            for folder in active:
                meta = _read_json(folder/'upload.json', 16_384)
                outstanding += max(0, meta['total_bytes']-meta['offset'])
            require(shutil.disk_usage(self.upload_root).free>=total_bytes+outstanding+16*1024**2,
                    'No hay espacio libre suficiente para cargar esta copia completa.')
            identifier = secrets.token_hex(32)
            folder = self.upload_root/identifier
            folder.mkdir(mode=0o700)
            private_directory(str(folder))
            meta = {'version':1, 'name':name, 'total_bytes':total_bytes, 'offset':0, 'updated_at':now()}
            try:
                _atomic_write(folder/'source.canamo', b'')
                _atomic_write(folder/'upload.json', dumps(meta).encode())
            except Exception:
                shutil.rmtree(folder, ignore_errors=True)
                raise
            return {'upload_id':identifier, **meta, 'chunk_bytes':CHUNK_BYTES}

    def upload_status(self, upload_id):
        with self.db.lock:
            folder = self._upload_folder(upload_id)
            meta = _read_json(folder/'upload.json', 16_384)
            require(meta.get('version')==1 and type(meta.get('total_bytes')) is int and 0<meta['total_bytes']<=MAX_ARCHIVE_BYTES
                    and type(meta.get('offset')) is int and 0<=meta['offset']<=meta['total_bytes'], 'Metadatos de carga dañados. Cancela esta carga y vuelve a seleccionarla.')
            require(datetime.fromisoformat(meta['updated_at'])+UPLOAD_LIFETIME>datetime.now(timezone.utc),
                    'La carga ha caducado. Cancélala y selecciona de nuevo el archivo.', 'not_found')
            path = folder/'source.canamo'
            require(path.is_file() and not path.is_symlink() and path.stat().st_size>=meta['offset'], 'La carga está incompleta o ha cambiado.')
            # Crash between appending bytes and committing upload.json: only
            # acknowledged bytes survive. A repeated last chunk is safe.
            if path.stat().st_size>meta['offset']:
                with path.open('r+b') as output:
                    output.truncate(meta['offset'])
                    output.flush()
                    os.fsync(output.fileno())
            return {'upload_id':upload_id, **meta, 'chunk_bytes':CHUNK_BYTES}

    def upload_list(self):
        with self.db.lock:
            self._clean_uploads()
            items = []
            for folder in sorted(self.upload_root.iterdir()):
                if re.fullmatch(r'[a-f0-9]{64}', folder.name) and folder.is_dir():
                    try:
                        items.append(self.upload_status(folder.name))
                    except (AppError, ValueError, KeyError):
                        items.append({'upload_id':folder.name, 'name':'Carga incompleta o dañada', 'invalid':True})
            return items

    def upload_chunk(self, upload_id, offset, content):
        require(isinstance(content, str) and len(content)<=4*((CHUNK_BYTES+2)//3), 'Bloque de copia demasiado grande.')
        try:
            chunk = base64.b64decode(content, validate=True)
        except (ValueError, TypeError) as exc:
            raise AppError('Bloque de copia no válido.') from exc
        require(0<len(chunk)<=CHUNK_BYTES and type(offset) is int and offset>=0, 'Tamaño o posición de bloque no válido.')
        with self.db.lock:
            meta = self.upload_status(upload_id)
            require(offset<=meta['offset'] and offset+len(chunk)<=meta['total_bytes'], 'Posición de bloque incorrecta. Consulta el progreso antes de repetir.', 'conflict')
            folder = self._upload_folder(upload_id)
            with (folder/'source.canamo').open('r+b') as output:
                output.seek(offset)
                if offset<meta['offset']:
                    require(offset+len(chunk)<=meta['offset'] and output.read(len(chunk))==chunk,
                            'El bloque repetido no coincide con la copia recibida.', 'conflict')
                else:
                    output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                    meta['offset'] += len(chunk)
            meta = {key:value for key,value in meta.items() if key not in ('upload_id', 'chunk_bytes')}
            meta['updated_at'] = now()
            _atomic_write(folder/'upload.json', dumps(meta).encode())
            return {'upload_id':upload_id, 'offset':meta['offset'], 'total_bytes':meta['total_bytes'], 'chunk_bytes':CHUNK_BYTES}

    def upload_finish(self, upload_id, password=''):
        with self.db.lock:
            meta = self.upload_status(upload_id)
            require(meta['offset']==meta['total_bytes'], 'Termina de cargar todos los bloques antes de comprobar la copia.')
            result = self._preview_path(self._upload_folder(upload_id)/'source.canamo', password)
            self.upload_cancel(upload_id)
            return result

    def upload_cancel(self, upload_id):
        with self.db.lock:
            require(isinstance(upload_id, str) and re.fullmatch(r'[a-f0-9]{64}', upload_id), 'Identificador de carga no válido.')
            require(not self.upload_root.is_symlink(), 'La carpeta de cargas no puede ser un enlace.')
            if not (self.upload_root/upload_id).exists():
                return {'cancelled':True}
            folder = self._upload_folder(upload_id)
            shutil.rmtree(folder)
            _sync_directory(self.upload_root)
        return {'cancelled':True}

    def _automatic_password(self):
        secret = self.db.root/'secure'/'backup-password.dpapi'
        require(not secret.is_symlink() and (not secret.exists() or secret.stat().st_size<=16_384), 'El archivo protegido de contraseña necesita revisión.')
        return dpapi(secret.read_bytes(),decrypt=True).decode() if secret.exists() else ''

    def _retention(self):
        files = sorted((self.db.root/'backups').glob('auto-*.canamo'),reverse=True)
        policy = self.settings.get()['backup'].get('retention',{'daily':7,'weekly':4,'monthly':12})
        require(isinstance(policy,dict) and set(policy)=={'daily','weekly','monthly'}
                and all(isinstance(value,int) and not isinstance(value,bool) and 0<=value<=365 for value in policy.values())
                and sum(policy.values())>0,'Revisa la retención de copias antes de aplicar la limpieza automática.')
        daily,weekly,monthly,set_keep = set(),set(),set(),set()
        for file in files:
            try: stamp = datetime.strptime(file.name[5:13],'%Y%m%d')
            except ValueError: continue
            day,week,month = stamp.strftime('%Y-%m-%d'),stamp.strftime('%G-W%V'),stamp.strftime('%Y-%m')
            if (len(daily)<policy['daily'] and day not in daily) or (len(weekly)<policy['weekly'] and week not in weekly) or (len(monthly)<policy['monthly'] and month not in monthly):
                set_keep.add(file);daily.add(day);weekly.add(week);monthly.add(month)
        for file in files:
            if file not in set_keep: file.unlink(missing_ok=True)

    def configure_retention(self,daily=7,weekly=4,monthly=12):
        policy = {'daily':daily,'weekly':weekly,'monthly':monthly}
        require(all(isinstance(value,int) and not isinstance(value,bool) and 0<=value<=365 for value in policy.values())
                and sum(policy.values())>0,'Conserva al menos una copia automática; cada periodo admite entre 0 y 365.')
        with self.db.transaction() as conn:
            config = self.settings.get(conn)
            config['backup']['retention'] = policy
            conn.execute('UPDATE settings SET data=? WHERE id=1',(dumps(config),))
            self.db.audit(conn,'backup.retention','1',policy)
        return policy

    def automatic(self,force=False):
        self._expire_downloads()
        config = self.settings.get()['backup']
        if not force and (not config['daily'] or config['last_success'][:10]==now()[:10]): return {'status':'not_due'}
        password = self._automatic_password()
        result = self.create(password,automatic=True)
        result.pop('content',None)
        return result

    def password(self,value):
        require(isinstance(value, str) and len(value)<=1024, 'La contraseña debe tener como máximo 1024 caracteres.')
        path = self.db.root/'secure'/'backup-password.dpapi'
        if value:
            require(len(value)>=10,'La contrase\u00f1a debe tener al menos 10 caracteres.')
            _atomic_write(path,dpapi(value.encode()))
        else:
            path.unlink(missing_ok=True)
        return {'configured':bool(value)}

    def list(self):
        return [{'name':p.name,'bytes':p.stat().st_size,'created_at':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in sorted((self.db.root/'backups').glob('*.canamo'),reverse=True)[:100]]

    def recovery_status(self):
        state = _guard(self.db.root)
        pending = (self.db.root/JOURNAL).exists()
        return {'blocked':state['blocked'] or pending,'pending_journal':pending,'reason':state.get('reason',''),'message':state.get('message',''),
                'transfer_ready':state.get('reason')=='transfer_ready','transfer_id':state.get('transfer_id'),
                'expected_heads':[anchor['head'] for anchor in state['known'] if anchor.get('head')]}

    def prepare_transfer(self,password=''):
        with self.db.lock:
            previous = _guard(self.db.root)
            if previous.get('reason')=='transfer_source':
                name = previous.get('transfer_backup','')
                require(isinstance(name,str) and re.fullmatch(r'traslado-[0-9a-f-]{36}\.canamo',name),
                        'No se encuentra el paquete de traslado preparado. Conserva las copias y el equipo inactivo.','restore_review_required')
                path = self.db.root/'backups'/name
                require(path.is_file() and not path.is_symlink(),'El paquete preparado ya no está en la carpeta de copias. Conserva el equipo inactivo.','restore_review_required')
                digest = _file_hash(path)
                require(digest==previous.get('export_sha256'),'El paquete preparado ha cambiado. Conserva el equipo inactivo.','restore_review_required')
                with path.open('rb') as source:
                    encrypted = source.read(len(MAGIC))==MAGIC
                return {'name':name,'mime':'application/octet-stream',**self._download_result(path, digest),
                        'bytes':path.stat().st_size,'sha256':digest,'encrypted':encrypted,
                        'warning':'Se entrega el mismo paquete preparado; conserva su contraseña original.','source_blocked':True,'transfer_id':previous['transfer_id'],'repeated':True}
            assert_restore_allows_emission(self.db)
            ticket = {'id':uid(),'source_device':self.device_id,'created_at':now()}
            backup_name = 'traslado-'+ticket['id']+'.canamo'
            with self.db.read() as conn:
                source = _anchor(conn)
            state = {'version':1,'blocked':True,'known':[source],'reason':'transfer_source','transfer_id':ticket['id'],'transfer_backup':backup_name,
                     'message':'Este equipo ha quedado inactivo para emisión y envíos fiscales tras preparar el traslado. Activa únicamente el equipo de destino.'}
            _atomic_write(self.db.root/GUARD,dumps(state).encode())
            try:
                result = self._create(password or self._automatic_password(),False,ticket,backup_name)
            except Exception:
                # Once a transferable file exists the source must stay retired,
                # even if a later settings/audit write or save dialog fails.
                if not (self.db.root/'backups'/backup_name).exists():
                    _atomic_write(self.db.root/GUARD,dumps(previous).encode())
                raise
            return {**result,'source_blocked':True,'transfer_id':ticket['id']}

    def activate_transfer(self,confirmation):
        require(confirmation=='ACTIVAR SOLO ESTE EQUIPO','Escribe ACTIVAR SOLO ESTE EQUIPO después de retirar el equipo anterior.')
        with self.db.lock:
            state = _guard(self.db.root)
            require(state.get('reason')=='transfer_ready' and state.get('transfer_id'),'Esta copia no procede de un traslado preparado o le falta historial conocido.','restore_review_required')
            with self.db.read() as conn:
                require(all(_covers(conn,anchor) for anchor in state['known']),'Falta historial conocido. Restaura una copia completa antes de activar.','restore_review_required')
            state.update(blocked=False,reason='transfer_active',message='',activated_at=now())
            _atomic_write(self.db.root/GUARD,dumps(state).encode())
            with self.db.transaction() as conn:
                self.db.audit(conn,'backup.transfer.activate',state['transfer_id'],{'device_id':self.device_id})
            return self.recovery_status()

    def preview(self,content,password=''):
        require(isinstance(content,str) and len(content)<=4*((INLINE_BYTES+2)//3),
                'Para copias de más de 4 MiB utiliza la carga por bloques; no se ha cargado todo el archivo en memoria.')
        try:
            data = base64.b64decode(content,validate=True)
        except ValueError as exc:
            raise AppError('El archivo no es una copia de El C\u00e1\u00f1amo.') from exc
        require(len(data)<=INLINE_BYTES, 'Utiliza la carga por bloques para esta copia.')
        with tempfile.TemporaryDirectory(prefix='.backup-input-', dir=self.db.root) as temporary:
            private_directory(temporary)
            path = Path(temporary)/'input.canamo'
            _atomic_write(path, data)
            return self._preview_path(path, password)

    def _preview_path(self, path, password=''):
        require(isinstance(password, str) and len(password)<=1024, 'Contraseña de copia no válida.')
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_ARCHIVE_BYTES, 'Copia demasiado grande o formato incorrecto.')
        with tempfile.TemporaryDirectory(prefix='.backup-check-', dir=self.db.root) as temporary:
            private_directory(temporary)
            with path.open('rb') as incoming:
                encrypted = incoming.read(len(MAGIC))==MAGIC
            if encrypted:
                require(shutil.disk_usage(self.db.root).free>=path.stat().st_size+16*1024**2, 'No hay espacio libre suficiente para autenticar la copia cifrada.')
            archive_path = _decrypt_file(path, Path(temporary)/'authenticated.zip', password)
            try:
                _preflight_zip(archive_path)
                with zipfile.ZipFile(archive_path) as archive:
                    return self._preview_archive(archive, password)
            except (zipfile.BadZipFile, ValueError, OSError) as exc:
                raise AppError('El archivo no contiene una copia completa y válida de El Cáñamo.') from exc

    def _preview_archive(self, archive, password):
        folder = None
        try:
            names = archive.namelist()
            canonical = {unicodedata.normalize('NFC',name).casefold() for name in names}
            require(len(names)==len(canonical) and len(names)<=MAX_FILES,'Copia con entradas duplicadas o excesivas para Windows.')
            total_bytes = sum(info.file_size for info in archive.infolist())
            require(total_bytes<=MAX_BYTES, 'La copia descomprimida es demasiado grande: supera el límite de 8 GiB.')
            require(shutil.disk_usage(self.db.root).free>=total_bytes+16*1024**2, 'No hay espacio libre suficiente para comprobar todos los archivos de la copia.')
            for info in archive.infolist():
                _valid_name(info.filename)
                mode = stat.S_IFMT(info.external_attr >> 16)
                require(mode in (0,stat.S_IFREG) and not info.flag_bits & 1,'La copia contiene enlaces, dispositivos o cifrado ZIP no admitido.')
                require(info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'La compresión del ZIP no está admitida.')
            require('manifest.json' in names and 'taller.sqlite3' in names,'Copia incompleta.')
            require(archive.getinfo('manifest.json').file_size<=MAX_MANIFEST_BYTES,'El manifiesto es demasiado grande.')
            manifest = json.loads(archive.read('manifest.json'))
            require(isinstance(manifest,dict) and isinstance(manifest.get('schema'),int) and not isinstance(manifest['schema'],bool)
                    and 1<=manifest['schema']<=SCHEMA_VERSION,'Versión de base de datos incompatible.')
            require(isinstance(manifest.get('files'),dict) and set(manifest['files'])==set(names)-{'manifest.json'},'El manifiesto no coincide con los archivos.')
            require(isinstance(manifest.get('created_at'),str),'Falta la fecha de creación de la copia.')
            folder = Path(tempfile.mkdtemp(prefix='.restore-preview-', dir=self.db.root))
            private_directory(str(folder))
            extracted_bytes = 0
            for name,digest in manifest['files'].items():
                require(isinstance(digest,str) and re.fullmatch(r'[a-f0-9]{64}',digest),'Huella de archivo no válida.')
                destination = folder/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                actual, size = hashlib.sha256(), 0
                with archive.open(name) as source, destination.open('xb') as output:
                    os.chmod(destination, 0o600)
                    while chunk := source.read(CHUNK_BYTES):
                        size += len(chunk)
                        extracted_bytes += len(chunk)
                        require(size<=archive.getinfo(name).file_size and extracted_bytes<=MAX_BYTES,
                                'El contenido descomprimido excede los tamaños declarados.')
                        output.write(chunk)
                        actual.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                require(size==archive.getinfo(name).file_size and actual.hexdigest()==digest,'La copia ha sido alterada o está dañada.')
            self._validate_resources(folder,manifest['files'])
            inspection = _inspect_database(folder/'taller.sqlite3',manifest['schema'],migrate=True)
            # Keep a separate fingerprint after migration; the original manifest
            # has already been checked and must not be relabelled as newly signed.
            prepared_files = dict(manifest['files'])
            prepared_files['taller.sqlite3'] = _file_hash(folder/'taller.sqlite3')
            token = uid()
            for stale,item in list(self.previews.items()):
                if item['expires']<=datetime.now(timezone.utc) or len(self.previews)>=3:
                    shutil.rmtree(item['folder'],ignore_errors=True)
                    del self.previews[stale]
            self.previews[token] = {'folder':folder,'expires':datetime.now(timezone.utc)+timedelta(minutes=15),'manifest':manifest,
                                    'prepared_files':prepared_files,'password':password,'inspection':inspection}
            return {'token':token,'counts':inspection['counts'],'created_at':manifest['created_at'],'migration':inspection['migration'],
                    'warning':'Se reemplazarán la base, imágenes, PDF e importaciones. Se creará una copia previa. Una copia antigua o de otro equipo puede exigir recuperar el historial o completar el traslado antes de emitir.'}
        except (ValueError,UnicodeDecodeError,zipfile.BadZipFile,KeyError,sqlite3.DatabaseError) as exc:
            if folder: shutil.rmtree(folder,ignore_errors=True)
            raise AppError('El archivo no contiene una copia completa y válida de El Cáñamo.') from exc
        except Exception:
            if folder: shutil.rmtree(folder,ignore_errors=True)
            raise

    def _restore_state(self, preview, restored_path):
        previous = _guard(self.db.root)
        with self.db.read() as conn:
            known = [anchor for anchor in previous['known'] if not _covers(conn,anchor)]
            known.append(_anchor(conn))
        with closing(sqlite3.connect(restored_path)) as conn:
            conn.row_factory = sqlite3.Row
            missing = [anchor for anchor in known if not _covers(conn,anchor)]
            target = _anchor(conn)
        state = {'version':1,'blocked':False,'reason':'','message':'','known':missing+[target],'restored_at':now()}
        manifest = preview['manifest']
        ticket = manifest.get('transfer')
        prepared = isinstance(ticket,dict) and isinstance(ticket.get('id'),str) and bool(re.fullmatch(r'[0-9a-f-]{36}',ticket['id']))
        return_transfer = prepared and ticket['id']!=previous.get('transfer_id') and manifest.get('device_id')!=self.device_id
        if previous.get('reason')=='transfer_source' and not return_transfer:
            state.update(blocked=True,reason='transfer_source',message=previous['message'],transfer_id=previous.get('transfer_id'),
                         transfer_backup=previous.get('transfer_backup'),export_sha256=previous.get('export_sha256'))
        elif missing:
            state.update(blocked=True,reason='older_history',message='La copia no contiene todo el historial fiscal, numeración o acuses ya conocidos. Puedes consultar y preparar borradores; restaura una copia más reciente para volver a emitir o enviar.')
        else:
            same_device = manifest.get('device_id')==self.device_id or (not manifest.get('device_id') and known[-1]['installation_id']==target['installation_id'])
            if not same_device:
                state.update(blocked=True,reason='transfer_ready' if prepared else 'transfer_required',
                             transfer_id=ticket['id'] if prepared else None,
                             message='Activa únicamente este equipo para terminar el traslado preparado.' if prepared else 'La copia viene de otro equipo. Prepara el traslado desde el origen y restaura ese paquete; el historial queda disponible para consulta.')
        return state

    def _checkpoint(self, stage):
        """Persist the last completed stage for diagnostics and crash testing."""
        journal = _read_json(self.db.root/JOURNAL)
        journal['last_stage'] = stage
        _atomic_write(self.db.root/JOURNAL,dumps(journal).encode())

    def restore(self,token,confirmation):
        require(confirmation=='RESTAURAR','Escribe RESTAURAR para confirmar.')
        preview = self.previews.pop(token,None)
        if not preview:
            raise AppError('La vista previa ha caducado. Selecciona de nuevo la copia.')
        folder = preview['folder']
        work = None
        try:
            require(preview['expires']>datetime.now(timezone.utc),'La vista previa ha caducado. Selecciona de nuevo la copia.')
            with self.db.lock, _restore_lock(self.db.root):
                _recover(self.db.root)
                for name,digest in preview['prepared_files'].items():
                    path = folder/name
                    require(path.is_file() and not path.is_symlink() and _file_hash(path)==digest,
                            'La vista previa ha cambiado. Selecciona de nuevo la copia.')
                safety = self._create(preview['password'] or self._automatic_password(), export=False)
                prepared_bytes = sum((folder/name).stat().st_size for name in preview['prepared_files'])
                require(shutil.disk_usage(self.db.root).free>=prepared_bytes+16*1024**2,
                        'La copia previa está guardada, pero falta espacio para preparar la restauración completa.')
                work = self.db.root/('.restore-work-'+uid())
                work.mkdir(mode=0o700)
                private_directory(str(work))
                new = work/'new';old = work/'old'
                new.mkdir();old.mkdir()
                for name in ('assets','pdfs','imports'):
                    if (folder/name).exists():
                        shutil.copytree(folder/name,new/name)
                    else:
                        (new/name).mkdir()
                shutil.copyfile(folder/'taller.sqlite3',new/'taller.sqlite3')
                state = self._restore_state(preview,new/'taller.sqlite3')
                _atomic_write(new/GUARD,dumps(state).encode())
                with closing(sqlite3.connect(new/'taller.sqlite3')) as conn, conn:
                    conn.row_factory = sqlite3.Row
                    config = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
                    config['fiscal']['certificate_info'] = None
                    if preview['manifest'].get('device_id')!=self.device_id:
                        config['backup']['external_directory'] = ''
                    conn.execute('UPDATE settings SET data=? WHERE id=1',(dumps(config),))
                    self.db.audit(conn,'backup.restore',token,{'safety_copy':safety['name'],'emission_blocked':state['blocked']})
                _inspect_database(new/'taller.sqlite3')
                # This checkpoint is essential before moving the original DB:
                # its main file must contain all committed WAL transactions.
                with self.db.read() as conn:
                    result = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                    require(result[0]==0,'La base está ocupada. Cierra otras instancias antes de restaurar.')
                for suffix in ('-wal','-shm'):
                    Path(str(self.db.path)+suffix).unlink(missing_ok=True)
                previous = {}
                for name in COMPONENTS:
                    destination = self.db.root/name
                    require(not destination.is_symlink() and not destination.parent.is_symlink(),'Una ruta de datos es un enlace. No se ha restaurado.')
                    previous[name] = destination.exists()
                for path in new.rglob('*'):
                    if path.is_file():
                        with open(path,'rb') as handle: os.fsync(handle.fileno())
                for path in sorted((path for path in work.rglob('*') if path.is_dir()),key=lambda path:len(path.parts),reverse=True):
                    _sync_directory(path)
                _sync_directory(work)
                journal = {'version':1,'phase':'prepared','work':work.name,'previous':previous,'safety_copy':safety['name']}
                _atomic_write(self.db.root/JOURNAL,dumps(journal).encode())
                self._checkpoint('prepared')
                journal['phase']='applying'
                _atomic_write(self.db.root/JOURNAL,dumps(journal).encode())
                for name in COMPONENTS:
                    destination = self.db.root/name
                    saved = old/name
                    saved.parent.mkdir(parents=True,exist_ok=True)
                    if previous[name]:
                        os.replace(destination,saved)
                        _sync_directory(destination.parent)
                        _sync_directory(saved.parent)
                    self._checkpoint('saved:'+name)
                    if (new/name).exists():
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        os.replace(new/name,destination)
                        _sync_directory(destination.parent)
                        _sync_directory((new/name).parent)
                    self._checkpoint('installed:'+name)
                _inspect_database(self.db.path)
                journal['phase']='committed'
                _atomic_write(self.db.root/JOURNAL,dumps(journal).encode())
                self._checkpoint('committed')
                _recover(self.db.root)
                return {'restored':True,'safety_copy':safety['name'],'certificate_reconfiguration':True,'recovery':self.recovery_status()}
        except Exception as exc:
            if (self.db.root/JOURNAL).exists():
                try:
                    with _restore_lock(self.db.root):
                        recovery = _recover(self.db.root)
                except Exception as recovery_error:
                    raise AppError('La restauración quedó interrumpida. Conserva la carpeta de datos y reinicia para recuperar el conjunto anterior.','restore_review_required') from recovery_error
                if recovery['action']=='committed':
                    return {'restored':True,'safety_copy':recovery['safety_copy'],'certificate_reconfiguration':True,'recovery':self.recovery_status()}
                raise AppError('No se completó la restauración; se ha recuperado el conjunto anterior de datos, imágenes, PDF y certificado.','restore_failed') from exc
            raise
        finally:
            shutil.rmtree(folder,ignore_errors=True)
            if work and not (self.db.root/JOURNAL).exists():
                shutil.rmtree(work,ignore_errors=True)
