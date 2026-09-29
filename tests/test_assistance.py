"""Real bundled engines run on synthetic fixtures. Ollama contract tests are identified."""
import base64
import io
import json
import socket
import wave
from pathlib import Path

import pytest
from PIL import Image

from taller.assistance import extract_candidates
from taller.errors import AppError

FIXTURES = Path(__file__).parent/'fixtures/assistance'


def content(path):
    return base64.b64encode(path.read_bytes()).decode()


def block_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Un motor anunciado como local ha intentado usar la red')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def test_optional_assistance_is_disabled_without_blocking_billing(app, draft):
    for action, params in [('assistant.rewrite', {'text': 'Notas'}),
                           ('assistant.extract', {'content': 'AA=='}),
                           ('assistant.transcribe', {'content': 'AA=='})]:
        with pytest.raises(AppError, match='Activa la asistencia'):
            app.dispatch(action, params)
    assert app.documents.publish(draft['id'])['status'] == 'issued'


def test_real_ocr_recovers_reviewable_fields_offline_and_writes_nothing(app, monkeypatch):
    app.settings.save('assistant', {'enabled': True})
    block_network(monkeypatch)
    answer = app.assistance.extract(content(FIXTURES/'ficha-sintetica.png'), 'ficha-sintetica.png')
    candidates = {item['field']: item for item in answer['candidates']}
    assert candidates['plate']['value'] == '1234BCD'
    assert candidates['tax_id']['value'] == '12345678Z' and candidates['tax_id']['valid_format']
    assert candidates['km']['value'] == '123456'
    assert all(item['requires_review'] and item['source_text'] for item in candidates.values())
    assert 'SINTÉTICO' in answer['text'] and not answer['network_called']
    assert answer['source']['sha256'] and answer['source']['width'] == 1400
    assert app.dashboard()['customers'] == 0 and app.documents.list()['total'] == 0
    assert not list(app.db.root.rglob('*.png'))


def test_real_spanish_voice_engine_processes_synthetic_audio_offline(app, monkeypatch):
    app.settings.save('assistant', {'enabled': True})
    block_network(monkeypatch)
    result = app.assistance.transcribe(content(FIXTURES/'dictado-sintetico.wav'))
    assert 'cambio de aceite' in result['text']
    assert result['words'] and all(0 <= word['conf'] <= 1 for word in result['words'])
    assert result['requires_review'] and not result['network_called']
    assert 7 < result['source']['duration_seconds'] < 9
    assert not list(app.db.root.rglob('*.wav'))
    # The reference text is retained separately; this is not a perfect-ASR claim.
    assert json.loads((FIXTURES/'manifest.json').read_text())['voice']['source_text']


def test_bad_or_oversized_audio_and_multiple_image_pages_are_rejected(app):
    app.settings.save('assistant', {'enabled': True})
    with pytest.raises(AppError, match='codificado'):
        app.assistance.transcribe('No es base64!')
    with pytest.raises(AppError, match='WAV'):
        app.assistance.transcribe(base64.b64encode(b'Esto no es WAV').decode())
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(2); audio.setsampwidth(2); audio.setframerate(16000); audio.writeframes(b'\x00'*200)
    with pytest.raises(AppError, match='un canal'):
        app.assistance.transcribe(base64.b64encode(buffer.getvalue()).decode())
    buffer = io.BytesIO()
    Image.new('RGB', (30, 30)).save(buffer, format='TIFF', save_all=True, append_images=[Image.new('RGB', (30, 30), 'white')])
    with pytest.raises(AppError, match='una imagen por página'):
        app.assistance.extract(base64.b64encode(buffer.getvalue()).decode())


def test_ocr_does_not_invent_identity_and_reports_invalid_control_letter():
    candidates = extract_candidates([{'text': 'NIF: 12345678A. Matrícula: 1234 BCD', 'confidence': .42}])
    assert {item['field'] for item in candidates} == {'tax_id', 'plate'}
    assert next(item for item in candidates if item['field'] == 'tax_id')['valid_format'] is False
    assert all(item['confidence'] == .42 and item['requires_review'] for item in candidates)


def test_rewrite_without_model_preserves_facts_and_does_not_use_network(app, monkeypatch):
    app.settings.save('assistant', {'enabled': True, 'model': ''})
    block_network(monkeypatch)
    result = app.assistance.rewrite('  revisar   posible ruido a 80 km/h.\n Consultar antes de reparar. ')
    assert result['text'] == 'Revisar posible ruido a 80 km/h.\nConsultar antes de reparar.'
    assert result['requires_review'] and result['provider'] == 'Reglas de presentación locales'


def test_ollama_adapter_contract_rejects_changed_numbers(app, monkeypatch):
    """Injected protocol response; does not claim an installed generative model."""
    app.settings.save('assistant', {'enabled': True, 'model': 'prueba-local:1'})
    seen = []
    def protocol(path, data, **kwargs):
        seen.append((path, data))
        if path == '/api/show':
            return {'details': {'format': 'gguf'}, 'model_info': {'general.architecture': 'llama'}, 'capabilities': ['completion']}
        return {'response': '{"text":"Revisar a 90 km/h"}'}
    monkeypatch.setattr('taller.assistance._local_model', protocol)
    with pytest.raises(AppError, match='alteraba cifras'):
        app.assistance.rewrite('Revisar a 80 km/h')
    assert seen[0][0] == '/api/show' and 'prompt' not in seen[0][1]
    assert seen[1][0] == '/api/generate' and seen[1][1]['stream'] is False
    assert seen[1][1]['format']['type'] == 'object'


def test_ollama_cloud_proxy_rejected_before_notes_are_sent(app, monkeypatch):
    app.settings.save('assistant', {'enabled': True, 'model': 'alias-local'})
    calls = []
    def remote(path, data, **kwargs):
        calls.append((path, data))
        return {'remote_host': 'https://ollama.com', 'remote_model': 'modelo'}
    monkeypatch.setattr('taller.assistance._local_model', remote)
    with pytest.raises(AppError, match='No se han enviado las notas'):
        app.assistance.rewrite('Contenido sintético privado')
    assert calls == [('/api/show', {'model': 'alias-local'})]


def test_history_queries_conserved_documents_without_ai_and_preserves_owner_history(app, draft, monkeypatch):
    document = app.documents.publish(draft['id'])
    block_network(monkeypatch)
    result = app.assistance.history(customer_id=document['customer_id'], query='mano obra')
    assert result['total'] == 1 and result['items'][0]['id'] == document['id']
    assert app.assistance.history(customer_id=document['customer_id'], query='frenos')['total'] == 0
    assert app.assistance.history(customer_id=document['customer_id'], query='%')['total'] == 0
    with pytest.raises(AppError, match='Selecciona'):
        app.assistance.history()


def test_messages_are_reviewable_drafts_only_and_never_send(app, draft, monkeypatch):
    block_network(monkeypatch)
    with pytest.raises(AppError, match='Publica'):
        app.assistance.message(draft['id'])
    doc = app.documents.publish(draft['id'])
    result = app.assistance.message(doc['id'])
    assert result['sent'] is False and result['draft'] is True
    assert doc['full_number'] in result['text'] and result['text'].startswith('[DOCUMENTO DE PRUEBA]')
    assert result['whatsapp_url'].startswith('https://wa.me/34612000001?text=')
    with pytest.raises(AppError, match='no corresponde'):
        app.assistance.message(doc['id'], 'vehicle_ready')


def test_altered_models_fail_before_loading_engine(app, monkeypatch, tmp_path):
    app.settings.save('assistant', {'enabled': True})
    monkeypatch.setattr('taller.assistance.MODEL_ROOT', tmp_path)
    (tmp_path/'ocr-detection.onnx').write_bytes(b'corrupto')
    (tmp_path/'manifest.json').write_text(json.dumps({'assets': {'ocr-detection.onnx': '0'*64}}))
    with pytest.raises(AppError, match='ha cambiado'):
        app.assistance.extract(content(FIXTURES/'ficha-sintetica.png'))
