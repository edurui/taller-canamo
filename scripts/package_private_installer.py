"""Wrap an unchanged NSIS installer and a verified initial backup in one private EXE.

Run locally for real workshop data. CI must use synthetic backups only.
The application binaries and all fiscal/restore controls remain unchanged.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inspect_backup(path):
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as temporary:
        manifest = json.loads(archive.read("manifest.json"))
        names = archive.namelist()
        if (
            manifest.get("format") != "canamo-backup-v2"
            or manifest.get("certificate_included") is not False
            or len(names) != len(set(names))
            or set(manifest["files"]) != set(names) - {"manifest.json"}
            or "taller.sqlite3" not in manifest["files"]
            or any(name.startswith("secure/") for name in names)
        ):
            raise ValueError("La copia inicial no tiene un manifiesto completo y sin certificados.")
        for name, expected in manifest["files"].items():
            with archive.open(name) as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                    raise ValueError("La copia inicial contiene un archivo alterado.")
        database = Path(temporary) / "taller.sqlite3"
        with archive.open("taller.sqlite3") as source, database.open("wb") as target:
            shutil.copyfileobj(source, target)
        with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("La base inicial no pasa integridad.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("La base inicial tiene referencias incompletas.")
            counts = {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("customers", "vehicles", "documents")
            }
            visible_counts = {
                "customers": connection.execute(
                    "SELECT count(*) FROM customers WHERE archived=0"
                ).fetchone()[0],
                "vehicles": connection.execute(
                    "SELECT count(*) FROM vehicles WHERE archived=0"
                ).fetchone()[0],
                "documents": connection.execute(
                    "SELECT count(*) FROM documents WHERE kind='invoice' AND status!='import_reverted'"
                ).fetchone()[0],
            }
        return {"sha256": digest(path), "counts": counts, "visible_counts": visible_counts}


def nsis_text(value):
    value = str(value)
    if "\n" in value or "\r" in value:
        raise ValueError("Ruta con salto de línea.")
    return value.replace("$", "$$").replace('"', '$\\"')


def prepare(installer, backup, output, folder):
    folder.mkdir(parents=True, exist_ok=False)
    for source, name in ((installer, "installer.exe"), (backup, "data.canamo")):
        shutil.copyfile(source, folder / name)
    spec = inspect_backup(folder / "data.canamo")
    spec["installer_sha256"] = digest(folder / "installer.exe")
    (folder / "seed.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    (folder / "seed.ps1").write_text(
        (ROOT / "scripts/installer_seed.ps1").read_text(encoding="utf-8"),
        encoding="utf-8-sig",
    )
    recipe = r"""
Unicode true
RequestExecutionLevel user
Name "Talleres El Cañamo - Instalación con datos"
OutFile "@OUTPUT@"
InstallDir "$LOCALAPPDATA\Talleres El Canamo - Desarrollo"
SetCompressor lzma
!include "MUI2.nsh"
!include "x64.nsh"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Instalar El Cáñamo con sus datos"
!define MUI_WELCOMEPAGE_TEXT "Se instalará la aplicación y se cargarán los datos preparados del taller.$\r$\n$\r$\nLos datos existentes nunca se sustituyen.$\r$\n$\r$\nLa emisión fiscal nueva sigue pendiente de activación; los históricos estarán disponibles."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\taller-canamo.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir el programa"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "Spanish"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Se necesita Windows de 64 bits." /SD IDOK
    Abort
  ${EndIf}
FunctionEnd
Section
  SetShellVarContext current
  InitPluginsDir
  SetOutPath "$PLUGINSDIR\canamo"
  SetCompress off
  File /oname=installer.exe "@FOLDER@\installer.exe"
  SetCompress auto
  File /oname=data.canamo "@FOLDER@\data.canamo"
  File /oname=seed.json "@FOLDER@\seed.json"
  File /oname=seed.ps1 "@FOLDER@\seed.ps1"
  DetailPrint "Instalando la aplicación..."
  ExecWait '"$PLUGINSDIR\canamo\installer.exe" /S /D=$INSTDIR' $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "La instalación no ha terminado. No se han cargado datos." /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  IfFileExists "$LOCALAPPDATA\es.tallereselcanamo.desktop.dev\taller.sqlite3" existing
  DetailPrint "Cargando y comprobando los datos del taller..."
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\canamo\seed.ps1" -Service "$INSTDIR\canamo-service.exe" -Bundle "$PLUGINSDIR\canamo"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "No se ha completado la carga inicial. No se han reemplazado datos existentes. Conserva este instalador y avisa a Eduardo." /SD IDOK
    SetErrorLevel 2
    Quit
  ${EndIf}
  Goto done
existing:
  DetailPrint "Se conservan los datos que ya había en este ordenador."
done:
  SetErrorLevel 0
SectionEnd
"""
    recipe = recipe.replace("@OUTPUT@", nsis_text(compiler_path(output))).replace(
        "@FOLDER@", nsis_text(compiler_path(folder))
    )
    (folder / "installer.nsi").write_text(recipe, encoding="utf-8-sig")
    return spec


def compiler_path(path):
    absolute = path.resolve().as_posix()
    return (absolute if os.name == "nt" else "Z:" + absolute).replace("/", "\\")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installer", "backup", "output", "work", "makensis"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--installer-sha256", required=True)
    parser.add_argument("--wine-prefix", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("El archivo de salida ya existe; no se sobrescribe.")
    if digest(args.installer) != args.installer_sha256:
        parser.error("El instalador no coincide con el original verificado.")
    if os.name != "nt" and not args.wine_prefix:
        parser.error("En Linux se necesita un prefijo Wine exclusivo para la compilación.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    spec = prepare(args.installer, args.backup, args.output, args.work)
    command = [str(args.makensis.resolve()), "/V2", compiler_path(args.work / "installer.nsi")]
    environment = os.environ.copy()
    if os.name != "nt":
        command.insert(0, "wine")
        environment.update(WINEPREFIX=str(args.wine_prefix.resolve()), WINEDEBUG="-all")
    subprocess.run(command, check=True, env=environment)
    spec["output_sha256"] = digest(args.output)
    (args.work / "package-proof.json").write_text(
        json.dumps(spec, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "output": str(args.output), "counts": spec["counts"]}))


if __name__ == "__main__":
    main()
