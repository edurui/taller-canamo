"""Separate, versioned historical estimates. Source documents remain immutable."""

VERSION = 9
NAME = 'historical_review_overlays'
SQL = '''
CREATE TABLE historical_review_versions (
 document_id TEXT NOT NULL REFERENCES documents(id), version INTEGER NOT NULL CHECK(version>=0),
 state TEXT NOT NULL CHECK(state IN ('estimated','pending_review','verified')),
 payload TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('automatic','adjust','verify','reset')),
 created_at TEXT NOT NULL, PRIMARY KEY(document_id,version)
);
CREATE TABLE historical_review_current (
 document_id TEXT PRIMARY KEY REFERENCES documents(id), version INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('estimated','pending_review','verified')), payload TEXT NOT NULL,
 FOREIGN KEY(document_id,version) REFERENCES historical_review_versions(document_id,version)
);
CREATE INDEX idx_historical_review_state ON historical_review_current(state,document_id);
CREATE TABLE historical_review_pending (document_id TEXT PRIMARY KEY REFERENCES documents(id));
CREATE TRIGGER historical_review_no_update BEFORE UPDATE ON historical_review_versions
 BEGIN SELECT RAISE(ABORT,'La revisión histórica es inalterable'); END;
CREATE TRIGGER historical_review_no_delete BEFORE DELETE ON historical_review_versions
 BEGIN SELECT RAISE(ABORT,'La revisión histórica es inalterable'); END;
CREATE TRIGGER historical_review_next BEFORE INSERT ON historical_review_versions
 WHEN NEW.version != coalesce((SELECT max(version)+1 FROM historical_review_versions WHERE document_id=NEW.document_id),0)
 BEGIN SELECT RAISE(ABORT,'La versión de revisión histórica no es consecutiva'); END;
CREATE TRIGGER historical_review_project AFTER INSERT ON historical_review_versions
 BEGIN
 INSERT INTO historical_review_current(document_id,version,state,payload)
 VALUES(NEW.document_id,NEW.version,NEW.state,NEW.payload)
 ON CONFLICT(document_id) DO UPDATE SET version=excluded.version,state=excluded.state,payload=excluded.payload;
 END;
CREATE TRIGGER historical_review_queue_insert AFTER INSERT ON documents
 WHEN NEW.kind='invoice' AND NEW.status IN ('historical','import_reverted')
 AND (NEW.base_cents IS NULL OR NEW.tax_cents IS NULL OR NEW.total_cents IS NULL)
 BEGIN INSERT OR IGNORE INTO historical_review_pending VALUES(NEW.id); END;
CREATE TRIGGER historical_review_queue_update AFTER UPDATE OF status,payload,base_cents,tax_cents,total_cents ON documents
 WHEN NEW.kind='invoice' AND NEW.status IN ('historical','import_reverted')
 AND (NEW.base_cents IS NULL OR NEW.tax_cents IS NULL OR NEW.total_cents IS NULL)
 BEGIN INSERT OR IGNORE INTO historical_review_pending VALUES(NEW.id); END;
-- Python after-hook materializes immutable policy v1 inside this transaction.
INSERT INTO historical_review_pending SELECT id FROM documents WHERE kind='invoice'
 AND status IN ('historical','import_reverted')
 AND (base_cents IS NULL OR tax_cents IS NULL OR total_cents IS NULL);
'''


def after(conn):
    from ..historical_reviews import synchronize_defaults
    synchronize_defaults(conn)
