$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:CARAXES_OPENAI_BASE_URL = "http://127.0.0.1:9901/v1"

$Backend = Get-NetTCPConnection -LocalPort 9901 -ErrorAction SilentlyContinue
if (-not $Backend) {
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Root\scripts\start_model_server.ps1`"" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden
}

Start-Sleep -Seconds 2
& "$Root\scripts\start.ps1"
