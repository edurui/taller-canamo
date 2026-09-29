"""Madrid wall times, bounded recurrence, occurrence exceptions and durable alarms."""
import calendar
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from .db import uid, dumps
from .errors import AppError, require
from .validation import aware_date, iso_date, now, TZ, clean_text

KINDS = ('appointment', 'pickup', 'itv', 'maintenance', 'task', 'personal')
FIELDS = ('title', 'kind', 'start', 'end', 'all_day', 'customer_id', 'vehicle_id',
          'notes', 'location', 'reminders', 'recurrence', 'completed', 'start_date', 'end_date')
UTC = timezone.utc


def utc(value):
    return value.astimezone(UTC)


def wall_candidates(value):
    """Return distinct real instants for a naive Madrid wall time, in time order."""
    candidates = {}
    for fold in (0, 1):
        local = value.replace(tzinfo=TZ, fold=fold)
        instant = utc(local)
        if instant.astimezone(TZ).replace(tzinfo=None) == value:
            candidates[instant] = local
    return [candidates[key] for key in sorted(candidates)]


def resolve_wall(value, fold=None):
    try:
        require(isinstance(value, str) and len(value) <= 30, 'Fecha y hora no válidas.')
        local = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AppError('Fecha y hora no válidas.') from exc
    require(local.tzinfo is None, 'Escribe una hora local de Madrid, sin desplazamiento.')
    candidates = wall_candidates(local)
    require(candidates, 'Esa hora no existe en Madrid por el cambio de horario. Elige otra hora.', 'nonexistent_time')
    require(len(candidates) == 1 or (type(fold) is int and fold in (0, 1)),
            'Esa hora ocurre dos veces en Madrid. Elige la primera o la segunda.', 'ambiguous_time')
    return candidates[fold if len(candidates) == 2 else 0]


def _date_times(event):
    start = aware_date(event['start']).astimezone(TZ)
    end = aware_date(event['end']).astimezone(TZ)
    # Version <=4 stored all-day UTC instants. Derive dates in Madrid on read.
    if event.get('all_day'):
        first = date.fromisoformat(event.get('start_date') or start.date().isoformat())
        last = date.fromisoformat(event.get('end_date') or end.date().isoformat())
        start = datetime.combine(first, time.min, TZ)
        end = datetime.combine(last, time.min, TZ)
    return start, end


def occurrences(event, start=None, end=None):
    original, original_end = _date_times(event)
    duration = utc(original_end) - utc(original)
    days = (original_end.date() - original.date()).days
    rule = event.get('recurrence') or {}
    if isinstance(rule, str):
        rule = json.loads(rule)
    freq = rule.get('freq', 'none')
    until = date.fromisoformat(rule['until']) if rule.get('until') else original.date()
    naive = original.replace(tzinfo=None)
    for index in range(732 if freq != 'none' else 1):
        if freq == 'daily':
            local = naive + timedelta(days=index)
        elif freq == 'weekly':
            local = naive + timedelta(weeks=index)
        elif freq == 'monthly':
            year, month = divmod(original.year * 12 + original.month - 1 + index, 12)
            month += 1
            if original.day > calendar.monthrange(year, month)[1]:
                continue  # An absent day 31 is skipped, never silently moved.
            local = naive.replace(year=year, month=month)
        else:
            local = naive
        if freq != 'none' and local.date() > until:
            break
        if index == 0:
            local = original  # Preserve the explicitly selected fall-back fold.
        else:
            choices = wall_candidates(local)
            policy = rule.get('dst_policy', 'skip')
            if not choices or (len(choices) == 2 and policy == 'skip'):
                continue
            local = choices[-1 if policy == 'later' else 0]
        finish = (datetime.combine(local.date() + timedelta(days=days), time.min, TZ)
                  if event.get('all_day') else (utc(local) + duration).astimezone(TZ))
        if (end is None or utc(local) < utc(end)) and (start is None or utc(finish) > utc(start)):
            yield local, finish


class Agenda:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    @staticmethod
    def _decode(row):
        result = dict(row)
        for key in ('reminders', 'recurrence'):
            if isinstance(result[key], str):
                result[key] = json.loads(result[key])
        if result.get('all_day'):
            start, end = _date_times(result)
            result['start_date'], result['end_date'] = start.date().isoformat(), end.date().isoformat()
        return result

    def _normalize(self, data):
        require(isinstance(data, dict), 'Evento no válido.')
        all_day = bool(data.get('all_day'))
        if all_day and data.get('start_date') and data.get('end_date'):
            start_date, end_date = iso_date(data['start_date']), iso_date(data['end_date'])
            start, end = resolve_wall(start_date), resolve_wall(end_date)
        else:
            def point(name):
                if data.get(name + '_local'):
                    return resolve_wall(data[name + '_local'], data.get(name + '_fold'))
                value = aware_date(data.get(name))
                # UTC is an absolute instant. Nonzero offsets supplied as local
                # Madrid times must correspond to the real zone at that instant.
                if value.utcoffset() != timedelta(0):
                    require(value.replace(tzinfo=None) == value.astimezone(TZ).replace(tzinfo=None),
                            'La hora y su desplazamiento no corresponden a Madrid.', 'nonexistent_time')
                return value.astimezone(TZ)
            start, end = point('start'), point('end')
            start_date, end_date = '', ''
            if all_day:
                require(start.time() == time.min and end.time() == time.min,
                        'Un evento de todo el día empieza y termina a medianoche.')
                start_date, end_date = start.date().isoformat(), end.date().isoformat()
        require(utc(end) > utc(start) and utc(end) - utc(start) <= timedelta(days=366, hours=1),
                'La cita debe terminar después de empezar y durar como máximo un año.')
        kind = data.get('kind', 'appointment')
        require(kind in KINDS, 'Tipo de cita no válido.')
        rule = data.get('recurrence') or {'freq': 'none'}
        require(isinstance(rule, dict) and rule.get('freq', 'none') in ('none', 'daily', 'weekly', 'monthly'),
                'Repetición no admitida.')
        rule = dict(rule)
        if rule.get('freq', 'none') != 'none':
            until = date.fromisoformat(iso_date(rule.get('until')))
            require(start.date() <= until <= start.date() + timedelta(days=730),
                    'La repetición debe terminar en un máximo de 2 años.')
            rule['dst_policy'] = rule.get('dst_policy', 'skip')
            require(rule['dst_policy'] in ('earlier', 'later', 'skip'), 'Política de cambio horario no válida.')
        reminders = data.get('reminders', [self.settings.get()['agenda']['reminder_minutes']])
        require(isinstance(reminders, list) and len(reminders) <= 5 and
                all(type(x) is int and 0 <= x <= 10080 for x in reminders),
                'Elige hasta 5 avisos, como máximo una semana antes.')
        return {'title': clean_text(data, 'title', 150, True), 'kind': kind,
                'start': utc(start).isoformat(), 'end': utc(end).isoformat(), 'all_day': int(all_day),
                'start_date': start_date, 'end_date': end_date,
                'customer_id': data.get('customer_id') or None, 'vehicle_id': data.get('vehicle_id') or None,
                'notes': clean_text(data, 'notes', 4000), 'location': clean_text(data, 'location', 300),
                'reminders': sorted(set(reminders)), 'recurrence': rule,
                'completed': int(bool(data.get('completed', False)))}

    @staticmethod
    def _relations(conn, event):
        if event.get('customer_id'):
            require(conn.execute('SELECT 1 FROM customers WHERE id=?', (event['customer_id'],)).fetchone(),
                    'Cliente no encontrado.')
        if event.get('vehicle_id'):
            vehicle = conn.execute('SELECT customer_id FROM vehicles WHERE id=?', (event['vehicle_id'],)).fetchone()
            require(vehicle and (not event.get('customer_id') or vehicle['customer_id'] == event['customer_id']),
                    'El vehículo no corresponde al cliente.')

    @staticmethod
    def _existing(conn, identifier, version=None):
        row = conn.execute('SELECT * FROM events WHERE id=?', (identifier,)).fetchone()
        require(row, 'Evento no encontrado.', 'not_found')
        if version is not None:
            require(row['version'] == version, 'La cita ha cambiado. Vuelve a abrirla.', 'conflict')
        return dict(row)

    @staticmethod
    def _key(event, value):
        key = utc(aware_date(value)).isoformat()
        require(any(utc(start).isoformat() == key for start, _ in occurrences(event)),
                'La repetición no pertenece a esta serie.', 'conflict')
        return key

    def get(self, identifier):
        with self.db.read() as conn:
            event = self._decode(self._existing(conn, identifier))
            event['exceptions'] = [dict(r) for r in conn.execute(
                'SELECT occurrence_key,cancelled FROM event_exceptions WHERE event_id=? ORDER BY occurrence_key',
                (identifier,))]
            return event

    def _expanded(self, conn, event, start=None, end=None, include_cancelled=False):
        base = self._decode(event)
        exceptions = {r['occurrence_key']: dict(r) for r in conn.execute(
            'SELECT * FROM event_exceptions WHERE event_id=?', (event['id'],))}
        for original, finish in occurrences(base):
            key = utc(original).isoformat()
            exception = exceptions.get(key)
            if exception and exception['cancelled'] and not include_cancelled:
                continue
            overrides = json.loads(exception['payload']) if exception else {}
            actual = {**base, **overrides}
            if overrides:
                current, finish = _date_times(actual)
                customer = conn.execute('SELECT name FROM customers WHERE id=?', (actual.get('customer_id'),)).fetchone()
                vehicle = conn.execute('SELECT plate FROM vehicles WHERE id=?', (actual.get('vehicle_id'),)).fetchone()
                actual['customer_name'] = customer['name'] if customer else None
                actual['plate'] = vehicle['plate'] if vehicle else None
            else:
                current = original
                actual.update(start=utc(current).isoformat(), end=utc(finish).isoformat())
                if actual['all_day']:
                    actual.update(start_date=current.date().isoformat(), end_date=finish.date().isoformat())
            if (start is not None and utc(finish) <= utc(start)) or (end is not None and utc(current) >= utc(end)):
                continue
            actual.update(id=base['id'], version=base['version'], recurrence=base['recurrence'],
                          completed=int(bool(base['completed'] or actual['completed'])),
                          occurrence_key=key, occurrence_id=base['id'] + '@' + key,
                          occurrence_start=current.isoformat(), occurrence_end=finish.isoformat(),
                          overridden=bool(exception), cancelled=bool(exception and exception['cancelled']))
            yield actual

    def save(self, data):
        require(isinstance(data, dict), 'Evento no válido.')
        identifier = data.get('id') or uid()
        scope = data.get('scope', 'series')
        require(scope in ('series', 'occurrence'), 'Ámbito de edición no válido.')
        # An override is a single event; moving it beyond the original until date
        # must not accidentally extend or reject the master's recurrence.
        normalized = self._normalize({**data, 'recurrence': {'freq': 'none'}} if scope == 'occurrence' else data)
        with self.db.transaction() as conn:
            self._relations(conn, normalized)
            existing = conn.execute('SELECT * FROM events WHERE id=?', (identifier,)).fetchone()
            if existing:
                require(existing['version'] == data.get('version'), 'La cita ha cambiado. Vuelve a abrirla.', 'conflict')
            if scope == 'occurrence':
                require(existing, 'La serie ya no existe.', 'not_found')
                key = self._key(dict(existing), data.get('occurrence_key'))
                conn.execute('INSERT INTO event_exceptions(event_id,occurrence_key,payload,created_at,updated_at) '
                             'VALUES(?,?,?,?,?) ON CONFLICT(event_id,occurrence_key) DO UPDATE SET '
                             'payload=excluded.payload,cancelled=0,updated_at=excluded.updated_at',
                             (identifier, key, dumps(normalized), now(), now()))
                conn.execute('UPDATE events SET version=version+1,updated_at=? WHERE id=?', (now(), identifier))
            else:
                if existing:
                    old = self._decode(existing)
                    changes_pattern = any(old.get(k) != normalized[k] for k in
                                          ('start', 'end', 'recurrence', 'all_day', 'start_date', 'end_date'))
                    count = conn.execute('SELECT count(*) FROM event_exceptions WHERE event_id=?', (identifier,)).fetchone()[0]
                    require(not (count and changes_pattern) or data.get('reset_exceptions') is True,
                            'La serie tiene repeticiones modificadas o eliminadas. Confirma su reinicio al cambiar las fechas o la repetición.',
                            'exceptions_review')
                    if count and changes_pattern:
                        conn.execute('DELETE FROM event_exceptions WHERE event_id=?', (identifier,))
                values = [dumps(normalized[k]) if k in ('reminders', 'recurrence') else normalized[k] for k in FIELDS]
                if existing:
                    conn.execute('UPDATE events SET ' + ','.join(k + '=?' for k in FIELDS) +
                                 ',version=version+1,updated_at=? WHERE id=?', (*values, now(), identifier))
                else:
                    conn.execute('INSERT INTO events(id,' + ','.join(FIELDS) + ',created_at,updated_at) VALUES(' +
                                 ','.join('?' for _ in range(len(FIELDS) + 3)) + ')',
                                 (identifier, *values, now(), now()))
            row = dict(conn.execute('SELECT * FROM events WHERE id=?', (identifier,)).fetchone())
            self._schedule(conn, row)
            self.db.audit(conn, 'event.save', identifier, {'title': normalized['title'], 'scope': scope,
                                                        'occurrence_key': data.get('occurrence_key', '')})
            return self._decode(row)

    def _schedule(self, conn, event):
        desired = set()
        for item in self._expanded(conn, event):
            if item['completed']:
                continue
            start = aware_date(item['occurrence_start']).astimezone(TZ)
            alarm = start.replace(hour=9, minute=0, second=0, microsecond=0) if item['all_day'] else start
            for minutes in item['reminders']:
                due = (utc(alarm) - timedelta(minutes=minutes)).isoformat(timespec='seconds')
                key = event['id'] + '|' + item['occurrence_key'] + '|' + str(minutes)
                desired.add(key)
                message = ('Todo el día' if item['all_day'] else start.strftime('%H:%M')) + ' - ' + item['title']
                existing = conn.execute('SELECT * FROM notifications WHERE dedup_key=?', (key,)).fetchone()
                legacy = False
                if existing is None:
                    # Adopt old keys without losing a delivered/read/snoozed alarm.
                    existing = conn.execute('SELECT * FROM notifications WHERE event_id=? AND occurrence=? AND dedup_key LIKE ?',
                                            (event['id'], start.isoformat(), '%|' + str(minutes))).fetchone()
                    legacy = existing is not None
                if existing:
                    # Legacy identifiers contain the same original wall time;
                    # differing due_at therefore represents a prior snooze.
                    # Preserve it while adopting the canonical original key.
                    if legacy:
                        conn.execute('UPDATE notifications SET scheduled_due_at=?,snoozed_until=? WHERE id=?',
                                     (due, existing['due_at'] if existing['due_at'] != due else None, existing['id']))
                    changed = not legacy and existing['scheduled_due_at'] != due
                    if changed:
                        conn.execute('UPDATE notifications SET due_at=?,scheduled_due_at=?,snoozed_until=NULL,'
                                     'delivered_at=NULL,read_at=NULL,delivery_group_ids=\'[]\' WHERE id=?',
                                     (due, due, existing['id']))
                    conn.execute('UPDATE notifications SET title=?,message=?,occurrence=?,dedup_key=?,cancelled_at=NULL WHERE id=?',
                                 (item['title'], message, item['occurrence_key'], key, existing['id']))
                else:
                    conn.execute('INSERT INTO notifications(id,event_id,occurrence,title,message,due_at,scheduled_due_at,dedup_key,created_at) '
                                 'VALUES(?,?,?,?,?,?,?,?,?)',
                                 (uid(), event['id'], item['occurrence_key'], item['title'], message, due, due, key, now()))
        for row in conn.execute('SELECT id,dedup_key FROM notifications WHERE event_id=? AND cancelled_at IS NULL', (event['id'],)).fetchall():
            if row['dedup_key'] not in desired:
                conn.execute('UPDATE notifications SET cancelled_at=? WHERE id=?', (now(), row['id']))

    def list(self, start, end, include_cancelled=False):
        start, end = aware_date(start), aware_date(end)
        require(utc(end) > utc(start) and utc(end) - utc(start) <= timedelta(days=370),
                'El intervalo debe ser de un año como máximo.')
        with self.db.read() as conn:
            events = [dict(r) for r in conn.execute('SELECT e.*,c.name AS customer_name,v.plate FROM events e '
                     'LEFT JOIN customers c ON c.id=e.customer_id LEFT JOIN vehicles v ON v.id=e.vehicle_id ORDER BY e.start')]
            output = [item for event in events for item in self._expanded(conn, event, start, end, bool(include_cancelled))]
        return sorted(output, key=lambda item: utc(aware_date(item['occurrence_start'])))

    def remove(self, identifier, scope='series', occurrence_key=None, version=None):
        require(scope in ('series', 'occurrence'), 'Ámbito de edición no válido.')
        with self.db.transaction() as conn:
            row = self._existing(conn, identifier, version)
            if scope == 'occurrence':
                require(version is not None, 'Vuelve a abrir la repetición antes de eliminarla.', 'conflict')
                key = self._key(row, occurrence_key)
                conn.execute('INSERT INTO event_exceptions(event_id,occurrence_key,cancelled,created_at,updated_at) '
                             'VALUES(?,?,1,?,?) ON CONFLICT(event_id,occurrence_key) DO UPDATE SET '
                             'cancelled=1,updated_at=excluded.updated_at', (identifier, key, now(), now()))
                conn.execute('UPDATE events SET version=version+1,updated_at=? WHERE id=?', (now(), identifier))
                self._schedule(conn, self._existing(conn, identifier))
            else:
                conn.execute('DELETE FROM events WHERE id=?', (identifier,))
            self.db.audit(conn, 'event.delete', identifier, {'scope': scope, 'occurrence_key': occurrence_key})
        return {'deleted': True}

    def restore_occurrence(self, identifier, occurrence_key, version):
        with self.db.transaction() as conn:
            row = self._existing(conn, identifier, version)
            key = self._key(row, occurrence_key)
            conn.execute('DELETE FROM event_exceptions WHERE event_id=? AND occurrence_key=?', (identifier, key))
            conn.execute('UPDATE events SET version=version+1,updated_at=? WHERE id=?', (now(), identifier))
            self._schedule(conn, self._existing(conn, identifier))
            self.db.audit(conn, 'event.restore_occurrence', identifier, {'occurrence_key': key})
        return self.get(identifier)

    def notifications(self, only_undelivered=False):
        # Persist the group before handing it to the UI/native delivery. A restart
        # between display and acknowledgement must not fan out every missed alarm.
        with self.db.transaction() as conn:
            condition = 'AND delivered_at IS NULL' if only_undelivered else ''
            rows = conn.execute('SELECT id,event_id,occurrence,title,message,due_at,read_at,delivered_at,snoozed_until '
                                'FROM notifications WHERE due_at<=? AND read_at IS NULL AND cancelled_at IS NULL ' +
                                condition + ' ORDER BY due_at DESC', (now(),)).fetchall()
            groups = {}
            for row in rows:
                groups.setdefault(row['event_id'], []).append(dict(row))
            output = []
            for group in list(groups.values())[:100]:
                representative = group[0]
                members = [{'id': row['id'], 'due_at': row['due_at']} for row in group]
                conn.execute('UPDATE notifications SET delivery_group_ids=? WHERE id=?', (dumps(members), representative['id']))
                representative['missed_count'] = len(group)
                if len(group) > 1:
                    representative['message'] = str(len(group)) + ' avisos pendientes · ' + representative['message']
                output.append(representative)
            return output

    def mark(self, identifiers, action='read', minutes=15):
        require(action in ('read', 'delivered', 'snooze'), 'Acción de aviso no válida.')
        require(isinstance(identifiers, list) and len(identifiers) <= 100 and all(isinstance(x, str) for x in identifiers),
                'Avisos no válidos.')
        require(type(minutes) is int and 1 <= minutes <= 10080, 'Posponer entre 1 minuto y una semana.')
        updated, seen = 0, set()
        with self.db.transaction() as conn:
            for identifier in identifiers:
                representative = conn.execute('SELECT * FROM notifications WHERE id=? AND cancelled_at IS NULL', (identifier,)).fetchone()
                if not representative:
                    continue
                members = json.loads(representative['delivery_group_ids']) or [{'id': identifier, 'due_at': representative['due_at']}]
                for member in members:
                    if member['id'] in seen:
                        continue
                    seen.add(member['id'])
                    condition = ' WHERE id=? AND due_at=? AND cancelled_at IS NULL'
                    params = (member['id'], member['due_at'])
                    if action == 'snooze':
                        due = (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat(timespec='seconds')
                        updated += conn.execute('UPDATE notifications SET due_at=?,snoozed_until=?,delivered_at=NULL,read_at=NULL,delivery_group_ids=\'[]\'' + condition,
                                                (due, due, *params)).rowcount
                    elif action == 'delivered':
                        stamp = now()
                        updated += conn.execute('UPDATE notifications SET delivered_at=?' + condition +
                                                ' AND due_at<=? AND read_at IS NULL AND delivered_at IS NULL',
                                                (stamp, *params, stamp)).rowcount
                    else:
                        updated += conn.execute('UPDATE notifications SET read_at=?' + condition, (now(), *params)).rowcount
        return {'updated': updated}

    def export_ics(self):
        def escape(value):
            return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
        def fold(value):
            chunks, current, size = [], '', 0
            for char in value:
                length = len(char.encode())
                if size + length > 72:
                    chunks.append(current)
                    current, size = ' ', 1
                current += char
                size += length
            return '\r\n'.join([*chunks, current])
        with self.db.read() as conn:
            events = [dict(r) for r in conn.execute('SELECT * FROM events ORDER BY start')]
            items = [item for event in events for item in self._expanded(conn, event)]
        lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//El Canamo//Agenda//ES', 'CALSCALE:GREGORIAN']
        # Export a finite snapshot of actual occurrences. UTC instants preserve
        # both explicit fold choices and exceptions without a lossy generic RRULE.
        for item in items:
            start, end = _date_times(item)
            key = hashlib.sha256(item['occurrence_key'].encode()).hexdigest()[:24]
            lines += ['BEGIN:VEVENT', 'UID:' + item['id'] + '-' + key + '@elcanamo.local',
                      'DTSTAMP:' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')]
            if item['all_day']:
                lines += ['DTSTART;VALUE=DATE:' + start.strftime('%Y%m%d'), 'DTEND;VALUE=DATE:' + end.strftime('%Y%m%d')]
            else:
                lines += ['DTSTART:' + utc(start).strftime('%Y%m%dT%H%M%SZ'), 'DTEND:' + utc(end).strftime('%Y%m%dT%H%M%SZ')]
            lines += ['SUMMARY:' + escape(item['title']), 'DESCRIPTION:' + escape(item['notes']),
                      'LOCATION:' + escape(item['location']), 'X-CANAMO-SERIES:' + item['id']]
            if not item['completed']:
                for minutes in item['reminders']:
                    if item['all_day']:
                        due = utc(start.replace(hour=9)) - timedelta(minutes=minutes)
                        trigger = 'TRIGGER;VALUE=DATE-TIME:' + due.strftime('%Y%m%dT%H%M%SZ')
                    else:
                        trigger = 'TRIGGER:-PT' + str(minutes) + 'M'
                    lines += ['BEGIN:VALARM', trigger, 'ACTION:DISPLAY', 'DESCRIPTION:' + escape(item['title']), 'END:VALARM']
            lines += ['END:VEVENT']
        lines += ['END:VCALENDAR']
        return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')
