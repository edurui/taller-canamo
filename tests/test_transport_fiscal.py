import io
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from taller.errors import AppError
from taller.stdio import serve
from taller.fiscal import fiscal_hash, parse_response, RESPONSE, SF, SOAP

@pytest.mark.parametrize("params",[[],False,0,""])
def test_dispatch_rejects_non_object_params(app,params):
    with pytest.raises(AppError):app.dispatch("bootstrap",params)

def test_dispatch_rejects_internal_parameters(app):
    with pytest.raises(AppError):app.dispatch("bootstrap",{"conn":"injected"})
    with pytest.raises(AppError):app.dispatch("unknown")

def test_production_cannot_be_enabled(app):
    with pytest.raises(AppError):app.settings.save("fiscal",{"mode":"production"})

def test_stdio_protocol_valid_invalid_then_valid(tmp_path):
    requests=b'{"id":1,"action":"bootstrap"}\nnot-json\n{"id":3,"action":"customers.list"}\n'
    target=io.StringIO()
    serve(tmp_path/"rpc",io.BytesIO(requests),target,background=False)
    rows=[json.loads(x) for x in target.getvalue().splitlines()]
    assert rows[0]["ok"] and rows[0]["id"]==1
    assert not rows[1]["ok"] and rows[2]["ok"]

def test_stdio_actual_subprocess(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,"PYTHONPATH":str(root/"backend")}
    result=subprocess.run([sys.executable,"-m","taller.stdio","--data",str(tmp_path/"process"),"--no-background"],
        input='{"id":42,"action":"bootstrap"}\n',text=True,capture_output=True,env=env,timeout=20)
    assert result.returncode==0, result.stderr
    response=json.loads(result.stdout)
    assert response["id"]==42 and response["result"]["version"]=="0.9.1"

def test_hash_is_stable_and_sensitive_to_total():
    data={"issuer_nif":"12345678Z","number":"TEST-1","date":"07-09-2026","type":"F1","tax":"21.00","total":"121.00","timestamp":"2026-09-07T09:00:00+02:00"}
    assert len(fiscal_hash(data))==64
    assert fiscal_hash(data)==fiscal_hash(dict(data))
    assert fiscal_hash(data)!=fiscal_hash({**data,"total":"122.00"})

def reply(status="Correcto",number="TEST-1"):
    overall = {'Correcto':'Correcto', 'AceptadoConErrores':'ParcialmenteCorrecto', 'Incorrecto':'Incorrecto'}[status]
    # Synthetic response, valid against the bundled official XSD; no AEAT call.
    return f'''<s:Envelope xmlns:s="{SOAP}" xmlns:r="{RESPONSE}" xmlns:i="{SF}"><s:Body>
      <r:RespuestaRegFactuSistemaFacturacion><r:CSV>LOCAL-TEST</r:CSV>
        <r:Cabecera><i:ObligadoEmision><i:NombreRazon>EMISOR FICTICIO</i:NombreRazon>
          <i:NIF>12345678Z</i:NIF></i:ObligadoEmision></r:Cabecera>
        <r:TiempoEsperaEnvio>60</r:TiempoEsperaEnvio><r:EstadoEnvio>{overall}</r:EstadoEnvio>
        <r:RespuestaLinea><r:IDFactura><i:IDEmisorFactura>12345678Z</i:IDEmisorFactura>
          <i:NumSerieFactura>{number}</i:NumSerieFactura><i:FechaExpedicionFactura>07-09-2026</i:FechaExpedicionFactura>
        </r:IDFactura><r:Operacion><i:TipoOperacion>Alta</i:TipoOperacion></r:Operacion>
          <r:EstadoRegistro>{status}</r:EstadoRegistro></r:RespuestaLinea>
      </r:RespuestaRegFactuSistemaFacturacion></s:Body></s:Envelope>'''

@pytest.mark.parametrize("state,expected",[("Correcto","accepted"),("AceptadoConErrores","accepted_with_errors"),("Incorrecto","rejected")])
def test_parse_local_response_fixture(state,expected):
    data={"issuer_nif":"12345678Z","number":"TEST-1","date":"07-09-2026"}
    assert parse_response(reply(state),data)["status"]==expected

def test_response_wrong_invoice_and_xml_entities_rejected():
    data={"issuer_nif":"12345678Z","number":"TEST-1","date":"07-09-2026"}
    with pytest.raises(AppError):parse_response(reply(number="OTHER"),data)
    with pytest.raises(AppError):parse_response('<!DOCTYPE foo><foo/>',data)

def test_local_fiscal_outbox_never_calls_network(app,draft):
    app.documents.publish(draft["id"])
    def forbidden(_):raise AssertionError("Unexpected network")
    assert app.fiscal.send_next(transport=forbidden)["status"]=="idle"
    assert app.fiscal.verify_chain()["ok"]


def test_dispatch_action_must_be_text(app):
    with pytest.raises(AppError):app.dispatch([])
