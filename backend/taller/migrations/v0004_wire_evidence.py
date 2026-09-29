"""Provenance for real mTLS exchanges, separate from injected test transports."""

VERSION = 4
NAME = 'fiscal_network_evidence'
SQL = '''
CREATE TABLE fiscal_wire_evidence (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES fiscal_records(id), evidence_id TEXT NOT NULL UNIQUE,
 operation TEXT NOT NULL CHECK(operation IN ('supply','query')), endpoint TEXT NOT NULL,
 request_sha256 TEXT NOT NULL, response_sha256 TEXT NOT NULL, certificate_fingerprint TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX idx_fiscal_wire_record ON fiscal_wire_evidence(record_id,operation);
CREATE TRIGGER fiscal_wire_no_update BEFORE UPDATE ON fiscal_wire_evidence
 BEGIN SELECT RAISE(ABORT,'La evidencia de transporte fiscal es inalterable'); END;
CREATE TRIGGER fiscal_wire_no_delete BEFORE DELETE ON fiscal_wire_evidence
 BEGIN SELECT RAISE(ABORT,'La evidencia de transporte fiscal es inalterable'); END;
'''
