$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $appDir
$dataDir = Join-Path $rootDir "Data"
$logPath = Join-Path $dataDir "server.timeforge.log"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
Set-Location $rootDir

try {
  $status = Invoke-WebRequest -UseBasicParsing -Uri "http://timeforge.localhost/api/settings" -TimeoutSec 2
  if ($status.StatusCode -eq 200) {
    "Timeforge is already running." | Out-File -FilePath $logPath -Encoding utf8 -Append
    exit 0
  }
} catch {
  # Server is not reachable yet; continue and start it.
}

& python (Join-Path $appDir "server.py") --host 127.0.0.1 --port 80 *> $logPath
