"""Preserve the original encoded bytes of locally received structured invoices."""

VERSION = 7
NAME = 'b2b_original_source_files'
SQL = '''
CREATE TABLE b2b_source_files (
 b2b_id TEXT PRIMARY KEY REFERENCES b2b_documents(id), content BLOB NOT NULL,
 sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER b2b_source_no_update BEFORE UPDATE ON b2b_source_files
 BEGIN SELECT RAISE(ABORT,'El archivo B2B recibido es inalterable'); END;
CREATE TRIGGER b2b_source_no_delete BEFORE DELETE ON b2b_source_files
 BEGIN SELECT RAISE(ABORT,'El archivo B2B recibido es inalterable'); END;
'''
