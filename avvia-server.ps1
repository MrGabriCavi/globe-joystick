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

# Serve solo index.html: il resto della cartella (.git compreso) non è visibile dalla rete.
$server = @'
import functools, http.server, sys

class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        if self.path.split('?')[0] not in ('/', '/index.html'):
            self.send_error(404)
            return None
        return super().send_head()

port, root = int(sys.argv[1]), sys.argv[2]
httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), functools.partial(Handler, directory=root))
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    pass
'@
$server | python - $Port $PSScriptRoot
