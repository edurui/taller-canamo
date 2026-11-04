# Test tooling only. The driver is never included in the installer.
param([string]$OutputDirectory = "edge-driver")
$ErrorActionPreference = "Stop"
$client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$roots = @('HKLM:\SOFTWARE\WOW6432Node\', 'HKLM:\SOFTWARE\', 'HKCU:\SOFTWARE\WOW6432Node\', 'HKCU:\SOFTWARE\')
$version = $null
foreach ($root in $roots) {
    $item = Get-ItemProperty -LiteralPath ($root + $client) -ErrorAction SilentlyContinue
    if ($item.pv -match '^\d+\.\d+\.\d+\.\d+$') { $version = $item.pv; break }
}
if (-not $version) { throw 'No se encuentra el runtime WebView2 del equipo de pruebas.' }
$destination = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$archive = Join-Path $destination 'edgedriver.zip'
Invoke-WebRequest "https://msedgedriver.microsoft.com/$version/edgedriver_win64.zip" -OutFile $archive
Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
$driver = Join-Path $destination 'msedgedriver.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $driver
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'El driver no tiene una firma Microsoft válida.'
}
$driverVersion = & $driver --version
if ($LASTEXITCODE -ne 0 -or $driverVersion -notmatch [regex]::Escape($version)) {
    throw 'Edge Driver no se puede ejecutar o no coincide con WebView2.'
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'reports') -Force | Out-Null
[ordered]@{
    webview2_version = $version
    driver_version = $driverVersion
    driver_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $driver).Hash.ToLowerInvariant()
    microsoft_signature_valid = $true
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $projectRoot 'reports/windows-webdriver.json')
Write-Host "WebView2 y driver Microsoft: $version"
