$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$MacStudioHost,

    [string]$ModelPort = "9901"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:CARAXES_OPENAI_BASE_URL = "http://$MacStudioHost`:$ModelPort/v1"

Write-Host "Using remote model backend: $env:CARAXES_OPENAI_BASE_URL"
Write-Host "Starting Windows Caraxes UI only on http://0.0.0.0:9898"
& "$Root\scripts\start.ps1"
