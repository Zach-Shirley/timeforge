$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $appDir
$dataDir = Join-Path $rootDir "Data"
$logPath = Join-Path $dataDir "server.timeforge.log"
$knownPython = "C:\Python314\python.exe"
$python = if (Test-Path $knownPython) { $knownPython } else { "python" }

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
Set-Location $rootDir
"[$(Get-Date -Format s)] Starting Timeforge from $rootDir using $python" | Out-File -FilePath $logPath -Encoding utf8 -Append

try {
  $status = Invoke-WebRequest -UseBasicParsing -Uri "http://timeforge.localhost/api/settings" -TimeoutSec 2
  if ($status.StatusCode -eq 200) {
    "Timeforge is already running." | Out-File -FilePath $logPath -Encoding utf8 -Append
    exit 0
  }
} catch {
  # Server is not reachable yet; continue and start it.
}

& $python (Join-Path $appDir "server.py") --host 127.0.0.1 --port 80 *>> $logPath
