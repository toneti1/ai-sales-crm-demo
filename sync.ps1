# Sincroniza el codigo de la app desde GitHub (solo codigo; jamas datos locales).
# Lo llama launch.ps1 antes de arrancar el server. Si falla, se sigue con la
# copia local: la demo nunca se queda sin funcionar por falta de red.

$ErrorActionPreference = 'Continue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncUrl = 'https://github.com/toneti1/ai-sales-crm-demo/archive/refs/heads/main.zip'
$logFile = Join-Path $dir 'sync.log'
$guid = [System.Guid]::NewGuid().ToString()
$tmpZip = Join-Path $env:TEMP "crm-demo-sync-$guid.zip"
$tmpDir = Join-Path $env:TEMP "crm-demo-sync-$guid"

function Write-SyncLog([string]$msg) {
    try {
        Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" -Encoding UTF8
    } catch {}
}

try {
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $syncUrl -OutFile $tmpZip -UseBasicParsing -TimeoutSec 45
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
    $srcRoot = (Get-ChildItem $tmpDir -Directory | Select-Object -First 1).FullName
    if (-not $srcRoot) { throw 'archivo descargado vacio' }

    # Codigo: se reemplaza entero.
    # NO se tocan: unified_leads.json, generated_landing_pages/, lead-finder/leads.json,
    # seen.json (datos locales), ni runtimes (python/, node/, chrome/, cloudflared.exe),
    # ni lead-finder/node_modules/.
    foreach ($f in @('dashboard\server.py', 'dashboard\index.html', 'integrate.py', 'run_pipeline.py', 'launch.ps1', 'sync.ps1', 'stop.ps1', 'Start.vbs', 'Stop.vbs')) {
        $src = Join-Path $srcRoot $f
        if (Test-Path $src) { Copy-Item $src (Join-Path $dir $f) -Force }
    }
    foreach ($d in @('frontend\dist', 'generator\sales_assistant_generator', 'lead-finder\dist')) {
        $src = Join-Path $srcRoot $d
        if (Test-Path $src) {
            $dst = Join-Path $dir $d
            Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
            Copy-Item $src $dst -Recurse -Force
        }
    }
    $ver = '?'
    $verFile = Join-Path $srcRoot 'VERSION.txt'
    if (Test-Path $verFile) {
        $ver = (Get-Content $verFile -First 1).Trim()
        Copy-Item $verFile (Join-Path $dir 'VERSION.txt') -Force
    }
    Write-SyncLog "OK  version $ver"
} catch {
    Write-SyncLog "FAIL  $($_.Exception.Message)  (se usa la copia local)"
} finally {
    Remove-Item $tmpZip -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}
