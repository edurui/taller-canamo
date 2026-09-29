"""Calendar dates, occurrence exceptions and durable notification grouping."""

VERSION = 5
NAME = 'agenda_exceptions_and_notification_delivery'
SQL = '''
ALTER TABLE events ADD COLUMN start_date TEXT NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN end_date TEXT NOT NULL DEFAULT '';
CREATE TABLE event_exceptions (
 event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE, occurrence_key TEXT NOT NULL,
 cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)), payload TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(event_id,occurrence_key)
);
ALTER TABLE notifications ADD COLUMN scheduled_due_at TEXT NOT NULL DEFAULT '';
ALTER TABLE notifications ADD COLUMN snoozed_until TEXT;
ALTER TABLE notifications ADD COLUMN cancelled_at TEXT;
ALTER TABLE notifications ADD COLUMN delivery_group_ids TEXT NOT NULL DEFAULT '[]';
UPDATE notifications SET scheduled_due_at=due_at;
'''
