"""Initial-delivery checks use only disposable synthetic workshop data."""

import importlib.util
import json
import sqlite3
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def packager():
    path = Path(__file__).resolve().parents[1] / "scripts/package_private_installer.py"
    spec = importlib.util.spec_from_file_location("private_packager", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backup_inspection_counts_archived_and_visible_records_separately(app, packager):
    app.contacts.save_customer({"name": "Cliente activo sintético"})
    archived = app.contacts.save_customer({"name": "Cliente archivado sintético"})
    with app.db.transaction() as connection:
        connection.execute("UPDATE customers SET archived=1 WHERE id=?", (archived["id"],))
    backup = app.backups._create(export=False)
    result = packager.inspect_backup(app.db.root / "backups" / backup["name"])
    assert result["counts"]["customers"] == 2
    assert result["visible_counts"]["customers"] == 1
    assert result["sha256"] == backup["sha256"]


def test_backup_inspection_closes_database_before_removing_temporary_files(
    app, packager, monkeypatch
):
    backup = app.backups._create(export=False)
    connections = []
    connect = sqlite3.connect

    def tracked_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(packager.sqlite3, "connect", tracked_connection)
    packager.inspect_backup(app.db.root / "backups" / backup["name"])
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("change", ["altered_database", "unlisted_file", "private_key"])
def test_initial_data_rejects_alteration_unlisted_files_and_secrets(
    app, packager, tmp_path, change
):
    backup = app.backups._create(export=False)
    with zipfile.ZipFile(app.db.root / "backups" / backup["name"]) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    if change == "altered_database":
        contents["taller.sqlite3"] += b"ALTERED"
    elif change == "unlisted_file":
        contents["unlisted.txt"] = b"UNLISTED"
    else:
        contents["secure/synthetic.key"] = b"NOT A REAL KEY"
        manifest = json.loads(contents["manifest.json"])
        manifest["files"]["secure/synthetic.key"] = "0" * 64
        contents["manifest.json"] = json.dumps(manifest).encode()
    changed = tmp_path / "altered.canamo"
    with zipfile.ZipFile(changed, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError):
        packager.inspect_backup(changed)
