"""Regression scenarios use temporary databases and synthetic workshop data only."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from taller.app import App
from taller.db import dumps
from taller.errors import AppError
from taller.money import calculate


def make_document(app, customer, *, kind="invoice", vehicle_id=None, **extra):
    return app.documents.save({
        "kind": kind,
        "customer_id": customer["id"],
        "vehicle_id": vehicle_id,
        "lines": [{"description": "Reparación de prueba", "unit_price": "10"}],
        **extra,
    })


@pytest.mark.parametrize("void", [False, True])
def test_document_history_keeps_names_and_plates_after_transfer(app, customer, void):
    vehicle = app.contacts.save_vehicle({"customer_id": customer["id"], "plate": "0540-BZD"})
    document = make_document(app, customer, vehicle_id=vehicle["id"])
    issued = app.documents.publish(document["id"])
    if void:
        app.documents.void(issued["id"], "Error material de prueba", "ANULAR")

    app.contacts.save_customer({**customer, "name": "Nombre actualizado"})
    new_owner = app.contacts.save_customer({"name": "Nuevo propietario"})
    app.contacts.transfer_vehicle(vehicle["id"], new_owner["id"], "Compraventa ficticia")
    current_vehicle = app.contacts.customer(new_owner["id"])["vehicles"][0]
    app.contacts.save_vehicle({**current_vehicle, "plate": "9999-XYZ"})

    listed = app.documents.list(customer_id=customer["id"])
    assert listed["total"] == 1
    assert (listed["items"][0]["customer_name"], listed["items"][0]["plate"]) == (customer["name"], "0540-BZD")
    for query in (customer["name"], "0540-BZD", "0540 bzd", "0540BZD", issued["full_number"]):
        assert [row["id"] for row in app.documents.list(query=query)["items"]] == [issued["id"]]
    for query in ("Nombre actualizado", "Nuevo propietario", "9999-XYZ"):
        assert app.documents.list(query=query)["total"] == 0
    assert app.documents.list(customer_id=new_owner["id"])["total"] == 0
    assert app.documents.list(vehicle_id=vehicle["id"])["items"][0]["plate"] == "0540-BZD"
    assert app.contacts.search("9999XYZ")[0]["customer_id"] == new_owner["id"]
    assert app.documents.get(issued["id"])["customer_name"] == customer["name"]


def test_draft_list_tracks_current_customer_and_plate(app, customer):
    vehicle = app.contacts.save_vehicle({"customer_id": customer["id"], "plate": "0540-BZD"})
    draft = make_document(app, customer, vehicle_id=vehicle["id"])
    app.contacts.save_customer({**customer, "name": "Nombre actualizado"})
    current = app.contacts.customer(customer["id"])["vehicles"][0]
    app.contacts.save_vehicle({**current, "plate": "9999-XYZ"})
    assert app.documents.list(query="Nombre actualizado")["items"][0]["id"] == draft["id"]
    assert app.documents.list(query="9999XYZ")["items"][0]["plate"] == "9999-XYZ"
    assert app.documents.list(query="0540BZD")["total"] == 0


def test_imported_history_uses_only_its_explicit_snapshot(app):
    package = {
        "format": "canamo-import-v1",
        "customers": [{"legacy_code": "H-01", "name": "Nombre actual"}],
        "vehicles": [{"legacy_customer_code": "H-01", "plate": "9999-XYZ"}],
        "invoices": [{
            "legacy_customer_code": "H-01", "legacy_key": "H-F1", "plate": "9999-XYZ",
            "issue_date": "2020-01-02", "full_number": "ANTIGUA-001", "total_cents": 1210,
            "lines": [{"description": "Trabajo histórico", "unit_price": "10"}],
            "customer_snapshot": {"name": "Nombre impreso en 2020"},
            "issuer_snapshot": {"legal_name": "Emisor histórico ficticio"},
            "vehicle_snapshot": {"plate": "0540-BZD"},
        }],
    }
    preview = app.imports.preview(json.dumps(package), "json")
    assert preview["errors"] == []
    app.imports.execute(preview["token"])
    listed = app.documents.list(query="0540BZD")
    assert listed["total"] == 1
    assert listed["items"][0]["customer_name"] == "Nombre impreso en 2020"
    assert app.documents.list(query="Nombre actual")["total"] == 0
    assert app.documents.list(query="9999XYZ")["total"] == 0
    assert app.fiscal.records() == []


@pytest.mark.parametrize("quantity, expected_tax", [("1", 2), ("-1", -2)])
def test_equivalent_vat_rates_share_one_rounding_group(quantity, expected_tax):
    result = calculate([
        {"description": "Concepto", "quantity": quantity, "unit_price": "0.03", "tax_rate": rate}
        for rate in ("21", "21.0", "21.00")
    ], corrective=quantity.startswith("-"))
    assert result["tax_cents"] == expected_tax
    assert len(result["taxes"]) == 1
    assert {line["tax_rate"] for line in result["lines"]} == {"21"}
    assert result["total_cents"] == (11 if quantity == "1" else -11)


def test_vat_groups_keep_different_rates_and_exemptions_separate():
    result = calculate([
        {"description": "General", "quantity": "1.5", "unit_price": "10.02", "discount": "10", "tax_rate": "21.00"},
        {"description": "Reducido A", "unit_price": "0.03", "tax_rate": "10.0"},
        {"description": "Reducido B", "unit_price": "0.03", "tax_rate": "10"},
        {"description": "Cero", "unit_price": "1", "tax_rate": "0.00"},
        {"description": "Exento", "unit_price": "1", "tax_rate": "0", "tax_kind": "E1", "tax_reason": "Caso sintético"},
    ])
    groups = {(row["kind"], row["rate"]): (row["base_cents"], row["tax_cents"]) for row in result["taxes"]}
    assert groups == {("S1", "21"): (1353, 284), ("S1", "10"): (6, 1), ("S1", "0"): (100, 0), ("E1", "0"): (100, 0)}
    assert (result["base_cents"], result["tax_cents"], result["total_cents"]) == (1559, 285, 1844)


def test_catalogue_accepts_equivalent_vat_representations(app):
    product = app.catalogue.save_product({"name": "Filtro", "tax_rate": "21.00"})
    assert next(row for row in app.catalogue.products() if row["id"] == product["id"])["tax_rate"] == "21"


def test_stock_key_cannot_hide_a_different_operation(app, customer):
    product = app.catalogue.save_product({"name": "Filtro"})
    other = app.catalogue.save_product({"name": "Aceite"})
    document = make_document(app, customer)
    original = dict(product_id=product["id"], quantity="5", reason=" Entrada inicial ", idempotency_key="same-key")
    movement = app.catalogue.move(**original)
    assert app.catalogue.move(**{**original, "quantity": "5.000"}) == {"id": movement["id"], "repeated": True}
    for replacement in ({"product_id": other["id"]}, {"quantity": "2"}, {"document_id": document["id"]}, {"reason": "Otra operación"}):
        with pytest.raises(AppError, match="clave"):
            app.catalogue.move(**{**original, **replacement})
    assert len(app.catalogue.movements(product["id"])) == 1
    assert app.catalogue.movements(product["id"])[0]["reason"] == original["reason"]
    assert next(row for row in app.catalogue.products() if row["id"] == product["id"])["stock"] == "5"


def test_conversion_chain_preserves_stock_and_reuses_existing_invoice(app, customer):
    product = app.catalogue.save_product({"name": "Filtro"})
    app.catalogue.move(product["id"], "9", "Entrada inicial", "initial")
    quote = make_document(app, customer, kind="quote", stock_affect=True, lines=[
        {"description": "Filtro", "unit_price": "10", "quantity": "2", "product_id": product["id"]},
    ])
    app.documents.publish(quote["id"])
    order = app.documents.convert(quote["id"], "order")
    app.documents.publish(order["id"])
    assert app.catalogue.products()[0]["stock"] == "9"
    invoice = app.documents.convert(order["id"], "invoice")
    assert invoice["payload"]["stock_affect"] is True
    assert invoice["payload"]["lines"] == quote["payload"]["lines"]
    app.documents.publish(invoice["id"])
    assert app.documents.convert(quote["id"], "invoice")["id"] == invoice["id"]
    assert app.documents.convert(order["id"], "invoice")["id"] == invoice["id"]
    app.documents.publish(invoice["id"])
    assert app.catalogue.products()[0]["stock"] == "7"
    assert len(app.catalogue.movements(product["id"])) == 2
    assert len(app.fiscal.records()) == 1


def test_concurrent_conversion_across_database_instances(app, customer):
    quote = make_document(app, customer, kind="quote")
    app.documents.publish(quote["id"])
    order = app.documents.convert(quote["id"], "order")
    app.documents.publish(order["id"])
    clients = [App(app.db.root) for _ in range(4)]
    start = Barrier(len(clients))

    def convert(task):
        client, source = task
        start.wait(timeout=10)
        return client.documents.convert(source, "invoice")

    with ThreadPoolExecutor(max_workers=len(clients)) as executor:
        sources = (quote["id"], order["id"], quote["id"], order["id"])
        converted = list(executor.map(convert, zip(clients, sources)))
    assert len({document["id"] for document in converted}) == 1
    assert app.documents.list()["total"] == 1


def test_issued_invoice_cannot_start_a_new_conversion_chain(app, customer):
    invoice = make_document(app, customer)
    app.documents.publish(invoice["id"])
    with pytest.raises(AppError):
        app.documents.convert(invoice["id"], "quote")


def test_rectification_keeps_vehicle_history_after_transfer(app, customer):
    vehicle = app.contacts.save_vehicle({"customer_id": customer["id"], "plate": "0540-BZD", "km": 100})
    original = make_document(app, customer, vehicle_id=vehicle["id"], kilometres=100)
    original = app.documents.publish(original["id"])
    new_owner = app.contacts.save_customer({"name": "Nuevo propietario"})
    app.contacts.transfer_vehicle(vehicle["id"], new_owner["id"], "Compraventa ficticia")
    current_vehicle = app.contacts.customer(new_owner["id"])["vehicles"][0]
    app.contacts.save_vehicle({**current_vehicle, "plate": "9999-XYZ", "km": 200})

    correction = app.documents.rectify(original["id"], "Devolución parcial de prueba")
    # Editing a partial correction must preserve the original vehicle as well.
    correction = app.documents.save({**correction, **correction["payload"], "kilometres": 9999,
        "lines": [{"description": "Devolución parcial", "quantity": "-1", "unit_price": "5"}]})
    corrected = app.documents.publish(correction["id"])
    assert corrected["customer_id"] == customer["id"]
    assert corrected["payload"]["vehicle"] == original["payload"]["vehicle"]
    assert corrected["plate"] == "0540-BZD"
    assert corrected["total_cents"] == -605
    assert app.contacts.customer(new_owner["id"])["vehicles"][0]["km"] == 200
    assert app.documents.list(customer_id=new_owner["id"])["total"] == 0
    assert app.fiscal.verify_chain()["ok"] is True


def test_unrelated_transferred_vehicle_still_blocks_new_invoice(app, customer):
    vehicle = app.contacts.save_vehicle({"customer_id": customer["id"], "plate": "0540-BZD"})
    draft = make_document(app, customer, vehicle_id=vehicle["id"])
    new_owner = app.contacts.save_customer({"name": "Nuevo propietario"})
    app.contacts.transfer_vehicle(vehicle["id"], new_owner["id"], "Compraventa ficticia")
    with pytest.raises(AppError, match="propietario"):
        app.documents.publish(draft["id"])
    assert app.documents.get(draft["id"])["status"] == "draft"
    assert app.fiscal.records() == []


def test_order_edit_preserves_published_identity(app, customer):
    order = make_document(app, customer, kind="order")
    published = app.documents.publish(order["id"])
    app.contacts.save_customer({**customer, "name": "Nombre actualizado"})
    saved = app.documents.save({**published, **published["payload"], "notes": "Diagnóstico actualizado"})
    assert saved["payload"]["customer"] == published["payload"]["customer"]
    assert saved["payload"]["issuer"] == published["payload"]["issuer"]
    assert app.documents.list(kind="order", query=customer["name"])["items"][0]["id"] == saved["id"]
    assert app.documents.list(kind="order", query="Nombre actualizado")["total"] == 0


def test_stock_key_conflict_rolls_back_issuing(app, customer):
    product = app.catalogue.save_product({"name": "Filtro"})
    draft = make_document(app, customer, stock_affect=True, lines=[
        {"description": "Filtro", "unit_price": "10", "product_id": product["id"]},
    ])
    app.catalogue.move(product["id"], "5", "Entrada ajena", draft["id"] + ":0")
    with pytest.raises(AppError, match="clave"):
        app.documents.publish(draft["id"])
    assert app.documents.get(draft["id"])["status"] == "draft"
    assert app.documents.get(draft["id"])["full_number"] is None
    assert app.fiscal.records() == []
    assert app.catalogue.products()[0]["stock"] == "5"
    assert next(series for series in app.settings.list_series() if series["kind"] == "invoice")["next_number"] == 1


def test_direct_invoice_reused_when_order_is_created_later(app, customer):
    quote = make_document(app, customer, kind="quote")
    app.documents.publish(quote["id"])
    invoice = app.documents.convert(quote["id"], "invoice")
    order = app.documents.convert(quote["id"], "order")
    app.documents.publish(order["id"])
    assert app.documents.convert(order["id"], "invoice")["id"] == invoice["id"]
    assert app.documents.list()["total"] == 1


def test_old_draft_rounding_requires_a_fresh_review_before_issuing(app, customer):
    lines = [{"description": "Concepto", "unit_price": "0.03", "tax_rate": rate} for rate in ("21", "21.0", "21.00")]
    draft = make_document(app, customer, lines=lines)
    old_payload = {**draft["payload"], "tax_cents": 3, "total_cents": 12}
    # Synthetic draft persisted by the old version, which rounded three groups.
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET payload=?,tax_cents=3,total_cents=12 WHERE id=?", (dumps(old_payload), draft["id"]))
    with pytest.raises(AppError, match="recalcularse"):
        app.documents.publish(draft["id"])
    assert app.fiscal.records() == []
    assert app.documents.get(draft["id"])["total_cents"] == 12
    corrected = app.documents.save({**draft, **draft["payload"], "lines": lines})
    assert corrected["total_cents"] == 11
    assert app.documents.publish(corrected["id"], expected_version=corrected["version"])["total_cents"] == 11


def test_rectification_draft_cannot_be_issued_after_original_is_void(app, customer):
    original = make_document(app, customer)
    app.documents.publish(original["id"])
    correction = app.documents.rectify(original["id"], "Corrección ficticia")
    # A prior version allowed this combination. The public void operation now
    # blocks existing corrective drafts; retain the legacy publication guard.
    with app.db.transaction() as conn:
        conn.execute("UPDATE documents SET status='void' WHERE id=?", (original["id"],))
    with pytest.raises(AppError, match="original"):
        app.documents.publish(correction["id"])
    assert app.documents.get(correction["id"])["status"] == "draft"
