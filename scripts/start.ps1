$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

try {
    & ".\.venv\Scripts\python.exe" -c "import llama_cpp"
} catch {
    Write-Host "llama-cpp-python is not installed yet. Installing CPU runtime..."
    try {
        $env:TEMP = "C:\t"
        $env:TMP = "C:\t"
        if (-not (Test-Path "C:\t")) { New-Item -ItemType Directory -Force -Path "C:\t" | Out-Null }
        & ".\.venv\Scripts\python.exe" -m pip install --prefer-binary -r requirements-llm.txt
    } catch {
        Write-Host "Could not install llama-cpp-python automatically."
        Write-Host "The web UI will still start. Use scripts\start_model_server.ps1 in another terminal and set CARAXES_OPENAI_BASE_URL=http://127.0.0.1:9901/v1 for model inference."
    }
}

Write-Host "Starting Caraxes on http://0.0.0.0:9898"
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 9898
