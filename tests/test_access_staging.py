"""Staging connections close independently of garbage collection or platform."""
from contextlib import closing

import pytest

from taller.access import Staging
from taller.errors import AppError


@pytest.mark.parametrize('invalid_count', [False, True])
def test_extracted_rows_release_connection_on_success_and_failure(tmp_path, monkeypatch, invalid_count):
    import sqlite3
    extracted = tmp_path / 'extracted'
    extracted.mkdir()
    (extracted / 'table-0.jsonl').write_text('{"name":"Synthetic staging row"}\n', encoding='utf-8')
    manifest = {'tables': [{'name': 'Synthetic', 'file': 'table-0.jsonl', 'rows': 2 if invalid_count else 1}]}
    stage = Staging(tmp_path / 'stage')
    original = stage.connect
    connections = []
    def tracked_connect():
        connection = original()
        # Keep a strong reference: GC must not be responsible for closing it.
        connections.append(connection)
        return connection
    monkeypatch.setattr(stage, 'connect', tracked_connect)
    try:
        if invalid_count:
            with pytest.raises(AppError, match='concilia'):
                stage.load_extracted(manifest, extracted)
        else:
            stage.load_extracted(manifest, extracted)
        assert len(connections) == 1
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            connections[0].execute('SELECT 1')
        with closing(original()) as connection:
            assert connection.execute('SELECT count(*) FROM raw_rows').fetchone()[0] == (0 if invalid_count else 1)
    finally:
        for connection in connections:
            connection.close()
