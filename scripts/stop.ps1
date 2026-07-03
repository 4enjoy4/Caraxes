$ErrorActionPreference = "SilentlyContinue"

foreach ($Port in @(9898, 9901)) {
    $Processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($ProcessId in $Processes) {
        if ($ProcessId) {
            Stop-Process -Id $ProcessId -Force
            Write-Host "Stopped process $ProcessId on port $Port"
        }
    }
}
