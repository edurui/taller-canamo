"""Structured B2B documents, local commercial states and unsent obligations."""

VERSION = 6
NAME = 'b2b_documents_and_commercial_states'
SQL = '''
CREATE TABLE b2b_documents (
 id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id), direction TEXT NOT NULL CHECK(direction IN ('outbound','inbound')),
 syntax TEXT NOT NULL, xml TEXT NOT NULL, digest TEXT NOT NULL UNIQUE, issuer_nif TEXT NOT NULL, recipient_nif TEXT NOT NULL,
 invoice_number TEXT NOT NULL, issue_date TEXT NOT NULL, currency TEXT NOT NULL, total_cents INTEGER NOT NULL,
 test_document INTEGER NOT NULL CHECK(test_document IN (0,1)), validation TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(direction,issuer_nif,invoice_number,issue_date), UNIQUE(document_id)
);
CREATE TABLE b2b_events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, b2b_id TEXT NOT NULL REFERENCES b2b_documents(id),
 state TEXT NOT NULL, occurred_on TEXT NOT NULL, paid_cents INTEGER, evidence TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL, corrects_event_id TEXT REFERENCES b2b_events(id),
 previous_hash TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX idx_b2b_events_document ON b2b_events(b2b_id,seq);
CREATE TABLE b2b_obligations (
 id TEXT PRIMARY KEY, b2b_id TEXT NOT NULL REFERENCES b2b_documents(id), event_id TEXT REFERENCES b2b_events(id),
 kind TEXT NOT NULL CHECK(kind IN ('invoice','commercial_state','payment_state')),
 status TEXT NOT NULL DEFAULT 'awaiting_official_specification', payload TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(b2b_id,kind,event_id)
);
CREATE TRIGGER b2b_document_no_update BEFORE UPDATE ON b2b_documents
 BEGIN SELECT RAISE(ABORT,'La factura B2B conservada es inalterable'); END;
CREATE TRIGGER b2b_document_no_delete BEFORE DELETE ON b2b_documents
 BEGIN SELECT RAISE(ABORT,'La factura B2B conservada es inalterable'); END;
CREATE TRIGGER b2b_event_no_update BEFORE UPDATE ON b2b_events
 BEGIN SELECT RAISE(ABORT,'El estado B2B se corrige con otro evento'); END;
CREATE TRIGGER b2b_event_no_delete BEFORE DELETE ON b2b_events
 BEGIN SELECT RAISE(ABORT,'El estado B2B se corrige con otro evento'); END;
'''
