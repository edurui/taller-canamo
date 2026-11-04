"""Accept a prior full Windows build for testing without rebuilding its bytes.

The original job may have failed only in desktop automation. All build, integrity,
Python, browser and installed-service checks must already have passed.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from xml.etree import ElementTree


RUNTIME_PATHS = (
    ".gitignore",
    "scripts/quality.py",
    ".prettierrc.json",
    ".prettierignore",
    "eslint.config.mjs",
    "backend/taller",
    "frontend",
    "web",
    "public",
    "tools",
    "src-tauri/src",
    "src-tauri/icons",
    "src-tauri/capabilities",
    "src-tauri/Cargo.toml",
    "src-tauri/Cargo.lock",
    "src-tauri/tauri.conf.json",
    "src-tauri/build.rs",
    "src-tauri/rust-toolchain.toml",
    ".gitattributes",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "index.html",
    "tsconfig.json",
    "vite.config.ts",
    "requirements.txt",
    "requirements.lock",
    "requirements-dev.txt",
    "requirements-dev.lock",
    "requirements-assistant.txt",
    "requirements-assistant.lock",
    "scripts/sidecar_entry.py",
    "scripts/build_desktop.py",
    "scripts/verify_sidecar.py",
    "scripts/prepare_access_runtime.py",
    "scripts/prepare_assistant_models.py",
    "scripts/prepare_licenses.py",
    "scripts/assistant-models.lock.json",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def passed_python_suite(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    count = 0
    for suite in suites:
        cases = list(suite.iter("testcase"))
        require(int(suite.attrib["tests"]) == len(cases), "Informe Python incompleto: " + path.name)
        require(
            all(int(suite.attrib.get(key, "0")) == 0 for key in ("failures", "errors", "skipped"))
            and not any(
                case.find(tag) is not None
                for case in cases
                for tag in ("failure", "error", "skipped")
            ),
            "La batería Python tiene fallos u omisiones: " + path.name,
        )
        count += len(cases)
    require(count > 0, "No hay pruebas Python: " + path.name)
    return count


def passed_browser_suite(path):
    report = json.loads(path.read_text(encoding="utf-8-sig"))

    def cases(suite):
        return [test for spec in suite.get("specs", []) for test in spec["tests"]] + [
            test for child in suite.get("suites", []) for test in cases(child)
        ]

    tests = cases(report)
    stats = report["stats"]
    require(
        tests
        and stats["expected"] == len(tests)
        and all(stats[key] == 0 for key in ("unexpected", "skipped", "flaky"))
        and all(
            test["status"] == "expected"
            and len(test["results"]) == 1
            and test["results"][0]["status"] == "passed"
            for test in tests
        ),
        "La batería de navegador está incompleta o tiene fallos, omisiones o reintentos: "
        + path.name,
    )
    return len(tests)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify(root, run_id, source_sha):
    destination = Path("reports/windows-reused-artifact.json")
    destination.unlink(missing_ok=True)
    if not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("Identificador de build o SHA no válido.")
    repository = os.environ["GITHUB_REPOSITORY"]
    run = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"], text=True
        )
    )
    require(
        run["head_sha"] == source_sha and run["status"] == "completed",
        "El run no corresponde al commit completo.",
    )
    require(run["conclusion"] in ("success", "failure"), "El build se canceló o no terminó.")
    require(
        run["path"] == ".github/workflows/windows-build.yml",
        "Workflow distinto del build completo.",
    )
    jobs = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs"], text=True
        )
    )["jobs"]
    require(len(jobs) == 1, "Número inesperado de jobs.")
    steps = {step["name"]: step["conclusion"] for step in jobs[0]["steps"]}
    for name in (
        "Test and build selected installer",
        "Install under a user path and verify bundled service",
        "Store installer and verification evidence for review",
    ):
        require(steps[name] == "success", "Paso obligatorio fallido: " + name)
    failed = {name for name, result in steps.items() if result == "failure"}
    require(
        failed <= {"Tauri UI with WebView2 and packaged service in the disposable runner account"},
        "Falló un paso distinto de la prueba nativa.",
    )
    manifests = list(root.rglob("windows-artifacts.json"))
    require(len(manifests) == 1, "Debe existir un único manifiesto del build.")
    artifact = manifests[0].parent.parent
    manifest = json.loads(manifests[0].read_text(encoding="utf-8-sig"))
    require(
        manifest.get("input_manifest_version") == 2,
        "El manifiesto antiguo no cubre todos los recursos; reconstruye el candidato.",
    )
    require(manifest["target"] == "x86_64-pc-windows-msvc", "Target distinto de Windows x64 MSVC.")
    require(
        manifest["embedded_release_policy"]["edition"] == "release_candidate",
        "No es un candidato de entrega.",
    )
    suites = {
        filename: passed_python_suite(artifact / "reports" / filename)
        for filename in ("windows-pytest.xml", "windows-preflight.xml")
    }
    suites.update(
        {
            filename: passed_browser_suite(artifact / "reports" / filename)
            for filename in ("e2e/results.json", "windows-e2e-preflight.json")
        }
    )
    for filename in (
        "sidecar-functional.json",
        "windows-staged-sidecar.json",
        "windows-installed-sidecar.json",
    ):
        require(
            json.loads((artifact / "reports" / filename).read_text(encoding="utf-8-sig"))["ok"]
            is True,
            "Diagnóstico fallido: " + filename,
        )
    sidecar = json.loads(
        (artifact / "reports/sidecar-functional.json").read_text(encoding="utf-8-sig")
    )
    require(
        sidecar["packaged"] and sidecar["platform"] == "win32",
        "El servicio no se probó empaquetado en Windows.",
    )
    require(
        sidecar["build_policy"]["policy_sha256"] == manifest["embedded_release_policy"]["sha256"],
        "La política del servicio es distinta.",
    )
    installers = list(artifact.rglob("*-setup.exe"))
    require(len(installers) == 1, "Debe existir un único instalador.")
    installer = installers[0]
    specification = next(
        item
        for item in manifest["artifacts"]
        if item["path"].replace("\\", "/").split("/")[-1] == installer.name
    )
    require(
        installer.stat().st_size == specification["bytes"]
        and digest(installer) == specification["sha256"],
        "El instalador no coincide con el build completo.",
    )
    checked = set()
    with tempfile.TemporaryDirectory(prefix="canamo-verified-source-") as temporary:
        source = Path(temporary) / "source"
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=true",
                "worktree",
                "add",
                "--detach",
                str(source),
                source_sha,
            ],
            check=True,
            capture_output=True,
        )
        try:
            tracked = set(
                subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"])
                .decode()
                .split("\0")
            ) - {""}
            current = set(
                subprocess.check_output(
                    [
                        "git",
                        "ls-files",
                        "--cached",
                        "--others",
                        "--exclude-standard",
                        "-z",
                        "--",
                        *RUNTIME_PATHS,
                    ]
                )
                .decode()
                .split("\0")
            ) - {""}
            inputs = {
                raw.replace("\\", "/"): expected
                for raw, expected in manifest["source_hashes"].items()
            }
            require(
                current <= inputs.keys(),
                "Hay entradas de ejecución nuevas o ausentes del manifiesto: "
                + ", ".join(sorted(current - inputs.keys())),
            )
            for path, expected in inputs.items():
                require(
                    not PurePosixPath(path).is_absolute()
                    and ".." not in PurePosixPath(path).parts
                    and ":" not in path,
                    "Ruta no válida en el manifiesto.",
                )
                if path in tracked:
                    require(digest(source / path) == expected, "El commit no coincide: " + path)
                    require(
                        digest(Path(path)) == expected,
                        "Cambió una entrada de la aplicación: " + path,
                    )
                    checked.add(path)
            require(
                {
                    "backend/taller/app.py",
                    "backend/taller/release-policy.json",
                    "frontend/app.tsx",
                    "frontend/core.tsx",
                    "frontend/controls.tsx",
                    "web/style.css",
                    "src-tauri/src/main.rs",
                    "src-tauri/Cargo.toml",
                    "scripts/build_desktop.py",
                }
                <= checked,
                "Faltan entradas obligatorias en el manifiesto.",
            )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(source)],
                check=True,
                capture_output=True,
            )
    proof = {
        "ok": True,
        "build_run_id": run_id,
        "build_source_sha": source_sha,
        "original_workflow_conclusion": run["conclusion"],
        "original_failed_steps": sorted(failed),
        "installer_path": str(installer.resolve()),
        "sha256": specification["sha256"],
        "bytes": specification["bytes"],
        "runtime_inputs_matched": len(checked),
        "passed_suites": suites,
        "manifest_path": str(manifests[0].resolve()),
        "rebuilt": False,
    }
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "unchanged_installer_sha256": proof["sha256"],
                "runtime_inputs_matched": len(checked),
            }
        )
    )


if __name__ == "__main__":
    verify(Path("build-artifact"), os.environ["BUILD_RUN_ID"], os.environ["BUILD_SOURCE_SHA"])
