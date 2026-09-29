"""Batch validation retains official XSD/semantic checks for every XML."""
import hashlib
import shutil
import sqlite3

from lxml import etree
import pytest

from taller import b2b_xml
from taller.b2b import check_storage
from taller.b2b_xml import RESOURCES, CBC, CAC, validation_session
from taller.errors import AppError


def test_one_compiled_batch_validates_each_invoice_and_credit_with_independent_findings():
    invoice=(RESOURCES/'en16931/examples/ubl-tc434-example1.xml').read_text()
    credit=(RESOURCES/'en16931/examples/ubl-tc434-creditnote1.xml').read_text()
    changed=etree.fromstring(invoice.encode())
    changed.find('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}TaxInclusiveAmount').text='1.00'
    with validation_session() as validator:
        assert validator.validate(invoice)['ok']
        assert validator.validate(credit)['ok']
        invalid=validator.validate(etree.tostring(changed,encoding='unicode'))
        assert not invalid['ok'] and any(item['id']=='BR-CO-15' for item in invalid['errors'])
        assert validator.validate(invoice)['ok']


def test_new_batch_reverifies_resource_hashes_after_previous_batch(tmp_path,monkeypatch):
    folder=tmp_path/'rules'
    shutil.copytree(RESOURCES,folder)
    monkeypatch.setattr(b2b_xml,'RESOURCES',folder)
    xml=(folder/'en16931/examples/ubl-tc434-example1.xml').read_text()
    with validation_session() as validator:
        assert validator.validate(xml)['ok']
    resource=folder/'en16931/xslt/EN16931-UBL-validation.xslt'
    resource.write_bytes(resource.read_bytes()+b'<!--changed-->')
    with pytest.raises(AppError) as caught:
        with validation_session():
            pass
    assert caught.value.code=='b2b_schema'


def test_backup_batch_detects_semantically_altered_last_document_even_with_updated_digest(app,customer):
    for index in range(4):
        invoice=app.documents.save({'customer_id':customer['id'],
            'lines':[{'description':'Trabajo sintético '+str(index),'unit_price':'10'}]})
        issued=app.documents.publish(invoice['id'])
        app.b2b.prepare(issued['id'],True)
    with app.db.read() as source:
        staging=sqlite3.connect(':memory:')
        source.backup(staging)
    try:
        assert check_storage(staging)['documents_checked']==4
        identifier,xml=staging.execute('SELECT id,xml FROM b2b_documents ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()
        root=etree.fromstring(xml.encode())
        root.find('{'+CAC+'}LegalMonetaryTotal/{'+CBC+'}TaxInclusiveAmount').text='1.00'
        changed=etree.tostring(root,encoding='unicode')
        staging.execute('DROP TRIGGER b2b_document_no_update')
        staging.execute('UPDATE b2b_documents SET xml=?,digest=? WHERE id=?',
                        (changed,hashlib.sha256(changed.encode()).hexdigest(),identifier))
        with pytest.raises(AppError,match='EN16931') as caught:
            check_storage(staging)
        assert caught.value.code=='b2b_integrity'
    finally:
        staging.close()
