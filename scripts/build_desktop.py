"""Build and verify the bundled service and the Windows NSIS development installer."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verify_sidecar import verify

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(command, *, cwd=ROOT, env=None, timeout=None):
    print("+", subprocess.list2cmdline([str(part) for part in command]), flush=True)
    subprocess.run(command, cwd=cwd, env=env, timeout=timeout, check=True)


def build_input_hashes(include_desktop):
    paths = [path for path in (ROOT / "backend" / "taller").rglob("*")
             if path.is_file() and path.suffix in {".py", ".xsd", ".wsdl", ".json", ".ttf", ".otf"}]
    paths.extend(ROOT / "scripts" / name for name in ("sidecar_entry.py", "build_desktop.py", "verify_sidecar.py"))
    paths.extend(ROOT / name for name in ("package.json", "requirements.lock", "requirements-dev.lock", "pyproject.toml")
                 if (ROOT / name).is_file())
    if include_desktop:
        for directory in ("frontend", "public", "src-tauri/src", "src-tauri/icons", "src-tauri/capabilities"):
            paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
        paths.extend(ROOT / name for name in ("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts",
                     "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json", "src-tauri/build.rs", "src-tauri/rust-toolchain.toml")
                     if (ROOT / name).is_file())
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def build_sidecar(target, release_policy):
    name = "canamo-service-" + target
    output = ROOT / "src-tauri" / "binaries"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
               "--name", name, "--paths", str(ROOT / "backend"), "--collect-all", "tzdata",
               "--collect-submodules", "lxml", "--collect-submodules", "reportlab", "--hidden-import", "taller.pdf",
               "--collect-all", "saxonche", "--collect-all", "vosk", "--collect-all", "rapidocr", "--collect-all", "onnxruntime",
               "--add-data", str(ROOT / "backend" / "taller" / "schemas") + os.pathsep + "taller/schemas",
               "--add-data", str(ROOT / "backend" / "taller" / "access_runtime") + os.pathsep + "taller/access_runtime",
               "--add-data", str(ROOT / "backend" / "taller" / "assistant_models") + os.pathsep + "taller/assistant_models",
               "--add-data", str(ROOT / "backend" / "taller" / "legal") + os.pathsep + "taller/legal",
               "--add-data", str(ROOT / "backend" / "taller" / "fonts") + os.pathsep + "taller/fonts",
               "--add-data", str(release_policy) + os.pathsep + "taller",
               "--distpath", str(output), "--workpath", str(ROOT / "build" / "pyinstaller"),
               "--specpath", str(ROOT / "build"), str(ROOT / "scripts" / "sidecar_entry.py")]
    run(command)
    executable = output / (name + (".exe" if sys.platform == "win32" else ""))
    verify([str(executable)], ROOT / "reports" / "sidecar-functional.json", packaged=True,
           expected_policy={**json.loads(release_policy.read_text(encoding="utf-8")), "sha256": sha256(release_policy)})
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar-only", action="store_true", help="Construye y verifica solo el servicio para el sistema actual; también admite Linux.")
    parser.add_argument("--release-candidate", action="store_true", help="Solo Windows MSVC: incorpora política de candidato antes de construir y verificar los mismos bytes; no habilita producción ni crea un expediente.")
    args = parser.parse_args()
    if args.release_candidate and (sys.platform != "win32" or args.sidecar_only):
        raise SystemExit("Un candidato exige la construcción Windows completa. Linux y --sidecar-only permanecen en desarrollo.")
    if sys.platform != "win32" and not args.sidecar_only:
        raise SystemExit("El instalador Windows se construye desde Windows x64. Para verificar el servicio en Linux usa --sidecar-only.")
    report = ROOT / "reports" / ("windows-artifacts.json" if not args.sidecar_only else "sidecar-artifact.json")
    # A failed rebuild must not leave an earlier acceptance report referring to
    # an artifact path that this invocation may have overwritten.
    report.unlink(missing_ok=True)
    rustc = shutil.which("rustc")
    if not rustc:
        raise SystemExit("Falta Rust. Consulta docs/BUILD-WINDOWS.md.")
    host = subprocess.check_output([rustc, "-vV"], cwd=ROOT / "src-tauri", text=True)
    target = next(line.split(": ", 1)[1] for line in host.splitlines() if line.startswith("host: "))
    if not args.sidecar_only and target != "x86_64-pc-windows-msvc":
        raise SystemExit("El instalador admite Windows 11 x64 MSVC.")
    run([sys.executable, str(ROOT / "scripts" / "prepare_access_runtime.py")])
    run([sys.executable, str(ROOT / "scripts" / "prepare_assistant_models.py")])
    run([sys.executable, str(ROOT / "scripts" / "prepare_licenses.py")])
    source_hashes = build_input_hashes(include_desktop=not args.sidecar_only)
    if not args.sidecar_only:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        cargo = shutil.which("cargo")
        if not npm or not cargo:
            raise SystemExit("Falta npm o cargo. Consulta docs/BUILD-WINDOWS.md.")
        for filename in ("package-lock.json", "requirements-dev.lock", "src-tauri/Cargo.lock"):
            if not (ROOT / filename).is_file():
                raise SystemExit(f"Falta el lock reproducible {filename}.")
        run([sys.executable, "-m", "pytest"])
        run([npm, "run", "typecheck"])
        run([npm, "run", "typecheck:e2e"])
        run([npm, "run", "build"])
        run([npm, "run", "test:e2e"])
    source_policy = json.loads((ROOT / "backend" / "taller" / "release-policy.json").read_text(encoding="utf-8"))
    expected_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    if source_policy != {"format_version": 1, "application_version": expected_version, "edition": "development"}:
        raise SystemExit("La política fuente debe ser development y coincidir con la versión. No se modifican constantes de producción para construir.")
    policy = {**source_policy, "edition": "release_candidate" if args.release_candidate else "development"}
    with tempfile.TemporaryDirectory(prefix="canamo-embedded-policy-") as directory:
        release_policy = Path(directory) / "release-policy.json"
        release_policy.write_text(json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        policy_hash = sha256(release_policy)
        executable = build_sidecar(target, release_policy)
    if not args.sidecar_only:
        run([cargo, "test", "--locked", "--no-default-features", "--lib"], cwd=ROOT / "src-tauri",
            env={**os.environ, "CANAMO_TEST_PYTHON": sys.executable})
        installer_directory = ROOT / "src-tauri" / "target" / "release" / "bundle" / "nsis"
        previous_installers = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in installer_directory.glob("*-setup.exe")}
        run([npm, "run", "tauri", "--", "build", "--", "--locked"])
        # Diagnose the staged app, including the sidecar filename Tauri removed
        # the target triple from, before accepting the NSIS artifact.
        diagnostic_report = ROOT / "reports" / "windows-staged-sidecar.json"
        diagnostic_report.unlink(missing_ok=True)
        run([str(ROOT / "src-tauri" / "target" / "release" / "taller-canamo.exe"), "--diagnose-sidecar", str(diagnostic_report)], timeout=120)
        result = json.loads(diagnostic_report.read_text(encoding="utf-8"))
        if not result["ok"]:
            raise SystemExit("El ejecutable Tauri empaquetado no ha pasado el diagnóstico: " + str(result))
        installers = [path for path in installer_directory.glob("*-setup.exe")
                      if previous_installers.get(path) != (path.stat().st_mtime_ns, path.stat().st_size)]
        if not installers:
            raise SystemExit("No se ha generado ningún instalador NSIS.")
        artifacts = [executable, ROOT / "src-tauri" / "target" / "release" / "taller-canamo.exe",
                     ROOT / "src-tauri" / "target" / "release" / "canamo-service.exe", *installers]
    else:
        artifacts = [executable]
    manifest = [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "bytes": path.stat().st_size} for path in artifacts]
    report.parent.mkdir(exist_ok=True)
    if build_input_hashes(include_desktop=not args.sidecar_only) != source_hashes:
        raise SystemExit("El código o los recursos cambiaron durante el empaquetado. El artefacto no se acepta: repite la construcción con las fuentes estables.")
    dependencies = {package.metadata["Name"]: package.version for package in importlib.metadata.distributions()}
    report.write_text(json.dumps({"target": target, "python": sys.version, "artifacts": manifest,
                                 "embedded_release_policy": {**policy, "sha256": policy_hash},
                                 "source_hashes": source_hashes, "build_dependencies": dependencies},
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Artefactos verificados y huellas:", report)


if __name__ == "__main__":
    main()
