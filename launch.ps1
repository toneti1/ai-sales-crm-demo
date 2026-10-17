# CRM demo launcher: server local + tunnel cloudflared, todo desacoplado y oculto.
# Llamado por Start.vbs. Al final muestra un popup con la URL publica.

$ErrorActionPreference = 'Continue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$tokenBytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($tokenBytes)
$token = [Convert]::ToBase64String($tokenBytes).Replace('+','-').Replace('/','_').TrimEnd('=')
$env:DASHBOARD_TOKEN = $token
$env:DASHBOARD_ALLOW_REMOTE = '1'

# 1. Parar instancias previas (evita doble bind en el puerto 8000).
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Remove-Item 'tunnel.log','tunnel.err.log','url.txt' -Force -ErrorAction SilentlyContinue

# 1b. Sincronizar el codigo de la app desde GitHub.
& "$dir\sync.ps1"

# 2. Server local (desacoplado, oculto). Sobrevive al cierre del launcher.
#    PUPPETEER_EXECUTABLE_PATH apunta al Chrome portatil para el scraper.
$env:PUPPETEER_EXECUTABLE_PATH = "$dir\chrome\chrome.exe"
Start-Process -WindowStyle Hidden -FilePath "$dir\python\python.exe" `
    -ArgumentList 'dashboard\server.py' -WorkingDirectory $dir
Start-Sleep -Seconds 2

# 3. Tunnel cloudflared (desacoplado, oculto, log a archivo).
Start-Process -WindowStyle Hidden -FilePath "$dir\cloudflared.exe" `
    -ArgumentList 'tunnel','--no-autoupdate','--url','http://127.0.0.1:8000' `
    -WorkingDirectory $dir `
    -RedirectStandardOutput "$dir\tunnel.log" -RedirectStandardError "$dir\tunnel.err.log"

# 4. Esperar a que el tunnel publique su URL (hasta 120 s).
$url = $null
$deadline = (Get-Date).AddSeconds(120)
while (-not $url -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $text = ''
    try { $text = (Get-Content "$dir\tunnel.log" -Raw -ErrorAction Stop) } catch {}
    if (-not $text) { try { $text = (Get-Content "$dir\tunnel.err.log" -Raw -ErrorAction Stop) } catch {} }
    if ($text) {
        $m = [regex]::Match([string]$text, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($m.Success) { $url = $m.Value }
    }
}

Add-Type -AssemblyName System.Windows.Forms

if ($url) {
    $share = "$url/?token=$token"
    Set-Content -Path 'url.txt' -Value $share -Encoding UTF8
    Set-Clipboard $share
    Start-Process $share
    [System.Windows.Forms.MessageBox]::Show(
        "Share this URL with your team (already copied to your clipboard):`r`n`r`n" +
        "$share`r`n`r`n" +
        "If it doesn't open immediately, wait 30-60 seconds and refresh (DNS may take a moment).`r`n" +
        "It is also saved in url.txt.`r`n`r`n" +
        "The server and tunnel continue running in the background.`r`n" +
        "To stop: run Stop.vbs or close 'cloudflared.exe' and 'python.exe' in Task Manager.",
        'CRM demo', 0, 64
    )
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "Could not create public tunnel (no internet connection or firewall is blocking cloudflared.exe).`r`n`r`n" +
        "Check your connection/firewall and double-click Start.vbs again.",
        'CRM demo', 0, 48
    )
}
