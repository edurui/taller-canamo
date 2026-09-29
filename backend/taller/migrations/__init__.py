"""Ordered, transactional SQLite migrations shared by startup and staged restore.

Never use executescript inside a migration: sqlite3 implicitly commits before it.
Each module is immutable after release; add a new version for future changes.
"""
import hashlib
import sqlite3
from datetime import datetime, timezone

from . import v0002_fiscal, v0003_import_history, v0004_wire_evidence, v0005_agenda_exceptions, v0006_b2b, v0007_b2b_source_files

MIGRATIONS = (v0002_fiscal,v0003_import_history,v0004_wire_evidence,v0005_agenda_exceptions,v0006_b2b,v0007_b2b_source_files)
LATEST_VERSION = MIGRATIONS[-1].VERSION


def execute_statements(conn, script):
    pending = ''
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            conn.execute(pending)
            pending = ''
    if pending.strip():
        raise RuntimeError('Migración SQL incompleta; no se ha guardado ningún cambio.')


def upgrade(conn, baseline_sql, *, migrations=None):
    migrations = MIGRATIONS if migrations is None else migrations
    target_version = migrations[-1].VERSION if migrations else 1
    if conn.in_transaction:
        raise RuntimeError('La migración requiere una conexión sin transacción activa.')
    foreign_keys = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    # Rebuilding a table while retaining its name is SQLite's documented method
    # for dropping a UNIQUE constraint. FK validation still runs before commit.
    conn.execute('PRAGMA foreign_keys=OFF')
    try:
        conn.execute('BEGIN EXCLUSIVE')
        before = conn.execute('PRAGMA user_version').fetchone()[0]
        if before > target_version or before < 0:
            raise RuntimeError('La base de datos pertenece a una versión más reciente.')
        if before == 0:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if tables:
                raise RuntimeError('Base sin versión y con tablas existentes; requiere diagnóstico antes de migrar.')
            execute_statements(conn, baseline_sql)
            conn.execute('PRAGMA user_version=1')
        conn.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)''')
        applied = []
        for migration in migrations:
            checksum = hashlib.sha256(migration.SQL.encode('utf-8')).hexdigest()
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            history = conn.execute('SELECT checksum FROM schema_migrations WHERE version=?',(migration.VERSION,)).fetchone()
            if history and history[0] != checksum:
                raise RuntimeError('El historial de migraciones no coincide con esta versión de la aplicación.')
            if version >= migration.VERSION:
                if not history:
                    raise RuntimeError('Falta evidencia de una migración aplicada; no se modifica la base.')
                continue
            if migration.VERSION != version + 1:
                raise RuntimeError('Falta una migración intermedia; no se modifica la base.')
            execute_statements(conn, migration.SQL)
            conn.execute('INSERT INTO schema_migrations VALUES(?,?,?,?)',(
                migration.VERSION, migration.NAME, checksum, datetime.now(timezone.utc).isoformat(timespec='seconds')))
            conn.execute(f'PRAGMA user_version={migration.VERSION}')
            applied.append(migration.VERSION)
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('La migración deja relaciones rotas; se han revertido sus cambios.')
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('La base no supera la comprobación de integridad.')
        conn.commit()
        return {'from_version':before, 'to_version':target_version, 'applied':applied}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute('PRAGMA foreign_keys='+('ON' if foreign_keys else 'OFF'))
