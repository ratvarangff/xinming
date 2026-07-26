$ErrorActionPreference = "Stop"

$repo   = "C:\Users\Admin\Desktop\xinming-bot"
$python = Join-Path $repo "venv\Scripts\python.exe"
$script = Join-Path $repo "bot.py"
$logDir = Join-Path $repo "logs"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp   = Get-Date -Format "yyyy-MM-dd_HHmmss"
$outLog  = Join-Path $logDir "bot_$stamp.log"
$errLog  = Join-Path $logDir "bot_$stamp.err.log"
$pidFile = Join-Path $repo "bot.pid"

# Don't start a second copy if one is already running
if (Test-Path $pidFile) {
    $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        Write-Output "Bot already running (PID $existingPid). Not starting a second instance."
        exit 0
    }
}

$proc = Start-Process -FilePath $python `
    -ArgumentList "`"$script`"" `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

$proc.Id | Out-File -FilePath $pidFile -Encoding ascii
Write-Output "Started xinming-bot (PID $($proc.Id)). Logs: $outLog"
