from datetime import datetime, timedelta, timezone

from taller.app import App


def test_delivery_after_snooze_does_not_consume_the_future_reminder(app):
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    app.agenda.save({
        "title": "Recordatorio sintético", "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(), "reminders": [0],
    })
    notification = app.agenda.notifications(only_undelivered=True)[0]
    app.agenda.mark([notification["id"]], "snooze", 15)
    assert app.agenda.mark([notification["id"]], "delivered") == {"updated": 0}
    reopened = App(app.db.root)
    with reopened.db.read() as conn:
        stored = dict(conn.execute("SELECT * FROM notifications WHERE id=?", (notification["id"],)).fetchone())
    assert stored["delivered_at"] is None
    assert stored["read_at"] is None
    assert datetime.fromisoformat(stored["due_at"]) > datetime.now(timezone.utc)


def test_delivery_after_read_does_not_override_state(app):
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    app.agenda.save({
        "title": "Aviso leído", "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(), "reminders": [0],
    })
    identifier = app.agenda.notifications()[0]["id"]
    assert app.agenda.mark([identifier], "delivered") == {"updated": 1}
    assert app.agenda.mark([identifier], "delivered") == {"updated": 0}
    app.agenda.mark([identifier], "read")
    assert app.agenda.mark([identifier], "delivered") == {"updated": 0}
    assert app.agenda.notifications() == []
