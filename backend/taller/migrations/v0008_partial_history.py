"""Preserve unavailable historical dates and amounts as NULL without weakening new invoices."""

VERSION = 8
NAME = 'partial_historical_documents'
SQL = '''

DROP TRIGGER doc_no_delete;
DROP TRIGGER doc_snapshot_immutable;
DROP TRIGGER doc_invoice_status_immutable;
CREATE TABLE documents_v8 (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('invoice','quote','order')),
 status TEXT NOT NULL, customer_id TEXT NOT NULL REFERENCES customers(id), vehicle_id TEXT REFERENCES vehicles(id),
 issue_date TEXT, due_date TEXT NOT NULL DEFAULT '', series_id TEXT REFERENCES series(id),
 sequence INTEGER, full_number TEXT, payload TEXT NOT NULL, base_cents INTEGER, tax_cents INTEGER,
 total_cents INTEGER, reference_id TEXT REFERENCES documents(id), origin_id TEXT REFERENCES documents(id),
 legacy_key TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(kind, origin_id),
 CHECK(status IN ('historical','import_reverted') OR (issue_date IS NOT NULL AND base_cents IS NOT NULL AND tax_cents IS NOT NULL AND total_cents IS NOT NULL))
);
INSERT INTO documents_v8 SELECT * FROM documents;
DROP TABLE documents;
ALTER TABLE documents_v8 RENAME TO documents;
CREATE UNIQUE INDEX idx_docs_issued_number ON documents(kind,full_number)
 WHERE status NOT IN ('historical','import_reverted');
CREATE INDEX idx_docs_customer ON documents(customer_id,issue_date DESC);
CREATE INDEX idx_docs_vehicle ON documents(vehicle_id,issue_date DESC);
CREATE INDEX idx_docs_kind_date ON documents(kind,issue_date DESC);
CREATE TRIGGER doc_no_delete BEFORE DELETE ON documents
 WHEN OLD.status NOT IN ('draft') BEGIN SELECT RAISE(ABORT,'El documento ya es inalterable'); END;
CREATE TRIGGER doc_snapshot_immutable BEFORE UPDATE ON documents
 WHEN OLD.status IN ('issued','void','historical','import_reverted') AND (
 OLD.payload IS NOT NEW.payload OR OLD.customer_id IS NOT NEW.customer_id OR OLD.vehicle_id IS NOT NEW.vehicle_id
 OR OLD.issue_date IS NOT NEW.issue_date OR OLD.full_number IS NOT NEW.full_number OR OLD.series_id IS NOT NEW.series_id
 OR OLD.sequence IS NOT NEW.sequence OR OLD.base_cents IS NOT NEW.base_cents OR OLD.tax_cents IS NOT NEW.tax_cents
 OR OLD.total_cents IS NOT NEW.total_cents OR OLD.reference_id IS NOT NEW.reference_id OR OLD.kind IS NOT NEW.kind
 OR OLD.due_date IS NOT NEW.due_date OR OLD.origin_id IS NOT NEW.origin_id OR OLD.legacy_key IS NOT NEW.legacy_key)
 BEGIN SELECT RAISE(ABORT,'La factura emitida no se puede modificar'); END;
CREATE TRIGGER doc_invoice_status_immutable BEFORE UPDATE OF status ON documents
 WHEN OLD.kind='invoice' AND (
 (OLD.status='issued' AND NEW.status NOT IN ('issued','void'))
 OR (OLD.status='void' AND NEW.status!='void')
 OR (OLD.status IN ('historical','import_reverted') AND NEW.status NOT IN ('historical','import_reverted')))
 BEGIN SELECT RAISE(ABORT,'El estado de la factura no puede volver a editable'); END;
'''
