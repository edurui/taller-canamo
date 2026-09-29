"""Preserve immutable v1 records and enable traced repeated corrections."""
VERSION = 2
NAME = 'fiscal_corrections_and_reconciliation'
SQL = '''
CREATE TABLE fiscal_records_new (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 document_id TEXT NOT NULL REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('alta','anulacion','subsanacion')), environment TEXT NOT NULL,
 payload TEXT NOT NULL, xml TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, previous_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, correction_of_id TEXT REFERENCES fiscal_records_new(id),
 idempotency_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL DEFAULT ''
);
INSERT INTO fiscal_records_new(seq,id,document_id,kind,environment,payload,xml,hash,previous_hash,created_at,idempotency_key)
 SELECT seq,id,document_id,kind,environment,payload,xml,hash,previous_hash,created_at,'legacy:'||id
 FROM fiscal_records ORDER BY seq;
DROP TRIGGER fiscal_no_update;
DROP TRIGGER fiscal_no_delete;
DROP TABLE fiscal_records;
ALTER TABLE fiscal_records_new RENAME TO fiscal_records;
CREATE UNIQUE INDEX idx_fiscal_initial ON fiscal_records(document_id,environment) WHERE kind='alta';
CREATE INDEX idx_fiscal_document ON fiscal_records(document_id,environment,seq);
CREATE INDEX idx_fiscal_channel ON fiscal_records(environment,seq);
CREATE TRIGGER fiscal_no_update BEFORE UPDATE ON fiscal_records BEGIN SELECT RAISE(ABORT,'Registro fiscal inalterable'); END;
CREATE TRIGGER fiscal_no_delete BEFORE DELETE ON fiscal_records BEGIN SELECT RAISE(ABORT,'Registro fiscal inalterable'); END;
CREATE TABLE fiscal_channels (
 environment TEXT PRIMARY KEY, next_allowed_at TEXT NOT NULL,
 claimed_record_id TEXT REFERENCES fiscal_records(id), claim_token TEXT NOT NULL DEFAULT '',
 claim_until TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
INSERT INTO fiscal_channels(environment,next_allowed_at,updated_at)
 SELECT r.environment,max(o.next_attempt),max(o.updated_at)
 FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id GROUP BY r.environment;
CREATE TABLE fiscal_reconciliations (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES fiscal_records(id),
 request_xml TEXT NOT NULL, response_xml TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX idx_fiscal_reconciliation ON fiscal_reconciliations(record_id,created_at);
CREATE TRIGGER fiscal_reconciliation_no_update BEFORE UPDATE ON fiscal_reconciliations BEGIN SELECT RAISE(ABORT,'Consulta fiscal inalterable'); END;
CREATE TRIGGER fiscal_reconciliation_no_delete BEFORE DELETE ON fiscal_reconciliations BEGIN SELECT RAISE(ABORT,'Consulta fiscal inalterable'); END;
CREATE TRIGGER fiscal_attempt_no_update BEFORE UPDATE ON fiscal_attempts BEGIN SELECT RAISE(ABORT,'Intento fiscal inalterable'); END;
CREATE TRIGGER fiscal_attempt_no_delete BEFORE DELETE ON fiscal_attempts BEGIN SELECT RAISE(ABORT,'Intento fiscal inalterable'); END;
'''
