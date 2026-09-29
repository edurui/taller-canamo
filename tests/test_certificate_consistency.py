"""Synthetic PKCS#12/TLS-context tests. No network or real certificate is used."""
import base64
import json
from datetime import datetime,timedelta,timezone
from io import BytesIO

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from taller import certificates,fiscal
from taller.errors import AppError


@pytest.fixture(scope='module')
def pfx_pair():
    result=[]
    current=datetime.now(timezone.utc)
    for index in range(2):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,f'SYNTHETIC LOCAL TEST {index}')])
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(current-timedelta(days=1)).not_valid_after(current+timedelta(days=2))
              .sign(key,hashes.SHA256()))
        pfx=pkcs12.serialize_key_and_certificates(b'SYNTHETIC TEST',key,cert,None,serialization.NoEncryption())
        result.append((base64.b64encode(pfx).decode(),cert.fingerprint(hashes.SHA256()).hex().upper()))
    return result


@pytest.fixture
def portable_vault(monkeypatch):
    # Only replace the Windows DPAPI boundary on Linux. PFX parsing and the
    # actual SSLContext/load_cert_chain execute normally with synthetic keys.
    monkeypatch.setattr(certificates,'dpapi',lambda content,**kwargs:content)


def test_save_restores_previous_protected_file_when_metadata_fails(app,pfx_pair,portable_vault,monkeypatch):
    first,second=pfx_pair
    app.certificates.save(first[0],'')
    protected=app.certificates.path.read_bytes()
    def fail(*args):
        raise OSError('synthetic metadata write failure')
    monkeypatch.setattr(app.settings,'internal_update',fail)
    with pytest.raises(OSError,match='synthetic'):
        app.certificates.save(second[0],'')
    assert app.certificates.path.read_bytes()==protected
    assert app.settings.get()['fiscal']['certificate_info']['fingerprint']==first[1]
    assert app.certificates.context()._canamo_certificate_fingerprint==first[1]


def test_save_without_previous_certificate_removes_file_on_metadata_failure(app,pfx_pair,portable_vault,monkeypatch):
    def fail(*args):
        raise OSError('synthetic metadata write failure')
    monkeypatch.setattr(app.settings,'internal_update',fail)
    with pytest.raises(OSError):
        app.certificates.save(pfx_pair[0][0],'')
    assert not app.certificates.path.exists()
    assert app.settings.get()['fiscal']['certificate_info'] is None


def test_crash_mismatch_fails_before_tls_and_creates_no_wire_evidence(app,pfx_pair,portable_vault,monkeypatch):
    first,second=pfx_pair
    app.certificates.save(first[0],'')
    # Simulate process loss after replacing the protected file but before
    # metadata commit. No plaintext/private key is persisted outside tmp_path.
    app.certificates.path.write_bytes(json.dumps({'pfx':second[0],'password':''}).encode())
    monkeypatch.setattr(fiscal.urllib.request,'build_opener',lambda *args:pytest.fail('No transport may open'))
    with pytest.raises(AppError,match='Reinstálalo') as failure:
        app.fiscal._exchange('<synthetic-request/>','aeat_test',None)
    assert failure.value.code=='setup'
    with app.db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fiscal_wire_evidence').fetchone()[0]==0
    assert list((app.db.root/'secure').glob('tls-*'))==[]


def test_exchange_fingerprint_identifies_loaded_context_during_certificate_rotation(app,pfx_pair,portable_vault,monkeypatch):
    first,second=pfx_pair
    app.certificates.save(first[0],'')
    original=app.certificates.context
    def rotated_after_loading():
        context=original()
        app.certificates.save(second[0],'')
        return context
    monkeypatch.setattr(app.certificates,'context',rotated_after_loading)
    class LocalOpener:
        def open(self,request,timeout):
            assert request.full_url==fiscal.TEST_ENDPOINT and timeout==30
            return BytesIO(b'<synthetic-local-response/>')
    monkeypatch.setattr(fiscal.urllib.request,'build_opener',lambda *args:LocalOpener())
    raw,wire=app.fiscal._exchange('<synthetic-request/>','aeat_test',None)
    assert raw=='<synthetic-local-response/>'
    assert wire['certificate_fingerprint']==first[1]
    assert app.settings.get()['fiscal']['certificate_info']['fingerprint']==second[1]
    # This isolated in-memory contract check stores no evidence and asserts no
    # authenticated exchange or AEAT result.
    with app.db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fiscal_wire_evidence').fetchone()[0]==0
