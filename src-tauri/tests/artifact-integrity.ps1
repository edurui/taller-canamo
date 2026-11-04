# Tauri patches its bundle marker UNK -> NSS for NSIS, then restores the staged EXE.
# Compare every byte with the build hash, allowing only that exact documented patch.
# https://github.com/tauri-apps/tauri/blob/tauri-utils-v2.9.3/crates/tauri-utils/src/platform.rs
function Assert-BuildArtifact {
    param([string]$Path, [object[]]$ExpectedArtifacts)
    $item = Get-Item -LiteralPath $Path
    $expected = @($ExpectedArtifacts | Where-Object { (Split-Path $_.path -Leaf) -eq $item.Name })
    if ($expected.Count -ne 1 -or $item.Length -ne $expected[0].bytes) {
        throw "Tamaño o entrada de manifiesto incorrectos: $($item.Name)"
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $proof = [ordered]@{ path = $item.FullName; bytes = $item.Length; sha256 = $actual; build_sha256 = $expected[0].sha256; comparison = 'exact' }
    if ($actual -eq $expected[0].sha256) { return $proof }
    if ($item.Name -ne 'taller-canamo.exe') { throw "SHA-256 incorrecto: $($item.Name)" }
    $bytes = [IO.File]::ReadAllBytes($item.FullName)
    # Latin1 maps one byte to one character; offsets are byte offsets, with no decoding loss.
    $text = [Text.Encoding]::Latin1.GetString($bytes)
    $marker = '__TAURI_BUNDLE_TYPE_VAR_NSS'
    $offset = $text.IndexOf($marker, [StringComparison]::Ordinal)
    if ($offset -lt 0 -or $text.IndexOf($marker, $offset + 1, [StringComparison]::Ordinal) -ge 0) {
        throw 'Falta el marcador NSIS único de Tauri.'
    }
    $original = [Text.Encoding]::ASCII.GetBytes('__TAURI_BUNDLE_TYPE_VAR_UNK')
    [Array]::Copy($original, 0, $bytes, $offset, $original.Length)
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    if ($hash -ne $expected[0].sha256) {
        throw "SHA-256 incorrecto incluso tras verificar el marcador NSIS: $($item.Name); actual=$actual; normalizado=$hash; esperado=$($expected[0].sha256)"
    }
    $proof.comparison = 'tauri-nsis-marker'
    $proof.marker_offset = $offset
    return $proof
}
