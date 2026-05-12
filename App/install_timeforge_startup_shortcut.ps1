$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $appDir
$scriptPath = Join-Path $appDir "start_timeforge.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Timeforge Local App.lnk"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$shortcut.WorkingDirectory = $rootDir
$shortcut.Description = "Start the local Timeforge review app."
$shortcut.Save()

Write-Host "Installed startup shortcut: $shortcutPath"
