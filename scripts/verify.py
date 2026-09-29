"""Run the integrated local checks and retain commands, exits, logs and input hashes.

No user data is opened: pytest/Playwright own their temporary synthetic directories.
Windows installation, physical printing and authenticated AEAT remain separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_hashes():
    result = {}
    extensions = {".py", ".tsx", ".ts", ".css", ".rs", ".xsd", ".xsl", ".xslt", ".xml", ".json", ".js", ".cjs", ".mjs", ".html", ".toml", ".java", ".lock", ".txt", ".md", ".wav", ".png", ".csv", ".sh", ".cmd", ".ps1", ".yml", ".yaml", ".ttf", ".otf"}
    for folder in ("backend", "frontend", "web", "public", "scripts", "tests", "e2e", "src-tauri/src", "src-tauri/capabilities", "tools"):
        for path in sorted((ROOT / folder).rglob("*")):
            excluded = {"__pycache__"} | ({"assistant_models", "access_runtime", "legal"} if folder=="backend" else set())
            if path.is_file() and path.suffix in extensions and not excluded.intersection(path.relative_to(ROOT/folder).parts):
                result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    files = [path.relative_to(ROOT).as_posix() for path in ROOT.iterdir() if path.is_file() and path.suffix in extensions]
    files += [".nvmrc", "src-tauri/Cargo.lock", "src-tauri/Cargo.toml", "src-tauri/build.rs", "src-tauri/tauri.conf.json", "src-tauri/rust-toolchain.toml", "backend/taller/assistant_models/manifest.json", "backend/taller/access_runtime/manifest.json", "backend/taller/legal/manifest.json"]
    for name in files:
        path = ROOT / name
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/local-verification")
    args = parser.parse_args()
    output = ROOT / args.report
    output.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        parser.error("Falta Node/npm.")
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"os": platform.platform(), "python": sys.version, "executable": sys.executable},
        "source_sha256": {}, "commands": [],
        "limits": ["No acredita instalación Windows, impresión física ni aceptación autenticada de AEAT.",
                   "TypeScript strict está activado; varios contratos heredados aún usan Row/any.",
                   "axe comprueba las pantallas recorridas, no certifica accesibilidad completa."],
    }
    report["source_sha256"] = source_hashes()
    commands = [
        ("python-dependencies", [sys.executable, "-m", "pip", "check"]),
        ("pytest", [sys.executable, "-m", "pytest", "--junitxml=" + str(output / "pytest.xml")]),
        ("typescript", [npm, "run", "typecheck"]),
        ("e2e-typescript", [npm, "run", "typecheck:e2e"]),
        ("vite", [npm, "run", "build"]),
        ("e2e", [npm, "run", "test:e2e"]),
    ]
    failed = False
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)
    env["NO_COLOR"] = "1"
    for label, command in commands:
        started = time.monotonic()
        print(f"[{label}] {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        (output / (label + ".log")).write_bytes(result.stdout)
        report["commands"].append({"name": label, "argv": command, "exit_code": result.returncode,
                                   "elapsed_seconds": round(time.monotonic() - started, 3), "log": label + ".log"})
        print(f"[{label}] código {result.returncode}; {report['commands'][-1]['elapsed_seconds']} s", flush=True)
        failed = failed or result.returncode != 0
        # Do not run E2E against stale dist if the build has failed.
        if label == "vite" and result.returncode:
            break
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    after = source_hashes()
    report["sources_changed_during_run"] = sorted(
        name for name in report["source_sha256"].keys() | after.keys()
        if report["source_sha256"].get(name) != after.get(name))
    if report["sources_changed_during_run"]:
        print("Se modificaron fuentes durante la ejecución. Los comandos conservan su resultado, pero la batería no acredita una revisión única.", flush=True)
        failed = True
    report["passed"] = not failed
    report["artifacts_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "dist").rglob("*")) if path.is_file()
    }
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
