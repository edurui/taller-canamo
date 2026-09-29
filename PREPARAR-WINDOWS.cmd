@echo off
setlocal
cd /d "%~dp0"
py -3.13 -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements-dev.lock
if errorlevel 1 goto :error
call npm ci
if errorlevel 1 goto :error
".venv\Scripts\python.exe" scripts\prepare_assistant_models.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" scripts\prepare_access_runtime.py
if errorlevel 1 goto :error
call npm run build
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pytest
if errorlevel 1 goto :error
echo Preparado para previsualizacion. No habilitado para facturacion real.
pause
exit /b 0
:error
echo Ha fallado un paso. Conserva el mensaje anterior para su revision.
pause
exit /b 1
