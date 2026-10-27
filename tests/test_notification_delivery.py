from datetime import datetime, timedelta, timezone

import pytest

from taller.app import App
from taller.errors import AppError


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


def test_ack_for_old_schedule_cannot_consume_a_rescheduled_overdue_occurrence(app):
    start = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0)
    app.agenda.save({
        'title': 'Cita sintética reprogramada', 'start': start.isoformat(),
        'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0],
        'recurrence': {'freq': 'daily', 'until': (start + timedelta(days=2)).date().isoformat()},
    })
    old = app.agenda.notifications(only_undelivered=True)[0]
    occurrence = app.agenda.list((start - timedelta(hours=1)).isoformat(),
                                 (start + timedelta(hours=2)).isoformat())[0]
    moved = start + timedelta(minutes=5)
    app.agenda.save({**occurrence, 'scope': 'occurrence', 'start': moved.isoformat(),
                    'end': (moved + timedelta(hours=1)).isoformat()})
    current = app.agenda.notifications(only_undelivered=True)[0]
    assert current['id'] == old['id'] and current['due_at'] != old['due_at']
    assert app.agenda.mark([old['id']], 'delivered', expected_due_at={old['id']: old['due_at']}) == {'updated': 0}
    assert app.agenda.notifications(only_undelivered=True)[0]['delivered_at'] is None
    assert app.agenda.mark([current['id']], 'delivered', expected_due_at={current['id']: current['due_at']}) == {'updated': 1}
    assert app.agenda.notifications(only_undelivered=True) == []


def test_ack_snapshot_retains_group_delivery_and_idempotence(app):
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    app.agenda.save({'title': 'Grupo sintético', 'start': start.isoformat(),
                    'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0, 15]})
    group = app.agenda.notifications(only_undelivered=True)[0]
    assert group['missed_count'] == 2
    expected = {group['id']: group['due_at']}
    assert app.agenda.mark([group['id']], 'delivered', expected_due_at=expected) == {'updated': 2}
    assert app.agenda.mark([group['id']], 'delivered', expected_due_at=expected) == {'updated': 0}
    assert app.agenda.notifications(only_undelivered=True) == []


@pytest.mark.parametrize('snapshot', [{}, {'different': 'time'}, {'synthetic': None}, []])
def test_ack_snapshot_rejects_incomplete_or_invalid_contract(app, snapshot):
    with pytest.raises(AppError, match='confirmación'):
        app.agenda.mark(['synthetic'], 'delivered', expected_due_at=snapshot)


def test_group_ack_keeps_original_members_when_another_list_refreshes_the_group(app):
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    event = app.agenda.save({'title': 'Grupo creciente sintético', 'start': start.isoformat(),
                            'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0, 15]})
    accepted = app.agenda.notifications(only_undelivered=True)[0]
    assert accepted['has_undelivered'] and len(accepted['delivery_members']) == 2
    app.agenda.save({**event, 'reminders': [0, 15, 30]})
    refreshed = app.agenda.notifications()[0]
    assert refreshed['id'] == accepted['id'] and refreshed['due_at'] == accepted['due_at']
    assert len(refreshed['delivery_members']) == 3

    expected = {accepted['id']: accepted['due_at']}
    members = {accepted['id']: accepted['delivery_members']}
    assert app.agenda.mark([accepted['id']], 'delivered', expected_due_at=expected,
                          expected_members=members) == {'updated': 2}
    mixed = app.agenda.notifications()[0]
    assert mixed['id'] == accepted['id'] and mixed['delivered_at'] is not None
    assert mixed['has_undelivered'] is True
    assert app.agenda.mark([accepted['id']], 'delivered', expected_due_at=expected,
                          expected_members=members) == {'updated': 0}
    pending = app.agenda.notifications(only_undelivered=True)
    assert len(pending) == 1 and pending[0]['id'] != accepted['id']
    assert pending[0]['missed_count'] == 1

    assert app.agenda.mark([mixed['id']], 'delivered', expected_due_at={mixed['id']: mixed['due_at']},
                          expected_members={mixed['id']: mixed['delivery_members']}) == {'updated': 1}
    assert app.agenda.notifications()[0]['has_undelivered'] is False


@pytest.mark.parametrize('members', [None, [], [{'id': 'representative', 'due_at': None}],
                                   [{'id': 'different', 'due_at': 'due'}],
                                   [{'id': 'representative', 'due_at': 'due'}] * 2,
                                   [{'id': 'representative', 'due_at': 'due'}] * 3661])
def test_group_snapshot_rejects_invalid_or_oversized_members(app, members):
    with pytest.raises(AppError, match='confirmación'):
        app.agenda.mark(['representative'], 'delivered', expected_due_at={'representative': 'due'},
                        expected_members={'representative': members})


def test_group_snapshot_cannot_confirm_another_event(app):
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    for title in ['Primer evento sintético', 'Segundo evento sintético']:
        app.agenda.save({'title': title, 'start': start.isoformat(),
                        'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0]})
    first, second = app.agenda.notifications(only_undelivered=True)
    with pytest.raises(AppError, match='otro evento'):
        app.agenda.mark([first['id']], 'delivered', expected_due_at={first['id']: first['due_at']},
                        expected_members={first['id']: first['delivery_members'] + second['delivery_members']})
    assert all(item['delivered_at'] is None for item in app.agenda.notifications())
