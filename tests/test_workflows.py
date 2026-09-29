import base64
import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import pytest
from taller.app import App
from taller.errors import AppError
from taller.agenda import occurrences
from taller.validation import today, aware_date, TZ
from taller.backups import encrypt,decrypt
from taller.db import uid

def test_bootstrap_has_production_disabled(app):
    assert not app.bootstrap()["production_released"]
    assert app.settings.get()["fiscal"]["mode"]=="local_test"

def test_demo_is_repeat_protected(app):
    state=app.seed_demo()
    assert state["dashboard"]["customers"]==5
    assert len(app.fiscal.records())==3
    assert app.fiscal.send_next()["status"]=="idle"
    with pytest.raises(AppError):app.seed_demo()

def test_search_first_character_and_plate(app,customer):
    app.contacts.save_vehicle({"customer_id":customer["id"],"plate":"0540-BZD","km":100})
    for query in ["0","0540 bzd","0540BZD","Lucia","612000001","001"]:
        assert app.contacts.search(query)[0]["customer_id"]==customer["id"]
    assert not app.contacts.search("ZZZZ-no-match")

def test_vehicle_unique_normalized(app,customer):
    app.contacts.save_vehicle({"customer_id":customer["id"],"plate":"0540-BZD"})
    with pytest.raises(AppError):app.dispatch("vehicles.save",{"data":{"customer_id":customer["id"],"plate":"0540 bzd"}})

def test_customer_optimistic_lock(app,customer):
    app.contacts.save_customer({**customer,"name":"Changed"})
    with pytest.raises(AppError):app.contacts.save_customer({**customer,"name":"Stale"})

def test_no_vehicle_required_for_invoice(app,draft):
    result=app.documents.publish(draft["id"])
    assert result["vehicle_id"] is None and result["total_cents"]==6171

def test_publish_double_click_atomic(app,draft):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _:app.documents.publish(draft["id"]),range(8)))
    assert len({x["full_number"] for x in results})==1
    assert len(app.fiscal.records())==1
    assert next(x for x in app.settings.list_series() if x["kind"]=="invoice")["used"]==1

def test_concurrent_different_documents_unique_numbers(app,customer):
    docs=[app.documents.save({"customer_id":customer["id"],"lines":[{"description":"A","unit_price":"1"}]}) for _ in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        issued=list(pool.map(lambda d:app.documents.publish(d["id"]),docs))
    assert len({x["full_number"] for x in issued})==12
    assert app.fiscal.verify_chain()=={"ok":True,"checked":12}

def test_snapshot_unchanged_after_customer_edit(app,customer,draft):
    issued=app.documents.publish(draft["id"])
    app.contacts.save_customer({**customer,"name":"Nuevo nombre","address":"Otra calle"})
    result=app.documents.get(issued["id"])
    assert result["payload"]["customer"]["name"]==customer["name"]
    assert result["payload"]["customer"]["address"]==customer["address"]

def test_protected_issued_document_and_audit(app,draft):
    issued=app.documents.publish(draft["id"])
    with pytest.raises(AppError):app.documents.delete_draft(issued["id"])
    with pytest.raises(sqlite3.IntegrityError):
        with app.db.transaction() as c:c.execute("UPDATE documents SET total_cents=1 WHERE id=?",(issued["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        with app.db.transaction() as c:c.execute("DELETE FROM audit")
    assert app.db.check_audit()["ok"]

def test_used_series_cannot_reset(app,draft):
    app.documents.publish(draft["id"])
    series=next(x for x in app.settings.list_series() if x["kind"]=="invoice")
    with pytest.raises(AppError):app.settings.save_series({**series,"next_number":1})

def test_payment_and_reversal(app,draft):
    issued=app.documents.publish(draft["id"])
    p=app.documents.pay(issued["id"],"10.00","cash",today(),"payment-one")
    assert p["paid_cents"]==1000
    assert app.documents.pay(issued["id"],"10.00","cash",today(),"payment-one")["paid_cents"]==1000
    reverted=app.documents.reverse_payment(p["payments"][0]["id"],"Prueba")
    assert reverted["paid_cents"]==0
    with pytest.raises(AppError):app.documents.pay(issued["id"],"999.00","cash",today(),"too-much")

def test_quote_conversion_idempotent(app,customer):
    q=app.documents.save({"kind":"quote","customer_id":customer["id"],"lines":[{"description":"Frenos","unit_price":"100"}]})
    app.documents.publish(q["id"])
    a=app.documents.convert(q["id"])
    b=app.documents.convert(q["id"])
    assert a["id"]==b["id"] and a["status"]=="draft"

def test_stock_idempotence_and_underflow(app):
    p=app.catalogue.save_product({"name":"Filtro"})
    app.catalogue.move(p["id"],"5","Inicial","initial")
    assert app.catalogue.move(p["id"],"5","Inicial","initial")["repeated"]
    with pytest.raises(AppError):app.catalogue.move(p["id"],"-6","Salida","underflow")
    assert app.catalogue.products()[0]["stock"]=="5"

def test_stock_failure_rolls_back_invoice_and_fiscal(app,customer):
    p=app.catalogue.save_product({"name":"Filtro"})
    d=app.documents.save({"customer_id":customer["id"],"stock_affect":True,"lines":[{"description":"Filtro","unit_price":"10","product_id":p["id"]}]})
    with pytest.raises(AppError):app.documents.publish(d["id"])
    assert app.documents.get(d["id"])["status"]=="draft"
    assert not app.fiscal.records()
    assert next(x for x in app.settings.list_series() if x["kind"]=="invoice")["next_number"]==1

def test_backup_roundtrip_restore_and_reopen(app,customer,tmp_path):
    saved=app.backups.create()
    app.contacts.save_customer({"name":"Despues"})
    preview=app.backups.preview(saved["content"])
    assert preview["counts"]["customers"]==1
    app.backups.restore(preview["token"],"RESTAURAR")
    reopened=App(app.db.root)
    assert reopened.contacts.list_customers()["total"]==1
    assert reopened.db.check_audit()["ok"]

def test_backup_never_exports_secure_files(app):
    (app.db.root/"secure"/"secret.txt").write_text("DO NOT EXPORT")
    saved=app.backups.create()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(saved["content"]))) as z:
        assert all(not n.startswith("secure/") for n in z.namelist())

def test_encrypted_backup_wrong_password(app):
    saved=app.backups.create(password="secure-test-password")
    with pytest.raises(AppError):app.backups.preview(saved["content"],"wrong-password")
    assert app.backups.preview(saved["content"],"secure-test-password")["counts"]["customers"]==0

def test_backup_rejects_path_traversal(app):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:z.writestr("../outside.txt","bad")
    with pytest.raises(AppError):app.backups.preview(base64.b64encode(out.getvalue()).decode())

def test_import_csv_preserves_codes_and_leaves_series(app):
    text="Cod_cli;Cliente;Matricula;Telefono1\n001;Persona Demo;1234-ABC;612000001\n"
    before=app.settings.list_series()
    p=app.imports.preview(text)
    assert not p["errors"]
    assert app.imports.execute(p["token"])=={"customers":1,"vehicles":1,"invoices":0}
    assert app.contacts.search("1234")[0]["legacy_code"]=="001"
    assert app.settings.list_series()==before and not app.fiscal.records()
    assert app.imports.preview(text)["already_imported"]

def test_import_duplicate_plates_blocked(app):
    p=app.imports.preview("Cod_cli;Cliente;Matricula\n1;A;1234-ABC\n2;B;1234ABC\n")
    assert p["errors"]
    with pytest.raises(AppError):app.imports.execute(p["token"])
    assert app.contacts.list_customers()["total"]==0

def test_agenda_roundtrip_and_invalid_duration(app):
    start=datetime.now(timezone.utc)+timedelta(hours=1)
    event=app.agenda.save({"title":"Cita demo","start":start.isoformat(),"end":(start+timedelta(hours=1)).isoformat(),"reminders":[15]})
    assert app.agenda.list(start.isoformat(),(start+timedelta(days=1)).isoformat())[0]["id"]==event["id"]
    with pytest.raises(AppError):app.agenda.save({"title":"Bad","start":start.isoformat(),"end":start.isoformat()})
    app.agenda.remove(event["id"])
    assert not app.agenda.list(start.isoformat(),(start+timedelta(days=1)).isoformat())

def test_monthly_skips_nonexistent_day():
    event={"start":"2026-01-31T09:00:00+01:00","end":"2026-01-31T10:00:00+01:00","recurrence":{"freq":"monthly","until":"2026-04-30"}}
    starts=[a for a,b in occurrences(event,aware_date("2026-01-01T00:00:00Z"),aware_date("2026-05-01T00:00:00Z"))]
    assert [x.month for x in starts]==[1,3]

def test_weekly_preserves_madrid_wall_clock_across_dst():
    event={"start":"2026-03-22T09:00:00+01:00","end":"2026-03-22T10:00:00+01:00","recurrence":{"freq":"weekly","until":"2026-04-05"}}
    rows=list(occurrences(event,aware_date("2026-03-01T00:00:00Z"),aware_date("2026-04-10T00:00:00Z")))
    assert [x.hour for x,_ in rows]==[9,9,9]
    assert rows[0][0].utcoffset()!=rows[-1][0].utcoffset()

def test_notification_snooze_persists(app):
    start=datetime.now(timezone.utc)-timedelta(minutes=1)
    e=app.agenda.save({"title":"Aviso","start":start.isoformat(),"end":(start+timedelta(hours=1)).isoformat(),"reminders":[0]})
    notices=app.agenda.notifications()
    assert len(notices)==1
    app.agenda.mark([notices[0]["id"]],"snooze",15)
    assert not App(app.db.root).agenda.notifications()

def test_logo_rejects_active_svg(app):
    svg=base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>').decode()
    with pytest.raises(AppError):app.settings.logo(svg)

def test_pdf_is_generated_from_demo(app,draft):
    issued=app.documents.publish(draft["id"])
    pdf=app.pdf(issued["id"])
    raw=base64.b64decode(pdf["content"])
    assert raw.startswith(b"%PDF-") and len(raw)>1000
    assert (app.db.root/"pdfs"/(issued["id"]+".pdf")).exists()


def test_search_punctuation_does_not_match_all_vehicles(app,customer):
    app.contacts.save_vehicle({"customer_id":customer["id"],"plate":"0540-BZD"})
    assert app.contacts.search("%") == []
    assert app.contacts.search("_") == []

def test_payment_key_cannot_mask_changed_amount(app,draft):
    issued=app.documents.publish(draft["id"])
    app.documents.pay(issued["id"],"10.00","cash",today(),"same-key")
    with pytest.raises(AppError):app.documents.pay(issued["id"],"20.00","cash",today(),"same-key")
    assert app.documents.get(issued["id"])["paid_cents"]==1000

def test_restore_removes_stale_certificate(app):
    saved=app.backups.create()
    (app.db.root/"secure"/"certificate.dpapi").write_bytes(b"test-placeholder-not-a-key")
    preview=app.backups.preview(saved["content"])
    app.backups.restore(preview["token"],"RESTAURAR")
    assert not (app.db.root/"secure"/"certificate.dpapi").exists()
