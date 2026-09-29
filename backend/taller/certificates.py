"""Windows DPAPI certificate vault. No private keys in SQLite, backups or logs."""
import base64
import ctypes
import io
import json
import os
import ssl
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives import hashes
from .errors import AppError, require
from .files import atomic_write


def inspect_pkcs12(data: bytes, password: str):
    require(0 < len(data) <= 2_000_000, 'El certificado es demasiado grande o est\u00e1 vac\u00edo.')
    try:
        key, cert, chain = pkcs12.load_key_and_certificates(data, password.encode() if password else None)
    except Exception as exc:
        raise AppError('No se puede abrir el certificado. Revisa el archivo y su contrase\u00f1a.') from exc
    require(key is not None and cert is not None, 'El archivo debe contener el certificado y su clave privada.')
    current = datetime.now(timezone.utc)
    require(cert.not_valid_before_utc <= current < cert.not_valid_after_utc, 'El certificado no est\u00e1 vigente.')
    info = {'subject': cert.subject.rfc4514_string(), 'expires': cert.not_valid_after_utc.isoformat(),
            'fingerprint': cert.fingerprint(hashes.SHA256()).hex().upper()}
    return key, cert, chain or [], info


def dpapi(data: bytes, *, decrypt=False) -> bytes:
    require(os.name == 'nt', 'La custodia persistente del certificado se configura en el PC Windows del taller.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), buffer), Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    ok = fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise AppError('Windows no puede abrir el almac\u00e9n seguro. Reinstala el certificado en este usuario.')
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(outgoing.pbData)


def private_directory(path: str):
    os.chmod(path, 0o700)
    if os.name == 'nt':
        # Obtain current Windows SID; no certificate data is ever placed in argv.
        import csv
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        system32 = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'
        who = subprocess.run([str(system32/'whoami.exe'), '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True, creationflags=flags)
        sid = next(csv.reader(io.StringIO(who.stdout)))[1]
        require(sid.startswith('S-1-'), 'No se puede identificar el usuario de Windows.')
        subprocess.run([str(system32/'icacls.exe'), path, '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F'], capture_output=True, check=True, creationflags=flags)


class Certificates:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.path = db.root/'secure'/'certificate.dpapi'

    def save(self, content: str, password: str):
        try:
            data = base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise AppError('Archivo de certificado no v\u00e1lido.') from exc
        _, _, _, info = inspect_pkcs12(data,password)
        protected = dpapi(json.dumps({'pfx':content,'password':password}).encode())
        with self.db.lock:
            previous=self.path.read_bytes() if self.path.exists() else None
            atomic_write(self.path,protected)
            try:
                self.settings.internal_update('fiscal','certificate_info',info)
            except Exception:
                # A process crash can interrupt this compensation. context()
                # independently rejects any file/metadata mismatch before TLS.
                if previous is None:
                    self.path.unlink(missing_ok=True)
                else:
                    atomic_write(self.path,previous)
                raise
        return info

    def context(self) -> ssl.SSLContext:
        with self.db.lock:
            require(self.path.exists(), 'Configura primero el certificado digital en este equipo.', 'setup')
            saved = json.loads(dpapi(self.path.read_bytes(), decrypt=True))
            key, cert, chain, info = inspect_pkcs12(base64.b64decode(saved['pfx']),saved['password'])
            expected=self.settings.get()['fiscal'].get('certificate_info') or {}
            require(expected.get('fingerprint')==info['fingerprint'],
                    'El certificado protegido no coincide con sus metadatos. Reinstálalo desde su archivo original; no se ha iniciado el envío.',
                    'setup')
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # SSLContext keeps the private key in memory after load_cert_chain.
            with tempfile.TemporaryDirectory(prefix='tls-', dir=self.db.root/'secure') as folder:
                private_directory(folder)
                key_path, cert_path = Path(folder)/'key.pem', Path(folder)/'cert.pem'
                key_path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
                cert_path.write_bytes(cert.public_bytes(Encoding.PEM) + b''.join(c.public_bytes(Encoding.PEM) for c in chain))
                os.chmod(key_path,0o600)
                context.load_cert_chain(str(cert_path),str(key_path))
            context._canamo_certificate_fingerprint=info['fingerprint']
        return context

    def delete(self):
        self.path.unlink(missing_ok=True)
        self.settings.internal_update('fiscal','certificate_info',None)
        return {'removed':True}
