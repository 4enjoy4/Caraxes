$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ModelPath = Join-Path $Root "models\Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-GGUF\Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-Q4_K.gguf"
$Port = $env:CARAXES_MODEL_PORT
if (-not $Port) { $Port = "9901" }
$Context = $env:CARAXES_N_CTX
if (-not $Context) { $Context = "8192" }
$Reasoning = $env:CARAXES_REASONING
if (-not $Reasoning) { $Reasoning = "off" }
$ReasoningBudget = $env:CARAXES_REASONING_BUDGET
if (-not $ReasoningBudget) { $ReasoningBudget = "0" }
$CommonArgs = @(
    "-m", $ModelPath,
    "--host", "127.0.0.1",
    "--port", $Port,
    "-c", $Context,
    "--reasoning", $Reasoning,
    "--reasoning-budget", $ReasoningBudget
)

if (-not (Test-Path $ModelPath)) {
    throw "Model file not found: $ModelPath. Run scripts\download_model.ps1 first."
}

$Server = Get-Command llama-server -ErrorAction SilentlyContinue
if ($Server) {
    & $Server.Source @CommonArgs
    exit $LASTEXITCODE
}

$WingetServer = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($WingetServer) {
    & $WingetServer.FullName @CommonArgs
    exit $LASTEXITCODE
}

$Llama = Get-Command llama -ErrorAction SilentlyContinue
if ($Llama) {
    & $Llama.Source serve -m $ModelPath --host 127.0.0.1 --port $Port -c $Context
    exit $LASTEXITCODE
}

throw "Could not find llama-server or llama on PATH. Install llama.cpp with: winget install llama.cpp"
