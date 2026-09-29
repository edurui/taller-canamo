# Run in an isolated Windows test account, never on the workshop's operational PC.
# This installs a development build, verifies it, and removes that installation.
param([string]$Installer = "")
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $Installer) {
    $Installer = (Get-ChildItem (Join-Path $projectRoot "src-tauri/target/release/bundle/nsis/*-setup.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
if (-not $Installer -or -not (Test-Path $Installer)) { throw "Falta el instalador NSIS." }
$existing = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq "Talleres El Canamo - Desarrollo" }
if ($existing) { throw "Ya existe una instalación de desarrollo. Usa una cuenta Windows desechable para esta prueba." }
$installRoot = Join-Path $env:TEMP ("Cáñamo instalación " + [guid]::NewGuid().ToString("N"))
$report = Join-Path $projectRoot "reports/windows-installed-sidecar.json"
if (Test-Path $report) { Remove-Item $report }
try {
    # /D must be last and is not quoted in NSIS' command line syntax.
    $install = Start-Process -FilePath $Installer -ArgumentList "/S /D=$installRoot" -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "El instalador falló: $($install.ExitCode)" }
    $app = Join-Path $installRoot "taller-canamo.exe"
    $service = Join-Path $installRoot "canamo-service.exe"
    if (-not (Test-Path $app) -or -not (Test-Path $service)) { throw "No están ambos ejecutables en la ubicación instalada." }
    $artifacts = @($Installer, $app, $service) | ForEach-Object {
        [ordered]@{ path = (Resolve-Path $_).Path; bytes = (Get-Item $_).Length; sha256 = (Get-FileHash -Algorithm SHA256 $_).Hash.ToLowerInvariant() }
    }
    # The diagnostic creates a disposable database, issues synthetic documents,
    # makes a PDF, shuts down, reopens the history, and cleans its temporary data.
    $test = Start-Process -FilePath $app -ArgumentList "--diagnose-sidecar `"$report`"" -PassThru
    if (-not $test.WaitForExit(120000)) { Stop-Process -Id $test.Id -Force; throw "Diagnóstico agotó 120 segundos." }
    $test.Refresh()
    if ($test.ExitCode -ne 0 -or -not (Test-Path $report)) { throw "El diagnóstico instalado falló: $($test.ExitCode)" }
    $result = Get-Content -Raw $report | ConvertFrom-Json
    if (-not $result.ok) { throw "El servicio instalado no pasó el diagnóstico." }
    foreach ($artifact in $artifacts) {
        if ((Get-FileHash -Algorithm SHA256 $artifact.path).Hash.ToLowerInvariant() -ne $artifact.sha256) { throw "Cambió un artefacto durante el diagnóstico." }
    }
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='canamo-service.exe'" | Where-Object { $_.ExecutablePath -eq $service })
    if ($orphans.Count -ne 0) { throw "Quedan procesos auxiliares de esta instalación." }
    $result | Add-Member -NotePropertyName artifacts -NotePropertyValue $artifacts
    $result | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $report
    Write-Host "Instalación, ruta con espacios/tildes, PDF, reapertura y cierre comprobados: $report"
} finally {
    $uninstaller = Join-Path $installRoot "uninstall.exe"
    if (Test-Path $uninstaller) { Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait | Out-Null }
}
