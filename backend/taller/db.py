"""SQLite unit-of-work, invariant triggers and append-only audit trail."""
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from .validation import now, normalized
from .migrations import LATEST_VERSION, upgrade

SCHEMA_VERSION = LATEST_VERSION
SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (
 id TEXT PRIMARY KEY, legacy_code TEXT UNIQUE, name TEXT NOT NULL, search_text TEXT NOT NULL,
 tax_id TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
 city TEXT NOT NULL DEFAULT '', province TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'ES',
 phone TEXT NOT NULL DEFAULT '', phone2 TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_customer_search ON customers(search_text);
CREATE INDEX IF NOT EXISTS idx_customer_tax ON customers(tax_id);
CREATE TABLE IF NOT EXISTS vehicles (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), legacy_code TEXT,
 plate TEXT NOT NULL, plate_normalized TEXT NOT NULL UNIQUE, make TEXT NOT NULL DEFAULT '',
 model TEXT NOT NULL DEFAULT '', vin TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'Turismo',
 km INTEGER NOT NULL DEFAULT 0 CHECK(km>=0), itv_date TEXT NOT NULL DEFAULT '', next_service TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_vehicle_owner ON vehicles(customer_id);
CREATE TABLE IF NOT EXISTS vehicle_owners (
 id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL REFERENCES vehicles(id), customer_id TEXT NOT NULL REFERENCES customers(id),
 from_date TEXT NOT NULL, until_date TEXT, reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS series (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('invoice','rectification','quote','order')),
 label TEXT NOT NULL, prefix TEXT NOT NULL, year INTEGER NOT NULL, padding INTEGER NOT NULL CHECK(padding BETWEEN 1 AND 8),
 next_number INTEGER NOT NULL CHECK(next_number>0), used INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
 UNIQUE(kind, prefix, year)
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('invoice','quote','order')),
 status TEXT NOT NULL, customer_id TEXT NOT NULL REFERENCES customers(id), vehicle_id TEXT REFERENCES vehicles(id),
 issue_date TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '', series_id TEXT REFERENCES series(id),
 sequence INTEGER, full_number TEXT, payload TEXT NOT NULL, base_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
 total_cents INTEGER NOT NULL, reference_id TEXT REFERENCES documents(id), origin_id TEXT REFERENCES documents(id),
 legacy_key TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(kind, full_number), UNIQUE(kind, origin_id)
);
CREATE INDEX IF NOT EXISTS idx_docs_customer ON documents(customer_id, issue_date DESC);
CREATE INDEX IF NOT EXISTS idx_docs_vehicle ON documents(vehicle_id, issue_date DESC);
CREATE INDEX IF NOT EXISTS idx_docs_kind_date ON documents(kind, issue_date DESC);
CREATE TRIGGER IF NOT EXISTS doc_no_delete BEFORE DELETE ON documents
 WHEN OLD.status NOT IN ('draft') BEGIN SELECT RAISE(ABORT,'El documento ya es inalterable'); END;
CREATE TRIGGER IF NOT EXISTS doc_snapshot_immutable BEFORE UPDATE ON documents
 WHEN OLD.status IN ('issued','void','historical') AND (
 OLD.payload IS NOT NEW.payload OR OLD.customer_id IS NOT NEW.customer_id OR OLD.vehicle_id IS NOT NEW.vehicle_id
 OR OLD.issue_date IS NOT NEW.issue_date OR OLD.full_number IS NOT NEW.full_number OR OLD.series_id IS NOT NEW.series_id
 OR OLD.sequence IS NOT NEW.sequence OR OLD.base_cents IS NOT NEW.base_cents OR OLD.tax_cents IS NOT NEW.tax_cents
 OR OLD.total_cents IS NOT NEW.total_cents OR OLD.reference_id IS NOT NEW.reference_id OR OLD.kind IS NOT NEW.kind
 OR OLD.due_date IS NOT NEW.due_date OR OLD.origin_id IS NOT NEW.origin_id OR OLD.legacy_key IS NOT NEW.legacy_key)
 BEGIN SELECT RAISE(ABORT,'La factura emitida no se puede modificar'); END;
CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), amount_cents INTEGER NOT NULL,
 method TEXT NOT NULL, paid_on TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', reversal_of TEXT UNIQUE REFERENCES payments(id),
 idempotency_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, tax_id TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, sku TEXT UNIQUE, name TEXT NOT NULL, supplier_id TEXT REFERENCES suppliers(id),
 unit_price TEXT NOT NULL DEFAULT '0', cost_price TEXT NOT NULL DEFAULT '0', tax_rate TEXT NOT NULL DEFAULT '21',
 track_stock INTEGER NOT NULL DEFAULT 1, stock TEXT NOT NULL DEFAULT '0', min_stock TEXT NOT NULL DEFAULT '0',
 notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), quantity TEXT NOT NULL, reason TEXT NOT NULL,
 document_id TEXT REFERENCES documents(id), idempotency_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 timezone TEXT NOT NULL DEFAULT 'Europe/Madrid', all_day INTEGER NOT NULL DEFAULT 0,
 customer_id TEXT REFERENCES customers(id), vehicle_id TEXT REFERENCES vehicles(id), notes TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '', reminders TEXT NOT NULL DEFAULT '[15]', recurrence TEXT NOT NULL DEFAULT '{}',
 completed INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_start ON events(start);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, event_id TEXT REFERENCES events(id) ON DELETE CASCADE, occurrence TEXT NOT NULL,
 title TEXT NOT NULL, message TEXT NOT NULL, due_at TEXT NOT NULL, read_at TEXT, delivered_at TEXT,
 dedup_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notification_due ON notifications(due_at,read_at);
CREATE TABLE IF NOT EXISTS fiscal_records (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, document_id TEXT NOT NULL REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('alta','anulacion','subsanacion')), environment TEXT NOT NULL,
 payload TEXT NOT NULL, xml TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, previous_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(document_id,kind)
);
CREATE TABLE IF NOT EXISTS fiscal_outbox (
 record_id TEXT PRIMARY KEY REFERENCES fiscal_records(id), status TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, next_attempt TEXT NOT NULL, last_error TEXT NOT NULL DEFAULT '',
 csv TEXT NOT NULL DEFAULT '', response TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fiscal_attempts (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES fiscal_records(id), status TEXT NOT NULL,
 response TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
 id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS fiscal_no_update BEFORE UPDATE ON fiscal_records BEGIN SELECT RAISE(ABORT,'Registro fiscal inalterable'); END;
CREATE TRIGGER IF NOT EXISTS fiscal_no_delete BEFORE DELETE ON fiscal_records BEGIN SELECT RAISE(ABORT,'Registro fiscal inalterable'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Auditoria inalterable'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Auditoria inalterable'); END;
CREATE TRIGGER IF NOT EXISTS payment_no_update BEFORE UPDATE ON payments BEGIN SELECT RAISE(ABORT,'Utiliza una contrapartida'); END;
CREATE TRIGGER IF NOT EXISTS payment_no_delete BEFORE DELETE ON payments BEGIN SELECT RAISE(ABORT,'Utiliza una contrapartida'); END;
CREATE TRIGGER IF NOT EXISTS stock_no_update BEFORE UPDATE ON stock_movements BEGIN SELECT RAISE(ABORT,'Utiliza otro movimiento'); END;
CREATE TRIGGER IF NOT EXISTS stock_no_delete BEFORE DELETE ON stock_movements BEGIN SELECT RAISE(ABORT,'Utiliza otro movimiento'); END;
'''


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def uid() -> str:
    return str(uuid4())


def migrate_connection(conn):
    """Migrate an already verified connection, including an extracted backup copy."""
    return upgrade(conn, SCHEMA)


class Database:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'taller.sqlite3'
        self.lock = threading.RLock()
        for sub in ['assets', 'pdfs', 'backups', 'secure']:
            (self.root / sub).mkdir(exist_ok=True, mode=0o700)
        conn = self.connect()
        try:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('La base de datos pertenece a una versi\u00f3n m\u00e1s reciente.')
            if 0 < version < SCHEMA_VERSION:
                # Complete SQLite snapshot outside the live database; never a
                # copy of a WAL-dependent main file or a modified original.
                snapshot = self.root/'backups'/f'pre-migration-v{version}-{uid()}.sqlite3'
                backup = sqlite3.connect(snapshot)
                try:
                    conn.backup(backup)
                finally:
                    backup.close()
            self.migration_result = migrate_connection(conn)
        finally:
            conn.close()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('PRAGMA busy_timeout=15000')
        conn.create_function('normalized', 1, normalized, deterministic=True)
        return conn

    @contextmanager
    def transaction(self):
        with self.lock:
            conn = self.connect()
            try:
                conn.execute('BEGIN IMMEDIATE')
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @contextmanager
    def read(self):
        with self.lock:
            conn = self.connect()
            try:
                yield conn
            finally:
                conn.close()

    @staticmethod
    def audit(conn, action: str, entity_id: str, detail: dict):
        previous = conn.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        previous = previous['hash'] if previous else ''
        stamp, payload = now(), dumps(detail)
        digest = hashlib.sha256((previous + '|' + action + '|' + entity_id + '|' + payload + '|' + stamp).encode()).hexdigest()
        conn.execute('INSERT INTO audit(action,entity_id,detail,previous_hash,hash,created_at) VALUES(?,?,?,?,?,?)',
                     (action, entity_id, payload, previous, digest, stamp))

    def check_audit(self) -> dict:
        previous, count = '', 0
        with self.read() as conn:
            for row in conn.execute('SELECT * FROM audit ORDER BY seq'):
                expected = hashlib.sha256((previous + '|' + row['action'] + '|' + row['entity_id'] + '|' + row['detail'] + '|' + row['created_at']).encode()).hexdigest()
                if row['previous_hash'] != previous or row['hash'] != expected:
                    return {'ok': False, 'row': row['seq'], 'checked': count}
                previous, count = row['hash'], count + 1
        return {'ok': True, 'checked': count}
