# Deterministic positive/negative fixtures. Does not install or accept an application.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'artifact-integrity.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('canamo-integrity-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$checks = 0
try {
    $app = Join-Path $root 'taller-canamo.exe'
    $original = [byte[]](0, 255, 128) + [Text.Encoding]::ASCII.GetBytes('__TAURI_BUNDLE_TYPE_VAR_UNK') + [byte[]](10, 13, 254)
    [IO.File]::WriteAllBytes($app, $original)
    $expected = @(@{ path = 'taller-canamo.exe'; bytes = $original.Length; sha256 = (Get-FileHash $app).Hash.ToLowerInvariant() })
    $result = Assert-BuildArtifact $app $expected
    if ($result.comparison -ne 'exact') { throw 'Falló la igualdad exacta.' }
    $checks++
    $patched = [Text.Encoding]::Latin1.GetBytes([Text.Encoding]::Latin1.GetString($original).Replace('_VAR_UNK', '_VAR_NSS'))
    [IO.File]::WriteAllBytes($app, $patched)
    $result = Assert-BuildArtifact $app $expected
    if ($result.comparison -ne 'tauri-nsis-marker' -or $result.marker_offset -ne 3 -or $result.sha256 -eq $result.build_sha256) { throw 'Falló la transformación NSIS.' }
    if ((Get-FileHash $app).Hash.ToLowerInvariant() -ne $result.sha256) { throw 'La comprobación modificó el archivo.' }
    $checks++
    foreach ($damage in @('other-byte', 'wrong-marker', 'duplicate-marker', 'size', 'wrong-hash', 'duplicate-entry', 'sidecar')) {
        $bytes = $patched.Clone()
        $path = $app
        $spec = @(@{ path = 'taller-canamo.exe'; bytes = $original.Length; sha256 = $expected[0].sha256 })
        switch ($damage) {
            'other-byte' { $bytes[0] = 1 }
            'wrong-marker' { $bytes[27] = 88 }
            'duplicate-marker' { $bytes = $bytes + $patched; $spec[0].bytes = $bytes.Length }
            'size' { $spec[0].bytes++ }
            'wrong-hash' { $spec[0].sha256 = '0' * 64 }
            'duplicate-entry' { $spec = $spec + $spec }
            'sidecar' { $path = Join-Path $root 'canamo-service.exe'; $spec[0].path = 'canamo-service.exe' }
        }
        [IO.File]::WriteAllBytes($path, $bytes)
        $rejected = $false
        try { Assert-BuildArtifact $path $spec | Out-Null } catch { $rejected = $true }
        if (-not $rejected) { throw "Alteración aceptada: $damage" }
        $checks++
    }
    Write-Host "$checks controles de integridad correctos; ningún archivo modificado por el verificador."
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
