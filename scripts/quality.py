"""Run the pinned source linters/formatters without modifying files or user data."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_PATHS = ["backend/taller", "scripts", "tests", "src-tauri/tests"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("reports/quality"))
    args = parser.parse_args()
    output = ROOT / args.report
    output.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    cargo = shutil.which("cargo") or str(
        Path.home() / ".cargo/bin" / ("cargo.exe" if sys.platform == "win32" else "cargo")
    )
    if not npm or not Path(cargo).is_file():
        parser.error("Falta npm o cargo; instala las herramientas de desarrollo documentadas.")
    commands = [
        ("prettier", [npm, "run", "format:check"], ROOT),
        ("eslint", [npm, "run", "lint"], ROOT),
        ("ruff-lint", [sys.executable, "-m", "ruff", "check", *PYTHON_PATHS], ROOT),
        ("ruff-format", [sys.executable, "-m", "ruff", "format", "--check", *PYTHON_PATHS], ROOT),
        ("rustfmt", [cargo, "fmt", "--all", "--", "--check"], ROOT / "src-tauri"),
        (
            "clippy",
            [cargo, "clippy", "--locked", "--no-default-features", "--lib", "--", "-D", "warnings"],
            ROOT / "src-tauri",
        ),
    ]
    report = {"ok": False, "commands": []}
    destination = output / "result.json"
    # An interrupted invocation must not leave an old successful report.
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for label, command, directory in commands:
        print(f"[{label}] {subprocess.list2cmdline(command)}", flush=True)
        started = time.monotonic()
        result = subprocess.run(
            command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (output / f"{label}.log").write_bytes(result.stdout)
        report["commands"].append(
            {
                "name": label,
                "argv": command,
                "exit_code": result.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        )
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            print(result.stdout.decode("utf-8", errors="replace"), flush=True)
            return result.returncode
    report["ok"] = True
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Formato y lint correctos.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
