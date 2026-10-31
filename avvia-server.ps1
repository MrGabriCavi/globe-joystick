# Avvia un piccolo server locale, per aprire la pagina anche dal telefono
# (telefono e PC sulla stessa rete Wi-Fi). Ctrl+C per fermarlo.
param([int]$Port = 8080)

$ips = Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback' } |
  Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "  PC:        http://localhost:$Port"
foreach ($ip in $ips) { Write-Host "  Telefono:  http://${ip}:$Port" }
Write-Host ""
Write-Host "  (se il telefono non si collega, consenti Python nel firewall di Windows per le reti private)"
Write-Host ""

python -m http.server $Port --bind 0.0.0.0 --directory $PSScriptRoot
