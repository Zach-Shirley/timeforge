$ErrorActionPreference = "Stop"

$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$entry = "127.0.0.1 timeforge.localhost"
$content = Get-Content -Path $hostsPath -ErrorAction Stop

if ($content -notcontains $entry) {
  Add-Content -Path $hostsPath -Value $entry
  Write-Host "Added hosts entry: $entry"
} else {
  Write-Host "Hosts entry already exists: $entry"
}
