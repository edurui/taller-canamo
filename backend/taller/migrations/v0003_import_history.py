"""Source-aware legacy imports and separately evidenced historic payments."""

VERSION = 3
NAME = 'import_sources_and_historic_numbers'
SQL = '''
DROP TRIGGER doc_no_delete;
DROP TRIGGER doc_snapshot_immutable;
CREATE TABLE documents_v3 (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('invoice','quote','order')),
 status TEXT NOT NULL, customer_id TEXT NOT NULL REFERENCES customers(id), vehicle_id TEXT REFERENCES vehicles(id),
 issue_date TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '', series_id TEXT REFERENCES series(id),
 sequence INTEGER, full_number TEXT, payload TEXT NOT NULL, base_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
 total_cents INTEGER NOT NULL, reference_id TEXT REFERENCES documents(id), origin_id TEXT REFERENCES documents(id),
 legacy_key TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(kind, origin_id)
);
INSERT INTO documents_v3 SELECT * FROM documents;
DROP TABLE documents;
ALTER TABLE documents_v3 RENAME TO documents;
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
CREATE TABLE import_sources (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE import_profiles (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE import_batches (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES import_sources(id), source_digest TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('diagnosed','previewed','simulated','running','paused','completed','reverted','failed')),
 profile TEXT NOT NULL DEFAULT '{}', summary TEXT NOT NULL DEFAULT '{}', cursor INTEGER NOT NULL DEFAULT 0 CHECK(cursor>=0),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE import_records (
 source_id TEXT NOT NULL REFERENCES import_sources(id), entity TEXT NOT NULL CHECK(entity IN ('customers','vehicles','invoices')),
 source_key TEXT NOT NULL, source_hash TEXT NOT NULL, target_id TEXT NOT NULL, batch_id TEXT NOT NULL REFERENCES import_batches(id),
 original_json TEXT NOT NULL, imported_state TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 PRIMARY KEY(source_id,entity,source_key)
);
CREATE TABLE import_changes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL REFERENCES import_batches(id), entity TEXT NOT NULL,
 source_key TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('insert','replace','link')),
 before_record TEXT, after_record TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(batch_id,entity,source_key)
);
CREATE INDEX idx_import_batches_source ON import_batches(source_id,created_at);
CREATE INDEX idx_import_records_target ON import_records(target_id);
CREATE INDEX idx_import_changes_batch ON import_changes(batch_id,id);
CREATE TABLE document_payment_baselines (
 document_id TEXT PRIMARY KEY REFERENCES documents(id), paid_cents INTEGER NOT NULL, evidence TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, documented_at TEXT NOT NULL
);
CREATE TRIGGER payment_baseline_no_update BEFORE UPDATE ON document_payment_baselines
 BEGIN SELECT RAISE(ABORT,'La evidencia de cobro es inalterable'); END;
CREATE TRIGGER payment_baseline_no_delete BEFORE DELETE ON document_payment_baselines
 BEGIN SELECT RAISE(ABORT,'La evidencia de cobro es inalterable'); END;
'''
