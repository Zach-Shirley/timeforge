$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path (Split-Path -Parent $appDir) "Data\server.runtime.log"
Set-Location (Split-Path -Parent $appDir)
& python (Join-Path $appDir "server.py") --host 127.0.0.1 --port 8787 *> $logPath
