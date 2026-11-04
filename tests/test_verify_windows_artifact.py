"""Synthetic guard tests only; these do not accept or execute a Windows build."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def artifact_guard(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/verify_windows_artifact.py"
    spec = importlib.util.spec_from_file_location("artifact_guard", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "synthetic/example")
    sha = "a" * 40
    root = tmp_path / "artifact"
    reports = root / "reports"
    reports.mkdir(parents=True)

    def write(name, value):
        path = reports / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    for name, count in [("windows-pytest.xml", 819), ("windows-preflight.xml", 6)]:
        cases = "".join(f'<testcase name="synthetic-{index}"/>' for index in range(count))
        (reports / name).write_text(
            f'<testsuite tests="{count}" failures="0" errors="0" skipped="0">{cases}</testsuite>'
        )
    for name, count in [("e2e/results.json", 166), ("windows-e2e-preflight.json", 13)]:
        write(
            name,
            {
                "stats": {"expected": count, "unexpected": 0, "skipped": 0, "flaky": 0},
                "suites": [
                    {
                        "specs": [
                            {"tests": [{"status": "expected", "results": [{"status": "passed"}]}]}
                            for _ in range(count)
                        ]
                    }
                ],
            },
        )
    for name in ("windows-staged-sidecar.json", "windows-installed-sidecar.json"):
        write(name, {"ok": True})
    write(
        "quality/result.json",
        {
            "ok": True,
            "commands": [
                {"name": name, "exit_code": 0}
                for name in ("prettier", "eslint", "ruff-lint", "ruff-format", "rustfmt", "clippy")
            ],
        },
    )
    write(
        "sidecar-functional.json",
        {
            "ok": True,
            "packaged": True,
            "platform": "win32",
            "build_policy": {"policy_sha256": "policy"},
        },
    )
    installer = root / "synthetic-setup.exe"
    installer.write_bytes(b"NOT AN EXECUTABLE: guard fixture")
    sources = {
        name: b"synthetic source"
        for name in (
            "backend/taller/app.py",
            "backend/taller/release-policy.json",
            "frontend/app.tsx",
            "frontend/core.tsx",
            "frontend/controls.tsx",
            "web/style.css",
            "src-tauri/src/main.rs",
            "src-tauri/Cargo.toml",
            "scripts/build_desktop.py",
        )
    }
    for name, content in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    write(
        "windows-artifacts.json",
        {
            "input_manifest_version": 2,
            "target": "x86_64-pc-windows-msvc",
            "embedded_release_policy": {"edition": "release_candidate", "sha256": "policy"},
            "artifacts": [
                {
                    "path": str(installer),
                    "bytes": installer.stat().st_size,
                    "sha256": module.digest(installer),
                }
            ],
            "source_hashes": {name: module.digest(tmp_path / name) for name in sources},
        },
    )
    run = {
        "head_sha": sha,
        "status": "completed",
        "conclusion": "failure",
        "path": ".github/workflows/windows-build.yml",
    }
    steps = [
        {"name": name, "conclusion": "success"}
        for name in (
            "Test and build selected installer",
            "Install under a user path and verify bundled service",
            "Store installer and verification evidence for review",
        )
    ]
    steps.append(
        {
            "name": "Tauri UI with WebView2 and packaged service in the disposable runner account",
            "conclusion": "failure",
        }
    )

    def output(command, **kwargs):
        if command[0] == "git":
            extra = (
                ["frontend/new.tsx"]
                if command[1] == "ls-files" and Path("frontend/new.tsx").exists()
                else []
            )
            return ("\0".join([*sources, *extra]) + "\0").encode()
        return json.dumps({"jobs": [{"steps": steps}]} if command[-1].endswith("/jobs") else run)

    def worktree(command, **kwargs):
        if "remove" in command:
            return
        destination = Path(command[-2])
        for name, content in sources.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    monkeypatch.setattr(module.subprocess, "check_output", output)
    monkeypatch.setattr(module.subprocess, "run", worktree)
    proof = tmp_path / "reports/windows-reused-artifact.json"
    proof.parent.mkdir()
    proof.write_text('{"obsolete_acceptance":true}')
    return module, root, sha, installer, reports, steps, run, proof


def test_unchanged_build_can_be_reused_only_for_new_desktop_verification(artifact_guard):
    module, root, sha, _, _, _, _, proof = artifact_guard
    module.verify(root, "123", sha)
    result = json.loads(proof.read_text())
    assert result["ok"] and result["rebuilt"] is False
    assert result["original_workflow_conclusion"] == "failure"
    assert result["scope"] == "build-and-installed-service"
    assert result["pending_gates"] == ["native-ui"]


def test_build_checkpoint_keeps_failed_installation_pending(artifact_guard):
    module, root, sha, _, reports, steps, _, proof = artifact_guard
    steps[1]["conclusion"] = "failure"
    (reports / "windows-installed-sidecar.json").unlink()
    with pytest.raises(ValueError, match="Paso obligatorio"):
        module.verify(root, "123", sha)
    assert not proof.exists()
    module.verify(root, "123", sha, through_build=True)
    result = json.loads(proof.read_text())
    assert result["scope"] == "build" and result["rebuilt"] is False
    assert result["pending_gates"] == ["installation", "native-ui"]


@pytest.mark.parametrize(
    "damage",
    [
        "installer",
        "python_failure",
        "skipped_browser",
        "source",
        "other_failed_step",
        "wrong_commit",
        "wrong_policy",
        "legacy_manifest",
        "missing_python_cases",
        "browser_retry",
        "css",
        "unlisted_source",
        "failed_build",
        "missing_quality",
        "failed_quality",
        "staged_diagnostic",
    ],
)
@pytest.mark.parametrize("through_build", [False, True])
def test_rejects_damage_and_removes_stale_acceptance(artifact_guard, damage, through_build):
    module, root, sha, installer, reports, steps, run, proof = artifact_guard
    if damage == "installer":
        installer.write_bytes(b"TAMPERED")
    elif damage == "python_failure":
        (reports / "windows-pytest.xml").write_text('<testsuite tests="819" failures="1"/>')
    elif damage == "skipped_browser":
        (reports / "e2e/results.json").write_text(
            json.dumps({"stats": {"expected": 166, "unexpected": 0, "skipped": 1, "flaky": 0}})
        )
    elif damage == "source":
        Path("frontend/app.tsx").write_text("changed after the accepted build")
    elif damage == "other_failed_step":
        steps.append({"name": "Unknown prerequisite", "conclusion": "failure"})
    elif damage == "wrong_commit":
        run["head_sha"] = "b" * 40
    elif damage == "wrong_policy":
        path = reports / "sidecar-functional.json"
        value = json.loads(path.read_text())
        value["build_policy"]["policy_sha256"] = "another policy"
        path.write_text(json.dumps(value))
    elif damage == "legacy_manifest":
        path = reports / "windows-artifacts.json"
        value = json.loads(path.read_text())
        del value["input_manifest_version"]
        path.write_text(json.dumps(value))
    elif damage == "missing_python_cases":
        (reports / "windows-pytest.xml").write_text('<testsuite tests="819" failures="0"/>')
    elif damage == "browser_retry":
        path = reports / "e2e/results.json"
        value = json.loads(path.read_text())
        value["suites"][0]["specs"][0]["tests"][0]["results"].insert(0, {"status": "failed"})
        path.write_text(json.dumps(value))
    elif damage == "css":
        Path("web/style.css").write_text("body { color: transparent; }")
    elif damage == "unlisted_source":
        Path("frontend/new.tsx").write_text("export const changed = true;")
    elif damage == "failed_build":
        steps[0]["conclusion"] = "failure"
    elif damage in ("missing_quality", "failed_quality"):
        path = reports / "quality/result.json"
        value = json.loads(path.read_text())
        if damage == "missing_quality":
            value["commands"].pop()
        else:
            value["commands"][0]["exit_code"] = 1
        path.write_text(json.dumps(value))
    elif damage == "staged_diagnostic":
        (reports / "windows-staged-sidecar.json").write_text('{"ok":false}')
    with pytest.raises(ValueError):
        module.verify(root, "123", sha, through_build=through_build)
    assert not proof.exists()
