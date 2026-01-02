Param(
  [switch]$Tunnel,
  [int]$Port = 5000
)

$cwd = Split-Path -Parent $MyInvocation.MyCommand.Path

Function Get-PrimaryIPv4 {
  try {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -InterfaceOperationalStatus Up |
      Where-Object { $_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1' } |
      Select-Object -ExpandProperty IPAddress
    if ($ips -and $ips.Count -gt 0) { return $ips[0] }
  } catch {
    try {
      $cfg = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled }
      if ($cfg -and $cfg.IPAddress) {
        foreach ($ip in $cfg.IPAddress) {
          if ($ip -and $ip -notlike '169.*' -and $ip -ne '127.0.0.1') { return $ip }
        }
      }
    } catch { }
  }
  return '127.0.0.1'
}

$ip = Get-PrimaryIPv4
Write-Host "Starting MWACSMED IT ASSET REG pilot server on port $Port..." -ForegroundColor Green

Try {
  Start-Process -FilePath "python" -ArgumentList "run_waitress.py" -WorkingDirectory $cwd
  Start-Sleep -Seconds 2
  $localUrl = "http://127.0.0.1:$Port/login"
  $lanUrl = "http://$ip:$Port/login"
  Start-Process $localUrl
  if ($ip -ne '127.0.0.1') {
    Write-Host "LAN URL: $lanUrl" -ForegroundColor Cyan
  }
  Write-Host "Local URL: $localUrl" -ForegroundColor Cyan
} Catch {
  Write-Host "Failed to start server. Ensure Python and dependencies are installed." -ForegroundColor Red
}

if ($Tunnel) {
  if (Get-Command ngrok -ErrorAction SilentlyContinue) {
    Write-Host "Starting ngrok tunnel..." -ForegroundColor Yellow
    Start-Process -FilePath "ngrok" -ArgumentList "http $Port"
  } elseif (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    Write-Host "Starting Cloudflare Tunnel..." -ForegroundColor Yellow
    Start-Process -FilePath "cloudflared" -ArgumentList "tunnel --url http://127.0.0.1:$Port"
  } else {
    Write-Host "No tunneling tool found. Install ngrok or cloudflared to enable public link." -ForegroundColor Red
  }
}
