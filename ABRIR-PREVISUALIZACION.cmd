@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta PREPARAR-WINDOWS.cmd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_preview.py
pause
