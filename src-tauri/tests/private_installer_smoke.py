"""Test initial-data installation/reinstallation in a disposable Windows runner.

Only creates synthetic demo data. Never accepts a real backup or a custom data path.
The application installer is reused unchanged from the verified prior build.
"""

import contextlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from package_private_installer import digest  # noqa: E402
from verify_sidecar import Service  # noqa: E402

NSIS_URL = "https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.11/nsis-3.11.zip"
NSIS_SHA256 = "c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1"


@contextlib.contextmanager
def service(executable, directory):
    client = Service([str(executable)], directory)
    try:
        yield client
        client.shutdown()
    finally:
        if client.process.poll() is None:
            client.process.kill()
            client.process.wait(timeout=30)


def files(root):
    return {str(p.relative_to(root)): digest(p) for p in root.rglob("*") if p.is_file()}


def rows(root):
    with sqlite3.connect((root / "taller.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        return {
            table: sorted(db.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
            for table in ("customers", "vehicles", "documents", "series", "fiscal_records")
        }


def main():
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Esta prueba usa exclusivamente una cuenta Windows desechable de CI.")
    destination = Path(os.environ["LOCALAPPDATA"]) / "es.tallereselcanamo.desktop.dev"
    if destination.exists():
        raise SystemExit("Ya existen datos. No se ejecuta ni se sustituye nada.")
    proof = json.loads((ROOT / "reports/windows-reused-artifact.json").read_text())
    installer = Path(proof["installer_path"]).resolve()
    report = ROOT / "reports/windows-initial-data.json"
    report.unlink(missing_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="canamo-initial-ci-") as temporary:
        work = Path(temporary)
        installation = work / "Cáñamo instalación privada"
        try:
            archive = work / "nsis.zip"
            urllib.request.urlretrieve(NSIS_URL, archive)
            assert digest(archive) == NSIS_SHA256
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(work / "compiler")
            compiler = work / "compiler/nsis-3.11/makensis.exe"
            extracted = work / "original"
            subprocess.run(
                ["7z", "x", str(installer), "-o" + str(extracted), "-y"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            executable = extracted / "canamo-service.exe"
            original = work / "synthetic-source"
            backup = work / "synthetic.canamo"
            with service(executable, original) as api:
                api.call("demo.load")
                api.download(api.call("backup.create"), backup)
            expected = rows(original)
            wrapped = work / "Instalar-Taller-Canamo.exe"
            bundle = work / "bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/package_private_installer.py"),
                    "--installer",
                    str(installer),
                    "--installer-sha256",
                    digest(installer),
                    "--backup",
                    str(backup),
                    "--output",
                    str(wrapped),
                    "--work",
                    str(bundle),
                    "--makensis",
                    str(compiler),
                ],
                check=True,
            )
            subprocess.run([str(wrapped), "/S", "/D=" + str(installation)], check=True, timeout=240)
            assert rows(destination) == expected
            receipt = json.loads(
                (destination / ".initial-data-loaded.json").read_text(encoding="utf-8-sig")
            )
            assert receipt["loaded"] and not receipt["fiscal_activated"]
            for name in ("taller-canamo.exe", "canamo-service.exe"):
                assert digest(installation / name) == digest(extracted / name)
            checks.append("initial_restore_and_unchanged_binaries")
            with service(installation / "canamo-service.exe", destination) as api:
                assert api.call("bootstrap")["recovery"]["blocked"] is True
                api.call(
                    "customers.save",
                    {"data": {"name": "Alta sintética posterior a la instalación"}},
                )
            before = files(destination)
            subprocess.run([str(wrapped), "/S", "/D=" + str(installation)], check=True, timeout=240)
            assert files(destination) == before
            checks.append("reinstall_preserves_every_existing_data_file")

            # Save the synthetic installed workshop before failure injection.
            destination.rename(work / "saved-synthetic-data")
            spec = json.loads((bundle / "seed.json").read_text())
            spec["visible_counts"]["customers"] += 1
            (bundle / "seed.json").write_text(json.dumps(spec), encoding="utf-8")
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(bundle / "seed.ps1"),
                    "-Service",
                    str(installation / "canamo-service.exe"),
                    "-Bundle",
                    str(bundle),
                ],
                timeout=180,
                capture_output=True,
            )
            assert result.returncode != 0 and not destination.exists()
            assert not list(destination.parent.glob(destination.name + ".initial-*"))
            checks.append("failed_validation_leaves_no_partial_workshop")
            destination.mkdir()
            sentinel = destination / "existing-file.txt"
            sentinel.write_text("SYNTHETIC EXISTING DATA")
            result = subprocess.run([str(wrapped), "/S", "/D=" + str(installation)], timeout=240)
            assert result.returncode != 0 and sentinel.read_text() == "SYNTHETIC EXISTING DATA"
            assert list(destination.iterdir()) == [sentinel]
            checks.append("existing_folder_without_database_is_not_replaced")
            report.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "synthetic_only": True,
                        "checks": checks,
                        "counts": receipt["counts"],
                        "original_installer_sha256": digest(installer),
                        "nsis_sha256": NSIS_SHA256,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"ok": True, "checks": checks}))
        finally:
            uninstaller = installation / "uninstall.exe"
            if uninstaller.exists():
                subprocess.run(
                    [str(uninstaller), "/S", "_?=" + str(installation)], timeout=90, check=True
                )
            if destination.exists():
                shutil.rmtree(destination)


if __name__ == "__main__":
    main()
