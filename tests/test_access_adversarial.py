import base64
import json
from pathlib import Path
import subprocess
import struct
import sys
import zipfile

import pytest

from taller.access import MAX_RAW_ROW_BYTES, java_command
from taller.access_mapping import source_key
from taller.errors import AppError
from test_access_imports import bundle, finish, load_file


def test_native_and_csv_package_tools_are_real_round_trips(app, tmp_path):
    native = tmp_path / 'origen.mdb'
    subprocess.run([*java_command(), 'fixture', str(native), 'mdb'], check=True)
    destination = tmp_path / 'extraído.zip'
    subprocess.run([sys.executable, 'scripts/access_tool.py', 'extract', str(native), str(destination)], check=True)
    diagnosed = load_file(app, destination)
    mapped = app.imports.map(diagnosed['batch_id'], diagnosed['profile'])
    assert mapped['counts']['invoices'] == 2
    assert finish(app, mapped['batch_id'])['balanced']
    csv_package = tmp_path / 'csv.zip'
    subprocess.run([sys.executable, 'scripts/access_tool.py', 'csv-package', str(csv_package),
                    '--table', 'Clientes=tools/access/templates/clientes.csv', '--table', 'Facturas=tools/access/templates/facturas.csv', '--table', 'DETALLE=tools/access/templates/detalle.csv'], check=True)
    with zipfile.ZipFile(csv_package) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['tables'][0]['rows'] == 1
        assert json.loads(archive.read('table-0.jsonl'))['Cod_cli'] == '001'


def test_bundle_path_traversal_rejected_without_extracting(app, tmp_path):
    path = tmp_path / 'hostil.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('../escape.txt', 'bad')
        archive.writestr('manifest.json', '{}')
    with pytest.raises(AppError, match='rutas'):
        load_file(app, path)
    assert not (app.db.root / 'escape.txt').exists()


def test_package_rejects_central_directory_before_zipfile_allocates(app, tmp_path, monkeypatch):
    path = tmp_path / 'central-hostil.zip'
    path.write_bytes(struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, 1, 1, 1024**3, 0, 0))
    monkeypatch.setattr('taller.access_imports.zipfile.ZipFile',
                        lambda *args, **kwargs: pytest.fail('ZipFile must not read an unbounded central directory'))
    with pytest.raises(AppError, match='directorio central'):
        load_file(app, path)
    assert app.contacts.list_customers()['total'] == 0
    assert app.imports.batches()['total'] == 0
    assert next(app.imports.root.glob('*/source.bin')).read_bytes() == path.read_bytes()


def test_compressed_oversize_jsonl_row_fails_without_truncating_original(app, tmp_path):
    path = tmp_path / 'fila-hostil.zip'
    manifest = {'format': 'canamo-access-raw-v1', 'tables': [
        {'name': 'Clientes', 'file': 'table-0.jsonl', 'rows': 2, 'linked': False}]}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('table-0.jsonl', '{"Cod_cli":"001","Cliente":"Sintético"}\n' +
                         json.dumps({'Cod_cli': '002', 'Notas': 'x' * MAX_RAW_ROW_BYTES}) + '\n')
    original = path.read_bytes()
    with pytest.raises(AppError, match='fila 2 supera 2 MiB') as failure:
        load_file(app, path)
    assert failure.value.code == 'access_row_size'
    assert app.contacts.list_customers()['total'] == 0
    assert app.imports.batches()['total'] == 0
    assert next(app.imports.root.glob('*/source.bin')).read_bytes() == original
    from taller.access import Staging
    with Staging(next(app.imports.root.iterdir())).connect() as conn:
        assert conn.execute('SELECT count(*) FROM raw_rows').fetchone()[0] == 0


def test_invalid_row_can_be_excluded_with_a_reason_and_is_still_in_report(app):
    data = bundle(); data['invoices'][0]['issue_date'] = 'not-a-date'
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['error'] == 1
    key = 'invoices:' + source_key(data['invoices'][0], ['legacy_key'])
    mapped = app.imports.map(preview['batch_id'], preview['profile'], {key: {'skip': True, 'reason': 'Fecha pendiente de contraste; excluida del ensayo'}})
    assert mapped['incident_counts']['error'] == 0
    result = finish(app, preview['batch_id'])
    assert result['balanced'] and result['totals']['excluded'] == 1
    original = app.imports.records(preview['batch_id'], entity='invoices')['items'][0]['original']
    assert original['issue_date'] == 'not-a-date'


def test_known_balance_and_missing_quantity_price_are_explicit(app):
    data = bundle(); invoice = data['invoices'][0]; invoice['paid_cents'] = 400
    invoice['lines'][0]['quantity'] = invoice['lines'][0]['unit_price'] = None
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['error'] == 0
    finish(app, preview['batch_id'])
    document = app.documents.get(app.documents.list()['items'][0]['id'])
    assert document['paid_cents'] == 400 and document['pending_cents'] == 760
    assert document['payload']['lines'][0]['unit_price'] is None
    assert document['payment_baseline']['evidence'].startswith('Saldo explícito del origen')
    assert base64.b64decode(app.pdf(document['id'])['content']).startswith(b'%PDF-')


def test_duplicate_number_is_not_identity(app):
    data = bundle(); extra = dict(data['invoices'][0]); extra['legacy_key'] = 'other-original-key'
    data['invoices'].append(extra)
    preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['counts']['invoices'] == 2
    finish(app, preview['batch_id'])
    assert app.documents.list()['total'] == 2


def test_large_csv_no_old_15000_record_cutoff_and_resume(app):
    text = 'codigo;nombre\n' + ''.join(f'{index:06d};Cliente sintético {index}\n' for index in range(15001))
    preview = app.imports.preview(text)
    assert preview['counts']['customers'] == 15001
    assert preview['incident_counts']['error'] == 0
    while not app.imports.simulate(preview['batch_id'], limit=500)['done']: pass
    assert app.contacts.list_customers()['total'] == 0
    while not app.imports.run(preview['batch_id'], limit=500)['done']: pass
    assert app.contacts.list_customers()['total'] == 15001
    reconciliation = app.imports.reconcile(preview['batch_id'])
    assert reconciliation['balanced']
    assert reconciliation['entity_counts']['customers'] == {'source':15001,'destination':15001,'excluded':0,'missing_keys':0}


def test_changes_in_live_customer_block_replacement_and_full_rollback(app):
    data = bundle(); initial = app.imports.preview(json.dumps(data), 'json'); finish(app, initial['batch_id'])
    customer = app.contacts.list_customers()['items'][0]
    app.contacts.save_customer({**customer, 'name': 'Nombre editado después en destino'})
    changed_data = json.loads(json.dumps(data)); changed_data['customers'][0]['name'] = 'Nombre distinto en copia final'
    preview = app.imports.preview(json.dumps(changed_data), 'json')
    key = 'customers:' + source_key(changed_data['customers'][0], ['legacy_code'])
    mapped = app.imports.map(preview['batch_id'], preview['profile'], {key:{'replace':True,'reason':'Copia final'}})
    assert any('actividad posterior' in error for error in mapped['errors'])
    with pytest.raises(AppError, match='actividad posterior'):
        app.imports.rollback(initial['batch_id'], 'No debe perder edición posterior')
    assert app.contacts.customer(customer['id'])['name'] == 'Nombre editado después en destino'


def test_new_invoice_after_import_prevents_archiving_owner(app):
    data = bundle(); initial = app.imports.preview(json.dumps(data), 'json'); finish(app, initial['batch_id'])
    customer = app.contacts.list_customers()['items'][0]
    draft = app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Trabajo posterior','quantity':'1','unit_price':'1','tax_rate':'21'}]})
    with pytest.raises(AppError, match='después'):
        app.imports.rollback(initial['batch_id'], 'No borrar borrador posterior')
    assert app.documents.get(draft['id'])['status'] == 'draft'
    assert app.contacts.customer(customer['id'])['archived'] == 0


def test_explicit_link_keeps_destination_and_does_not_overwrite_it(app):
    existing = app.contacts.save_customer({'legacy_code':'0001','name':'Ficha existente revisada'})
    data = bundle(); preview = app.imports.preview(json.dumps(data), 'json')
    assert preview['incident_counts']['error'] == 1
    key = 'customers:' + source_key(data['customers'][0], ['legacy_code'])
    mapped = app.imports.map(preview['batch_id'], preview['profile'], {key:{'link':existing['id'],'reason':'Identidad contrastada con propietario'}})
    assert mapped['incident_counts']['error'] == 0
    finish(app, preview['batch_id'])
    assert app.contacts.customer(existing['id'])['name'] == 'Ficha existente revisada'
    assert app.documents.list()['items'][0]['customer_id'] == existing['id']
    app.imports.rollback(preview['batch_id'], 'Fin del ensayo')
    assert app.contacts.customer(existing['id'])['archived'] == 0


def test_record_omitted_from_new_copy_is_retained_and_reported(app):
    data = bundle(); data['customers'].append({'legacy_code':'0002','name':'Segundo cliente sintético'})
    first = app.imports.preview(json.dumps(data), 'json'); finish(app, first['batch_id'])
    data['customers'].pop()
    second = app.imports.preview(json.dumps(data), 'json')
    assert any('no aparece' in warning for warning in second['warnings'])
    finish(app, second['batch_id'])
    assert app.contacts.list_customers()['total'] == 2


def test_csv_encoding_postal_relation_and_money_precision_do_not_guess(app, tmp_path):
    customer = tmp_path / 'clientes.csv'
    customer.write_bytes('Cod_cli;Cliente;Codigo_postal;Notas\n001;Muñoz de ensayo;00001;"Primera línea\nSegunda línea"\n'.encode('cp1252'))
    postal = tmp_path / 'postal.csv'; postal.write_text('cp_codpos;cp_poblacion;cp_provincia\n00001;Ciudad de ensayo;Provincia de ensayo\n', encoding='cp1252')
    invoice = tmp_path / 'facturas.csv'; invoice.write_text('COD_CLI;FACTURA;FECHA;BASE;IVA;TOTAL\n001;0001;28/03/2010;10,00;1,60;11,60\n', encoding='cp1252')
    lines = tmp_path / 'detalle.csv'; lines.write_text('COD_CLI;FACTURA;CANTIDAD;CONCEPTO;PRECIO;TOTAL;TIPO_IVA\n001;0001;1;Concepto de prueba;10,0000;10,0001;16\n', encoding='cp1252')
    package = tmp_path / 'paquete.zip'
    subprocess.run([sys.executable, 'scripts/access_tool.py', 'csv-package', str(package), '--encoding', 'cp1252',
                    '--table', 'Clientes=' + str(customer), '--table', 'Codigos_Postal=' + str(postal), '--table', 'Facturas=' + str(invoice), '--table', 'DETALLE=' + str(lines)], check=True)
    diagnosis = load_file(app, package); profile = diagnosis['profile']
    profile['options'] = {'decimal_separator': ',', 'date_format': 'dmy'}
    profile['customers']['joins'] = [{'table':'Codigos_Postal','local':'Codigo_postal','foreign':'cp_codpos','fields':{'city':'cp_poblacion','province':'cp_provincia'}}]
    mapped = app.imports.map(diagnosis['batch_id'], profile)
    assert any('fracciones de céntimo' in issue for issue in mapped['errors'])
    assert app.contacts.list_customers()['total'] == 0
    first = app.imports.records(diagnosis['batch_id'], entity='customers')['items'][0]
    assert first['payload']['legacy_code'] == '001'
    assert first['payload']['postal_code'] == '00001'
    assert first['payload']['city'] == 'Ciudad de ensayo'
    assert first['original']['row']['Notas'] == 'Primera línea\nSegunda línea'


def test_backup_capacity_blocks_before_mutation_and_unapplied_trial_can_be_discarded(app, monkeypatch):
    import taller.backups as backups
    preview = app.imports.preview('codigo;nombre\n001;Cliente sintético\n')
    batch_id = preview['batch_id']
    app.imports.simulate(batch_id)
    monkeypatch.setattr(backups, 'MAX_BYTES', 1024)
    assert app.imports.review(batch_id)['capacity']['within_limit'] is False
    with pytest.raises(AppError) as failure:
        app.imports.run(batch_id)
    assert failure.value.code == 'backup_capacity'
    assert app.contacts.list_customers()['total'] == 0
    assert app.imports.discard(batch_id, 'Ensayo demasiado grande para esta capacidad')['external_original_untouched']
    assert not app.imports._folder(batch_id).exists()
    assert app.imports.batches()['total'] == 0
    assert app.db.check_audit()['ok']


def test_discard_cannot_remove_evidence_of_applied_import(app):
    preview = app.imports.preview('codigo;nombre\n001;Cliente sintético\n')
    app.imports.execute(preview['batch_id'])
    with pytest.raises(AppError, match='cambios aplicados'):
        app.imports.discard(preview['batch_id'], 'No debe destruir evidencia')
    assert (app.imports._folder(preview['batch_id']) / 'source.bin').is_file()
