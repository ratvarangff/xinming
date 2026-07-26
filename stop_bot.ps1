$repo    = "C:\Users\Admin\Desktop\xinming-bot"
$pidFile = Join-Path $repo "bot.pid"
$python  = Join-Path $repo "venv\Scripts\python.exe"

$stopped = $false

if (Test-Path $pidFile) {
    $procId = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $procId -Force
        $stopped = $true
        Write-Output "Stopped xinming-bot (PID $procId)."
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

if (-not $stopped) {
    # Fallback: find any python.exe running bot.py from this venv
    $matches = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.ExecutablePath -eq $python -and $_.CommandLine -like "*bot.py*" }

    foreach ($m in $matches) {
        Stop-Process -Id $m.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped = $true
        Write-Output "Stopped xinming-bot (PID $($m.ProcessId)) via fallback match."
    }
}

if (-not $stopped) {
    Write-Output "No running xinming-bot process found."
}
