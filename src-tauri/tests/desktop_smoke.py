"""Real Tauri/WebDriver smoke. No mock RPC and no driver bundled in the app.

Linux: --xvfb isolates display; the script creates its own D-Bus/data session.
Windows: use a clean test account and matching msedgedriver; never real data.
"""

import argparse
import base64
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


@contextmanager
def ci_webview_debugging(application, port, output):
    """Temporary, app-specific HKLM policy for elevated disposable GitHub runners.

    WebView2 150+ ignores environment overrides from elevated hosts. This does
    not change the application, runtime version or production/user configuration.
    https://github.com/MicrosoftEdge/WebView2Feedback/issues/5640
    """
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("La política WebView2 de pruebas solo se permite en GitHub Windows.")
    import ctypes
    import winreg

    name = application.name
    key_path = r"Software\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments"
    with winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        key_path,
        0,
        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
    ) as key:
        try:
            original = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            original = None
        evidence = {
            "application": name,
            "port": port,
            "elevated": bool(ctypes.windll.shell32.IsUserAnAdmin()),
            "channel": "HKLM app-specific AdditionalBrowserArguments",
            "original_value_present": original is not None,
            "restored": False,
        }
        report = output / "webview-debug-policy.json"
        report.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f"--remote-debugging-port={port}")
            yield
        finally:
            if original is None:
                winreg.DeleteValue(key, name)
            else:
                winreg.SetValueEx(key, name, 0, original[1], original[0])
            evidence["restored"] = True
            report.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def artifact_metadata(application):
    files = [
        application.resolve(),
        application.resolve().with_name(
            "canamo-service.exe" if sys.platform == "win32" else "canamo-service"
        ),
    ]
    result = []
    for path in files:
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        result.append({"path": str(path), "bytes": path.stat().st_size, "sha256": checksum})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--driver", default="tauri-driver")
    parser.add_argument("--native-driver", required=True)
    parser.add_argument("--xvfb")
    parser.add_argument("--isolated-windows-account", action="store_true")
    parser.add_argument(
        "--ci-webview-policy",
        action="store_true",
        help="Solo GitHub Windows: política HKLM temporal para depurar el EXE en un runner elevado.",
    )
    parser.add_argument(
        "--attach-edge",
        action="store_true",
        help="Solo Windows: inicia el EXE normalmente y conecta Edge Driver al WebView2 real ya disponible.",
    )
    parser.add_argument(
        "--test-document-handlers",
        action="store_true",
        help="Solo Linux: sustituye xdg-open/lpr por receptores locales de prueba; nunca abre navegador ni imprime.",
    )
    parser.add_argument(
        "--test-save-dialog",
        action="store_true",
        help="Solo Linux/Xvfb: interactúa con el selector GTK real mediante xdotool en datos temporales.",
    )
    parser.add_argument("--output", type=Path, default=Path("reports/desktop"))
    args = parser.parse_args()
    if sys.platform == "win32" and not args.isolated_windows_account:
        parser.error(
            "Windows requiere una cuenta desechable de pruebas y --isolated-windows-account."
        )
    if args.attach_edge and sys.platform != "win32":
        parser.error("--attach-edge solo está disponible en Windows.")
    if args.ci_webview_policy and (
        not args.attach_edge
        or sys.platform != "win32"
        or os.environ.get("GITHUB_ACTIONS") != "true"
    ):
        parser.error("--ci-webview-policy requiere --attach-edge y un runner GitHub Windows.")
    if args.test_document_handlers and sys.platform != "linux":
        parser.error("Los receptores de prueba de documentos solo están implementados en Linux.")
    if args.test_save_dialog and (sys.platform != "linux" or not args.xvfb):
        parser.error("El selector automatizado requiere Linux y un Xvfb privado.")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").unlink(missing_ok=True)
    checks = []
    artifacts = artifact_metadata(args.application)
    session = None
    data_directory = None
    processes = []
    save_evidence = None
    with (
        tempfile.TemporaryDirectory(prefix="canamo-desktop-e2e-") as temporary,
        ExitStack() as cleanup,
    ):
        env = {
            **os.environ,
            "XDG_DATA_HOME": temporary + "/data",
            "XDG_CONFIG_HOME": temporary + "/config",
            "XDG_CACHE_HOME": temporary + "/cache",
        }
        runtime = Path(temporary) / "runtime"
        runtime.mkdir(mode=0o700)
        env["XDG_RUNTIME_DIR"] = str(runtime)
        if args.test_save_dialog:
            # This preference belongs only to the disposable bus/session.
            # GTK is the real installed portal backend, not a fake chooser.
            portal_config = Path(env["XDG_CONFIG_HOME"]) / "xdg-desktop-portal"
            portal_config.mkdir(parents=True)
            (portal_config / "portals.conf").write_text(
                "[preferred]\ndefault=gtk\n", encoding="utf-8"
            )
            env.update(XDG_CURRENT_DESKTOP="canamo-test", LANG="C.UTF-8", LC_ALL="C.UTF-8")
        capture = Path(temporary) / "handler-invocations.jsonl"
        handler_result = Path(temporary) / "handler-result.json"
        if args.test_document_handlers:
            handlers = Path(temporary) / "handlers"
            handlers.mkdir(mode=0o700)
            handler_result.write_text("{}", encoding="utf-8")
            receiver = """#!/usr/bin/env python3
import hashlib,json,os,sys
from pathlib import Path
program=Path(sys.argv[0]).name
target=Path(sys.argv[1])
if len(sys.argv)!=2 or not target.is_absolute() or target.suffix!='.pdf':
    raise SystemExit(3)
with target.open('rb') as source:
    magic=source.read(5)
    source.seek(0)
    checksum=hashlib.file_digest(source,'sha256').hexdigest()
with open(os.environ['CANAMO_HANDLER_CAPTURE'],'a',encoding='utf-8') as report:
    report.write(json.dumps({'program':program,'path':str(target),'bytes':target.stat().st_size,'pdf':magic==b'%PDF-','sha256':checksum})+'\\n')
status=json.loads(Path(os.environ['CANAMO_HANDLER_RESULT']).read_text())
raise SystemExit(status.get(program,0))
"""
            for name in ("xdg-open", "lpr"):
                path = handlers / name
                path.write_text(receiver, encoding="utf-8")
                path.chmod(0o700)
            env.update(
                PATH=str(handlers) + os.pathsep + os.environ.get("PATH", ""),
                CANAMO_HANDLER_CAPTURE=str(capture),
                CANAMO_HANDLER_RESULT=str(handler_result),
            )
        log = (args.output / "driver.log").open("w", encoding="utf-8")
        if sys.platform == "linux":
            # Own the private bus so its desktop helpers stop before temporary
            # data are removed. No access to the user's session services.
            bus = subprocess.Popen(
                ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
                env=env,
            )
            processes.append(bus)
            env["DBUS_SESSION_BUS_ADDRESS"] = bus.stdout.readline().strip()
        if args.xvfb:
            # Xvfb has no DRI3 device. Accelerated PDF canvas rendering may be
            # incomplete there even though the PDF itself is valid.
            env.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
            env.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
            display = subprocess.Popen(
                [args.xvfb, "-displayfd", "1", "-screen", "0", "1366x768x24", "-nolisten", "tcp"],
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
            )
            processes.append(display)
            env["DISPLAY"] = ":" + display.stdout.readline().strip()
        if args.test_save_dialog:
            subprocess.run(
                [
                    "dbus-update-activation-environment",
                    "DISPLAY",
                    "XDG_CURRENT_DESKTOP",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                    "XDG_CACHE_HOME",
                    "XDG_RUNTIME_DIR",
                    "LANG",
                    "LC_ALL",
                ],
                env=env,
                check=True,
                timeout=10,
                stdout=log,
                stderr=log,
            )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            native_port = probe.getsockname()[1]
        application_process = None
        application_started = time.monotonic()
        if args.attach_edge:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                debug_port = probe.getsockname()[1]
            # Local environment suffices for non-elevated Windows accounts.
            env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
                env.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
                + f" --remote-debugging-port={debug_port}"
            )
            if args.ci_webview_policy:
                cleanup.enter_context(
                    ci_webview_debugging(args.application, debug_port, args.output)
                )
            application_process = subprocess.Popen(
                [str(args.application.resolve())], env=env, stdout=log, stderr=log
            )
            processes.append(application_process)
            driver_command = [
                str(Path(args.native_driver).resolve()),
                f"--port={port}",
                "--verbose",
                "--log-path=" + str((args.output / "edge-driver.log").resolve()),
            ]
        else:
            driver_command = [
                args.driver,
                "--port",
                str(port),
                "--native-port",
                str(native_port),
                "--native-driver",
                args.native_driver,
            ]
        driver = subprocess.Popen(driver_command, env=env, stdout=log, stderr=log)
        processes.append(driver)
        base = f"http://127.0.0.1:{port}"

        def request(method, path, data=None, timeout=40):
            body = None if data is None else json.dumps(data).encode()
            req = urllib.request.Request(
                base + path, data=body, method=method, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as error:
                raise AssertionError(error.read().decode()) from error
            return result.get("value", result)

        def wait_for(check, timeout=30):
            until = time.monotonic() + timeout
            last = None
            while time.monotonic() < until:
                try:
                    result = check()
                    if result:
                        return result
                except (OSError, AssertionError) as error:
                    last = error
                time.sleep(0.1)
            raise AssertionError(f"La condición no se cumplió: {last}")

        def script(source, *values):
            return request(
                "POST", f"/session/{session}/execute/sync", {"script": source, "args": list(values)}
            )

        def rpc(action, params=None):
            return request(
                "POST",
                f"/session/{session}/execute/async",
                {
                    "script": "const done=arguments[arguments.length-1];window.__TAURI__.core.invoke('rpc',{action:arguments[0],params:arguments[1]}).then(done,e=>done({ok:false,error:String(e)}));",
                    "args": [action, params or {}],
                },
            )

        def invoke(command, params):
            return request(
                "POST",
                f"/session/{session}/execute/async",
                {
                    "script": "const done=arguments[arguments.length-1];window.__TAURI__.core.invoke(arguments[0],arguments[1]).then(result=>done({ok:true,result}),error=>done({ok:false,error:String(error)}));",
                    "args": [command, params],
                },
            )

        def handler_calls():
            return (
                [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
                if capture.exists()
                else []
            )

        def service_stopped():
            # WebDriver can return before the PyInstaller child finishes closing
            # SQLite. Never remove its isolated data while it can still write.
            marker = b"--data\0" + os.fsencode(data_directory) + b"\0"
            for process in Path("/proc").glob("[0-9]*/cmdline"):
                try:
                    if marker in process.read_bytes():
                        return False
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
            return True

        def click_text(text):
            return script(
                "const b=[...document.querySelectorAll('button')].filter(b=>b.textContent.trim()===arguments[0]).at(-1);if(!b)return false;b.click();return true",
                text,
            )

        def chooser_window():
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", "xdg-desktop-portal-gtk|zenity"],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return (
                result.stdout.splitlines()[-1]
                if result.returncode == 0 and result.stdout.strip()
                else None
            )

        def chooser_key(window, *keys):
            subprocess.run(
                ["xdotool", "windowfocus", "--sync", window], env=env, check=True, timeout=5
            )
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", *keys], env=env, check=True, timeout=5
            )

        try:
            wait_for(lambda: request("GET", "/status"))
            capabilities = {"tauri:options": {"application": str(args.application.resolve())}}
            if args.attach_edge:

                def webview_ready():
                    if application_process.poll() is not None:
                        raise RuntimeError(
                            f"La aplicación terminó antes de abrir WebView2: {application_process.returncode}"
                        )
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{debug_port}/json/version", timeout=1
                    ) as response:
                        return bool(json.load(response).get("webSocketDebuggerUrl"))

                wait_for(webview_ready, timeout=90)
                capabilities = {
                    "browserName": "webview2",
                    "ms:edgeOptions": {"debuggerAddress": f"127.0.0.1:{debug_port}"},
                }
            created = request(
                "POST",
                "/session",
                {"capabilities": {"alwaysMatch": capabilities}},
                timeout=120 if args.attach_edge else 40,
            )
            session = created["sessionId"]
            wait_for(
                lambda: script(
                    "return Boolean(window.__TAURI__&&document.querySelector('input[role=combobox]'))"
                )
            )
            startup_seconds = round(time.monotonic() - application_started, 3)
            if sys.platform == "linux":
                data_directory = rpc("bootstrap")["result"]["data_directory"]
                assert Path(data_directory).resolve().is_relative_to(Path(temporary).resolve())
            checks.append("Ventana Tauri real con API nativa y buscador renderizado")
            wait_for(lambda: click_text("Cargar demostración"))
            wait_for(lambda: script("return Boolean(document.querySelector('[role=dialog]'))"))
            assert click_text("Cargar demostración")
            wait_for(lambda: rpc("customers.list").get("result", {}).get("total", 0) >= 5)
            wait_for(lambda: script("return !document.querySelector('[role=dialog]')"))
            checks.append("Demostración creada desde interfaz por IPC real")
            element = request(
                "POST",
                f"/session/{session}/element",
                {"using": "css selector", "value": "input[role=combobox]"},
            )
            identifier = element["element-6066-11e4-a52e-4f735466cecf"]
            request("POST", f"/session/{session}/element/{identifier}/value", {"text": "0826lfg"})
            wait_for(
                lambda: script(
                    "return (document.querySelector('[role=listbox]')?.textContent||'').includes('612 000 001')"
                )
            )
            request("POST", f"/session/{session}/element/{identifier}/value", {"text": "\ue007"})
            wait_for(lambda: script("return document.body.textContent.includes('Lucia Medina')"))
            checks.append("Matrícula normalizada → teléfono → ficha con Enter")
            invoice = rpc("documents.list")["result"]["items"][0]
            pdf = rpc("documents.pdf", {"identifier": invoice["id"]})
            assert pdf["ok"] and base64.b64decode(pdf["result"]["content"]).startswith(b"%PDF-")
            checks.append("PDF generado por servicio PyInstaller desde WebView")
            if args.test_document_handlers:
                assert click_text("Facturas")
                wait_for(lambda: click_text(invoice["full_number"]))
                wait_for(lambda: click_text("Vista previa / PDF"))
                wait_for(
                    lambda: script("return Boolean(document.querySelector('iframe.pdf-frame'))")
                )
                assert handler_calls() == []  # Opening the preview is not an OS action.
                wait_for(lambda: click_text("Abrir en lector"))
                wait_for(lambda: len(handler_calls()) == 1)
                wait_for(
                    lambda: script(
                        "return document.body.textContent.includes('Se ha solicitado abrir el PDF')"
                    )
                )
                assert click_text("Imprimir")
                wait_for(lambda: len(handler_calls()) == 2)
                wait_for(
                    lambda: script(
                        "return document.body.textContent.includes('Solicitud de impresión aceptada')"
                    )
                )
                events = handler_calls()
                assert [event["program"] for event in events] == ["xdg-open", "lpr"]
                assert all(event["pdf"] and event["bytes"] > 100 for event in events)
                assert events[0]["sha256"] == events[1]["sha256"]
                assert all(
                    Path(event["path"]).is_relative_to(Path(env["XDG_CACHE_HOME"]))
                    for event in events
                )
                handler_result.write_text('{"lpr":2}', encoding="utf-8")
                assert click_text("Imprimir")
                wait_for(lambda: len(handler_calls()) == 3)
                wait_for(
                    lambda: script(
                        "return document.body.textContent.includes('no ha confirmado la impresión')"
                    )
                )
                checks.append(
                    "Botones PDF → IPC Rust real → caché validada → receptores locales xdg-open/lpr; error de impresión visible"
                )
                for params in [
                    {
                        "name": "malicioso.exe",
                        "content": base64.b64encode(b"%PDF-1.7\nFALSO\n%%EOF").decode(),
                        "action": "open",
                    },
                    {"name": "factura.pdf", "content": pdf["result"]["content"], "action": "runas"},
                ]:
                    assert invoke("handle_pdf", params)["ok"] is False
                for url in [
                    "file:///tmp/programa",
                    "https://wa.me.evil.test/34612000001",
                    "https://wa.me/34612000001?text=Hola&otro=1",
                ]:
                    assert invoke("open_external", {"url": url})["ok"] is False
                assert len(handler_calls()) == 3
                checks.append(
                    "IPC rechaza PDF falso, verbo arbitrario y URL fuera de lista antes de invocar un programa"
                )
                (args.output / "document-handler-invocations.json").write_text(
                    json.dumps(handler_calls(), ensure_ascii=False, indent=2), encoding="utf-8"
                )
            if args.test_save_dialog:
                # Make a valid, synthetic CSV original large enough to require
                # several encrypted download blocks. The copy includes pending
                # uploads; it is deliberately never imported into the workshop.
                workshop = Path(rpc("bootstrap")["result"]["data_directory"]).resolve()
                assert workshop.is_relative_to(Path(temporary).resolve())
                rng = random.Random(20260923)
                source_bytes = b"codigo;nombre\n" + b"".join(
                    f"{index:05d};".encode() + rng.randbytes(2048).hex().encode() + b"\n"
                    for index in range(1536)
                )
                origin = rpc(
                    "import.source_save", {"name": "Ensayo sintético del selector nativo"}
                )["result"]
                upload = rpc(
                    "import.upload_start",
                    {
                        "name": "clientes-sinteticos.csv",
                        "size": len(source_bytes),
                        "source_id": origin["id"],
                    },
                )["result"]
                original = workshop / "imports" / upload["upload_id"] / "source.bin"
                assert original.resolve().is_relative_to(workshop)
                original.write_bytes(source_bytes)
                del source_bytes
                script(
                    "document.querySelector('[role=dialog] button[aria-label=\"Cerrar ventana\"]')?.click()"
                )
                wait_for(
                    lambda: not script("return Boolean(document.querySelector('[role=dialog]'))")
                )
                assert click_text("Configuración")
                wait_for(lambda: click_text("Copias y traslado"))
                password = request(
                    "POST",
                    f"/session/{session}/element",
                    {
                        "using": "css selector",
                        "value": "input[type=password][autocomplete=new-password]",
                    },
                )
                identifier = password["element-6066-11e4-a52e-4f735466cecf"]
                request(
                    "POST",
                    f"/session/{session}/element/{identifier}/value",
                    {"text": "clave-sintetica-del-selector"},
                )
                assert click_text("Crear y guardar copia")
                window = wait_for(chooser_window)
                chooser_key(window, "Escape")
                wait_for(
                    lambda: script(
                        "return document.body.textContent.includes('Has cancelado guardar otra copia')"
                    )
                )
                local_before = {item["name"] for item in rpc("backup.list")["result"]}
                assert local_before
                destination = Path(temporary) / "copia guardada.canamo"
                previous = b"DESTINO SINTETICO QUE DEBE CONSERVARSE HASTA CONFIRMAR"
                destination.write_bytes(previous)
                assert click_text("Crear y guardar copia")
                window = wait_for(chooser_window)
                # GTK can select only the basename while retaining .canamo.
                # Replace the entire entry, otherwise the test saves to a
                # different .canamo.canamo path and never exercises overwrite.
                chooser_key(window, "ctrl+l", "ctrl+a")
                subprocess.run(
                    ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", str(destination)],
                    env=env,
                    check=True,
                    timeout=5,
                )
                # Capture the real chooser in the isolated display. This needs
                # Pillow/XCB, already pinned in the development requirements.
                from PIL import ImageGrab

                ImageGrab.grab(xdisplay=env["DISPLAY"]).save(args.output / "native-save-dialog.png")
                assert destination.read_bytes() == previous
                chooser_key(window, "Return")
                time.sleep(0.3)
                replacement = chooser_window()
                if replacement:
                    chooser_key(replacement, "alt+r")
                wait_for(
                    lambda: script("return document.body.textContent.includes('Copia guardada')")
                )
                with destination.open("rb") as source:
                    header = source.read(7)
                    assert header == b"CANAMO1", (
                        f"El destino seleccionado no contiene la copia cifrada: {header!r}"
                    )
                    source.seek(0)
                    checksum = hashlib.file_digest(source, "sha256").hexdigest()
                assert destination.stat().st_size > 2 * 1048576
                local_after = rpc("backup.list")["result"]
                candidates = [
                    workshop / "backups" / item["name"]
                    for item in local_after
                    if item["name"] not in local_before
                ]
                matching = []
                for candidate in candidates:
                    with candidate.open("rb") as source:
                        if hashlib.file_digest(source, "sha256").hexdigest() == checksum:
                            matching.append(candidate)
                assert len(matching) == 1
                save_evidence = {
                    "dialog": "xdg-desktop-portal-gtk real",
                    "encrypted": True,
                    "bytes": destination.stat().st_size,
                    "sha256": checksum,
                    "matches_retained_local_backup": True,
                    "cancel_preserved_local_backup": True,
                    "previous_destination_intact_before_confirmation": True,
                }
                (args.output / "native-save-result.json").write_text(
                    json.dumps(save_evidence, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                checks.append(
                    "Botón Crear y guardar copia → selector GTK real: cancelación y sustitución confirmada de archivo temporal cifrado de varios bloques; SHA coincide con copia local"
                )
            before = rpc("bootstrap")["result"]["data_directory"]
            again = subprocess.run(
                [str(args.application.resolve())], env=env, timeout=15, capture_output=True
            )
            assert again.returncode == 0
            assert rpc("bootstrap")["result"]["data_directory"] == before
            checks.append("Segunda instancia termina y la sesión original sigue disponible")
            screenshot = request("GET", f"/session/{session}/screenshot")
            (args.output / "native-window.png").write_bytes(base64.b64decode(screenshot))
            assert artifact_metadata(args.application) == artifacts, (
                "Los ejecutables cambiaron durante la prueba nativa"
            )
        except BaseException as error:
            if sys.platform == "win32":
                try:
                    capture_env = {
                        key: value for key, value in env.items() if key != "PSModulePath"
                    }
                    capture_env["CANAMO_FAILURE_SCREEN"] = str(
                        (args.output / "failure-desktop.png").resolve()
                    )
                    capture_script = """$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; $p=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($p); try {$g.CopyFromScreen($b.Left,$b.Top,0,0,$b.Size);$p.Save($env:CANAMO_FAILURE_SCREEN)} finally {$g.Dispose();$p.Dispose()}; Get-Process | Where-Object {$_.Name -match 'taller-canamo|canamo-service|msedge'} | Select-Object Name,Id,MainWindowTitle,Responding | ConvertTo-Json; Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'msedgewebview2.exe'} | Select-Object ProcessId,CommandLine | ConvertTo-Json"""
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", capture_script],
                        env=capture_env,
                        stdout=log,
                        stderr=log,
                        timeout=10,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if args.test_save_dialog:
                try:
                    from PIL import ImageGrab

                    ImageGrab.grab(xdisplay=env["DISPLAY"]).save(
                        args.output / "failure-desktop.png"
                    )
                except (OSError, KeyError):
                    pass
            if session:
                try:
                    screenshot = request("GET", f"/session/{session}/screenshot")
                    (args.output / "failure.png").write_bytes(base64.b64decode(screenshot))
                except (OSError, AssertionError):
                    pass
            (args.output / "result.json").write_text(
                json.dumps(
                    {
                        "ok": False,
                        "platform": sys.platform,
                        "artifacts": artifacts,
                        "checks": checks,
                        "error": str(error),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise
        finally:
            if session:
                try:
                    request("DELETE", f"/session/{session}")
                except (OSError, AssertionError):
                    pass
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            if sys.platform == "linux" and data_directory:
                wait_for(service_stopped, timeout=15)
            log.close()
    (args.output / "result.json").write_text(
        json.dumps(
            {
                "ok": True,
                "platform": sys.platform,
                "artifacts": artifacts,
                "save_dialog": save_evidence,
                "startup_seconds": startup_seconds,
                "driver_mode": "edge_attach" if args.attach_edge else "tauri_driver",
                "checks": checks,
                "limits": [
                    "No comprueba impresora, notificación visible ni instalador Windows",
                    "Las invocaciones xdg-open/lpr opcionales usan receptores de prueba; no abren lector/navegador ni envían impresión real",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # Keep console JSON portable to Windows legacy code pages. The UTF-8 file
    # above retains literal Unicode; JSON readers recover the same strings here.
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=True))


if __name__ == "__main__":
    main()
