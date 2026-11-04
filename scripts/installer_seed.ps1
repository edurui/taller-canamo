param([Parameter(Mandatory=$true)][string]$Service, [Parameter(Mandatory=$true)][string]$Bundle)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $Bundle 'seed.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$destination = Join-Path $env:LOCALAPPDATA 'es.tallereselcanamo.desktop.dev'
# The initial delivery never replaces any existing installation data.
if (Test-Path -LiteralPath $destination) { throw 'Ya existe una carpeta de datos. No se ha sustituido.' }
$backup = Join-Path $Bundle 'data.canamo'
if ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.sha256) { throw 'La copia inicial no coincide con la preparada.' }
$staging = $destination + '.initial-' + [guid]::NewGuid().ToString('N')
$process = New-Object System.Diagnostics.Process
$process.StartInfo.FileName = $Service
$process.StartInfo.Arguments = '--no-background --data "' + $staging + '"'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.CreateNoWindow = $true
$process.StartInfo.RedirectStandardInput = $true
$process.StartInfo.RedirectStandardOutput = $true
$process.StartInfo.RedirectStandardError = $true
$process.StartInfo.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
$sequence = 0
$started = $false
$committed = $false
function Invoke-Service([string]$Action, [hashtable]$Parameters = @{}) {
    $script:sequence++
    $request = @{ id = $script:sequence; action = $Action; params = $Parameters } | ConvertTo-Json -Depth 30 -Compress
    $process.StandardInput.WriteLine($request)
    $process.StandardInput.Flush()
    $line = $process.StandardOutput.ReadLineAsync()
    if (-not $line.Wait(120000)) { throw 'La preparación de datos ha agotado su tiempo.' }
    if (-not $line.Result) { throw 'El servicio terminó antes de completar los datos.' }
    $response = $line.Result | ConvertFrom-Json
    if ($response.id -ne $script:sequence -or $response.ok -ne $true) { throw "No se pudo preparar la copia: $($response.error.message)" }
    return $response.result
}
try {
    if (-not $process.Start()) { throw 'No se pudo iniciar el servicio.' }
    $started = $true
    $errors = $process.StandardError.ReadToEndAsync()
    $upload = Invoke-Service 'backup.upload_start' @{ name = 'data.canamo'; total_bytes = (Get-Item -LiteralPath $backup).Length }
    $stream = [IO.File]::OpenRead($backup)
    try {
        $buffer = New-Object byte[] 1048576
        $offset = 0L
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            Invoke-Service 'backup.upload_chunk' @{ upload_id = $upload.upload_id; offset = $offset; content = [Convert]::ToBase64String($buffer, 0, $read) } | Out-Null
            $offset += $read
        }
    } finally { $stream.Dispose() }
    $preview = Invoke-Service 'backup.upload_finish' @{ upload_id = $upload.upload_id }
    foreach ($table in @('customers','vehicles','documents')) {
        if ($preview.counts.$table -ne $spec.counts.$table) { throw "Recuento incorrecto: $table" }
    }
    Invoke-Service 'backup.restore' @{ token = $preview.token; confirmation = 'RESTAURAR' } | Out-Null
    $customers = Invoke-Service 'customers.list'
    $vehicles = Invoke-Service 'vehicles.page'
    $documents = Invoke-Service 'documents.list'
    if ($customers.total -ne $spec.visible_counts.customers -or $vehicles.total -ne $spec.visible_counts.vehicles -or $documents.total -ne $spec.visible_counts.documents) { throw 'Los datos restaurados no coinciden con la entrega.' }
    # Preserve all fiscal and transfer gates. Initial data loading is not fiscal activation.
    Invoke-Service 'app.shutdown' | Out-Null
    if (-not $process.WaitForExit(30000) -or $process.ExitCode -ne 0) { throw 'El servicio no cerró correctamente.' }
    if (Test-Path -LiteralPath $destination) { throw 'Otra instancia ha creado datos. No se sustituyen.' }
    @{ loaded = $true; counts = $spec.counts; backup_sha256 = $spec.sha256; fiscal_activated = $false } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $staging '.initial-data-loaded.json')
    [IO.Directory]::Move($staging, $destination)
    $committed = $true
} finally {
    if ($started -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    $process.Dispose()
    if (-not $committed -and (Test-Path -LiteralPath $staging)) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
