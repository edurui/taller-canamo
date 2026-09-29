"""Real SQLite regressions: Madrid clock changes, exceptions and durable delivery."""
from datetime import datetime, timedelta, timezone

import pytest

from taller.app import App
from taller.errors import AppError
from taller.validation import TZ

UTC = timezone.utc


def event(app, **changes):
    values = dict(title='Cita sintética', start_local='2026-10-18T09:00', end_local='2026-10-18T10:00',
                  reminders=[15], recurrence={'freq': 'weekly', 'until': '2026-11-01', 'dst_policy': 'skip'})
    return app.agenda.save({**values, **changes})


def october(app):
    return app.agenda.list('2026-10-01T00:00:00Z', '2026-11-08T00:00:00Z')


@pytest.mark.parametrize('field', ['start_local', 'end_local'])
def test_nonexistent_spring_clock_time_is_rejected(app, field):
    data = dict(start_local='2026-03-29T01:30', end_local='2026-03-29T04:00', recurrence={'freq': 'none'})
    with pytest.raises(AppError, match='no existe'):
        event(app, **{**data, field: '2026-03-29T02:30'})
    assert app.agenda.list('2026-03-01T00:00:00Z', '2026-04-01T00:00:00Z') == []


def test_nonexistent_explicit_offset_does_not_bypass_wall_validation(app):
    with pytest.raises(AppError, match='desplazamiento'):
        app.agenda.save({'title': 'Hora inexistente', 'start': '2026-03-29T02:30:00+01:00',
                         'end': '2026-03-29T04:00:00+02:00'})


def test_fall_repeated_hour_requires_choice_and_preserves_absolute_duration(app):
    values = dict(start_local='2026-10-25T02:30', end_local='2026-10-25T02:30', recurrence={'freq': 'none'})
    with pytest.raises(AppError) as error:
        event(app, **values)
    assert error.value.code == 'ambiguous_time'
    saved = event(app, **values, start_fold=0, end_fold=1)
    item = october(app)[0]
    assert datetime.fromisoformat(saved['end']) - datetime.fromisoformat(saved['start']) == timedelta(hours=1)
    assert item['occurrence_start'].endswith('+02:00') and item['occurrence_end'].endswith('+01:00')


@pytest.mark.parametrize('policy,count,offset', [('skip', 2, None), ('earlier', 3, '+02:00'), ('later', 3, '+01:00')])
def test_recurrence_fall_policy_is_explicit_and_persistent(app, policy, count, offset):
    event(app, start_local='2026-10-18T02:30', end_local='2026-10-18T03:30',
          recurrence={'freq': 'weekly', 'until': '2026-11-01', 'dst_policy': policy})
    items = october(App(app.db.root))
    assert len(items) == count
    if offset:
        assert items[1]['occurrence_start'].endswith(offset)
        assert datetime.fromisoformat(items[1]['end']) - datetime.fromisoformat(items[1]['start']) == timedelta(hours=1)


@pytest.mark.parametrize('first,last,hours', [('2026-03-28', '2026-03-31', 71), ('2026-10-24', '2026-10-27', 73)])
def test_all_day_multiday_dates_survive_dst_and_legacy_read(app, first, last, hours):
    saved = app.agenda.save({'title': 'Cierre sintético', 'all_day': True, 'start_date': first, 'end_date': last, 'reminders': [0]})
    assert saved['start_date'] == first and saved['end_date'] == last
    assert datetime.fromisoformat(saved['end']) - datetime.fromisoformat(saved['start']) == timedelta(hours=hours)
    with app.db.transaction() as conn:
        conn.execute("UPDATE events SET start_date='',end_date='' WHERE id=?", (saved['id'],))
    reopened = App(app.db.root).agenda.get(saved['id'])
    assert reopened['start_date'] == first and reopened['end_date'] == last
    ics = app.agenda.export_ics().decode()
    assert 'DTSTART;VALUE=DATE:' + first.replace('-', '') in ics
    assert 'DTEND;VALUE=DATE:' + last.replace('-', '') in ics
    assert 'TRIGGER;VALUE=DATE-TIME:' in ics


def test_edit_one_move_outside_view_cancel_and_restore(app):
    saved = event(app)
    initial = october(app)
    moved = app.agenda.save({**initial[1], 'scope': 'occurrence', 'title': 'Solo esta cita',
                            'start_local': '2026-12-14T11:00', 'end_local': '2026-12-14T13:00'})
    assert [r['title'] for r in october(app)] == ['Cita sintética', 'Cita sintética']
    december = app.agenda.list('2026-12-01T00:00:00Z', '2027-01-01T00:00:00Z')
    assert len(december) == 1 and december[0]['title'] == 'Solo esta cita'
    assert december[0]['occurrence_key'] == initial[1]['occurrence_key']
    assert december[0]['overridden']
    app.agenda.remove(saved['id'], scope='occurrence', occurrence_key=initial[0]['occurrence_key'], version=moved['version'])
    assert len(october(app)) == 1
    master = App(app.db.root).agenda.get(saved['id'])
    assert len(master['exceptions']) == 2
    restored = app.agenda.restore_occurrence(saved['id'], initial[0]['occurrence_key'], master['version'])
    assert len(october(app)) == 2 and len(restored['exceptions']) == 1
    ics = app.agenda.export_ics().decode()
    assert ics.count('BEGIN:VEVENT') == 3 and 'DTSTART:20261214T100000Z' in ics
    assert 'DTSTART:20261025T080000Z' not in ics


def test_stale_exception_edit_cannot_overwrite_series_and_pattern_change_needs_review(app):
    saved = event(app)
    first, second, _ = october(app)
    result = app.agenda.save({**first, 'scope': 'occurrence', 'title': 'Excepción'})
    with pytest.raises(AppError) as conflict:
        app.agenda.save({**second, 'scope': 'occurrence', 'title': 'Vista obsoleta'})
    assert conflict.value.code == 'conflict'
    with pytest.raises(AppError) as review:
        app.agenda.save({**result, 'start_local': '2026-10-18T11:00', 'end_local': '2026-10-18T12:00'})
    assert review.value.code == 'exceptions_review'
    changed = app.agenda.save({**result, 'start_local': '2026-10-18T11:00', 'end_local': '2026-10-18T12:00', 'reset_exceptions': True})
    assert app.agenda.get(saved['id'])['exceptions'] == []
    assert all('T11:00' in item['occurrence_start'] for item in october(app))
    assert changed['version'] == result['version'] + 1


def test_snooze_and_delivery_survive_title_edit_and_restart(app):
    start = datetime.now(UTC) - timedelta(minutes=5)
    saved = app.agenda.save({'title': 'Antes', 'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0, 15]})
    grouped = app.agenda.notifications(True)
    assert len(grouped) == 1 and grouped[0]['missed_count'] == 2
    assert app.agenda.mark([grouped[0]['id']], 'snooze', 30)['updated'] == 2
    app.agenda.save({**saved, 'title': 'Después'})
    reopened = App(app.db.root)
    assert reopened.agenda.notifications(True) == []
    with reopened.db.read() as conn:
        rows = list(conn.execute('SELECT * FROM notifications'))
    assert len(rows) == 2 and all(row['snoozed_until'] == row['due_at'] for row in rows)
    assert all(row['title'] == 'Después' and row['delivered_at'] is None for row in rows)


def test_missed_series_is_one_persistent_summary_and_delayed_delivery_cannot_consume_snooze(app):
    start = datetime.now(UTC).astimezone(TZ) - timedelta(days=30, minutes=1)
    app.agenda.save({'title': 'Serie atrasada', 'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(),
                     'recurrence': {'freq': 'daily', 'until': (start + timedelta(days=35)).date().isoformat()}, 'reminders': [0, 15]})
    group = app.agenda.notifications(True)
    assert len(group) == 1 and group[0]['missed_count'] >= 60
    assert 'delivery_group_ids' not in app.agenda.notifications(True)[0]
    reopened = App(app.db.root)
    result = reopened.agenda.mark([group[0]['id']], 'delivered')
    assert result['updated'] == group[0]['missed_count']
    assert reopened.agenda.notifications(True) == []
    assert reopened.agenda.mark([group[0]['id']], 'snooze', 15)['updated'] == group[0]['missed_count']
    assert reopened.agenda.mark([group[0]['id']], 'delivered')['updated'] == 0
    assert reopened.agenda.notifications(True) == []


def test_cancelled_occurrence_and_completed_series_stop_pending_alarms(app):
    start = datetime.now(UTC) - timedelta(minutes=2)
    saved = app.agenda.save({'title': 'Cancelar', 'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(),
                             'recurrence': {'freq': 'daily', 'until': (start + timedelta(days=2)).date().isoformat()}, 'reminders': [0]})
    assert len(app.agenda.notifications(True)) == 1
    app.agenda.remove(saved['id'], scope='occurrence', occurrence_key=saved['start'], version=saved['version'])
    assert not app.agenda.notifications(True)
    current = app.agenda.get(saved['id'])
    app.agenda.save({**current, 'completed': True})
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM notifications WHERE cancelled_at IS NULL').fetchone()[0] == 0


def test_adopting_a_legacy_notification_preserves_its_snooze(app):
    start = (datetime.now(UTC) - timedelta(minutes=2)).replace(microsecond=0)
    saved = app.agenda.save({'title': 'Aviso anterior a v5', 'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(), 'reminders': [0]})
    notice = app.agenda.notifications()[0]
    snoozed = (datetime.now(UTC) + timedelta(minutes=30)).isoformat(timespec='seconds')
    local = start.astimezone(TZ).isoformat()
    with app.db.transaction() as conn:
        conn.execute('UPDATE notifications SET occurrence=?,dedup_key=?,due_at=?,scheduled_due_at=?,snoozed_until=NULL WHERE id=?',
                     (local, saved['id'] + '|' + local + '|0', snoozed, snoozed, notice['id']))
    app.agenda.save({**saved, 'title': 'Texto revisado tras actualizar'})
    assert not app.agenda.notifications(True)
    with app.db.read() as conn:
        row = conn.execute('SELECT * FROM notifications WHERE id=?', (notice['id'],)).fetchone()
    assert row['due_at'] == snoozed and row['snoozed_until'] == snoozed
    assert row['scheduled_due_at'] == start.isoformat(timespec='seconds')


def test_modified_occurrence_customer_identity_matches_selected_customer(app, customer):
    saved = event(app, customer_id=customer['id'])
    second = app.contacts.save_customer({'name': 'Otro cliente sintético'})
    occurrence = october(app)[1]
    app.agenda.save({**occurrence, 'scope': 'occurrence', 'customer_id': second['id']})
    rows = october(app)
    assert rows[0]['customer_name'] == customer['name']
    assert rows[1]['customer_name'] == second['name']


def test_deleting_an_occurrence_rejects_a_forged_key(app):
    saved = event(app)
    with pytest.raises(AppError, match='no pertenece'):
        app.agenda.remove(saved['id'], scope='occurrence', occurrence_key='2026-10-20T09:00:00Z', version=saved['version'])
    assert len(october(app)) == 3


def test_all_cancelled_series_remains_recoverable_without_reactivating_alarms(app):
    saved = event(app)
    original = october(app)
    version = saved['version']
    for row in original:
        app.agenda.remove(saved['id'], scope='occurrence', occurrence_key=row['occurrence_key'], version=version)
        version += 1
    assert october(app) == []
    cancelled = app.agenda.list('2026-10-01T00:00:00Z', '2026-11-08T00:00:00Z', include_cancelled=True)
    assert [row['occurrence_start'] for row in cancelled] == [row['occurrence_start'] for row in original]
    assert all(row['cancelled'] for row in cancelled)
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM notifications WHERE cancelled_at IS NULL').fetchone()[0] == 0
    app.agenda.restore_occurrence(saved['id'], original[1]['occurrence_key'], version)
    assert len(october(app)) == 1
