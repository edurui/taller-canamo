"""JSON-lines IPC. stdout contains protocol data only; diagnostics go to stderr."""
import argparse
import json
import logging
import sys
import threading
from pathlib import Path
from .app import App
from .errors import AppError

MAX_LINE_BYTES = 300_000_000

def serve(root, source=None, target=None, background=True):
    source = source or sys.stdin.buffer
    target = target or sys.stdout
    app = App(root)
    stop = threading.Event()
    shutdown_completed = False
    def tick():
        while not stop.wait(30):
            try:
                app.tick()
            except Exception:
                logging.error("Background task failed; see operational state in the app.")
    if background:
        threading.Thread(target=tick, daemon=True).start()
    try:
        while True:
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                # Fail closed. Do not parse the remaining fragments as new requests.
                raise AppError("Solicitud demasiado grande.")
            identifier = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise AppError("Solicitud no valida.")
                identifier = request.get("id")
                if not isinstance(identifier, (int, str)) or isinstance(identifier, bool):
                    raise AppError("Falta un identificador de solicitud valido.")
                result = app.dispatch(request.get("action"), request.get("params"))
                response = {"id": identifier, "ok": True, "result": result}
            except AppError as exc:
                response = {"id": identifier, "ok": False, "error": {"message": str(exc), "code": exc.code, "details": exc.details}}
            except (ValueError, TypeError):
                response = {"id": identifier, "ok": False, "error": {"message": "JSON o parametros no validos.", "code": "invalid_request"}}
            except Exception:
                logging.error("RPC action failed. No request payload has been logged.")
                response = {"id": identifier, "ok": False, "error": {"message": "Error interno. Revisa el historial antes de repetir una emision.", "code": "internal"}}
            target.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            target.flush()
            if response["ok"] and request.get("action") == "app.shutdown":
                # The reply acknowledges the completed backup. Exit after flushing
                # it and do not take a second backup in finally.
                shutdown_completed = True
                break
    finally:
        stop.set()
        if not shutdown_completed:
            try:
                app.shutdown()
            except Exception:
                logging.error("Shutdown backup failed.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--no-background", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    serve(Path(args.data), background=not args.no_background)

if __name__ == "__main__":
    main()
