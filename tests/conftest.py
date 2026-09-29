import pytest
from taller.app import App
from taller.validation import today

@pytest.fixture
def app(tmp_path):
    return App(tmp_path / "data")

@pytest.fixture
def customer(app):
    app.settings.save("company", {"legal_name":"TALLER FICTICIO", "tax_id":"89890001K"})
    return app.contacts.save_customer({"name":"Lucia de Prueba", "legacy_code":"001", "tax_id":"12345678Z",
        "address":"Calle de prueba 1", "postal_code":"41300", "city":"La Rinconada", "phone":"612 000 001"})

@pytest.fixture
def draft(app, customer):
    return app.documents.save({"customer_id":customer["id"],"issue_date":today(),"lines":[
        {"description":"Mano de obra", "quantity":"1.5", "unit_price":"34.00", "tax_rate":"21"}]})
