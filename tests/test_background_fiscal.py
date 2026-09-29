"""Tick routing is a local spy; rejection uses the real gate and never contacts AEAT."""
import json

import pytest


def _set_stored_mode(app, mode):
    # Simulate stored configuration, including tampering. Settings.save correctly
    # refuses production without evidence; these tests do not authorize that mode.
    with app.db.transaction() as conn:
        row = conn.execute('SELECT data FROM settings WHERE id=1').fetchone()
        config = json.loads(row['data'])
        config['fiscal']['mode'] = mode
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(config),))


@pytest.mark.parametrize('mode,called', [('local_test',False),('aeat_test',True),('production',True)])
def test_tick_routes_enabled_remote_modes_without_network(app, monkeypatch, mode, called):
    _set_stored_mode(app,mode)
    calls=[]
    monkeypatch.setattr(app.fiscal,'send_next',lambda: calls.append(mode) or {'status':'idle'})
    result=app.tick()
    assert calls == ([mode] if called else [])
    assert ('fiscal' in result) is called


def test_background_production_gate_does_not_open_tls_or_claim_queue(app, draft, monkeypatch):
    app.documents.publish(draft['id'])
    with app.db.read() as conn:
        before=[dict(row) for row in conn.execute('SELECT * FROM fiscal_outbox')]
    _set_stored_mode(app,'production')
    monkeypatch.setattr(app.fiscal.certificates,'context',lambda: pytest.fail('TLS must not be opened'))
    result=app.tick()
    assert result['fiscal']['status']=='blocked'
    assert result['fiscal']['code']=='production_blocked'
    assert 'notifications' in result
    with app.db.read() as conn:
        assert [dict(row) for row in conn.execute('SELECT * FROM fiscal_outbox')]==before
