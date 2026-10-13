$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
  $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
  throw 'Python virtual environment was not found.'
}
$cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflaredCommand) {
  throw 'cloudflared was not found.'
}
$allowedHosts = @()
if ($env:DJANGO_ALLOWED_HOSTS) {
  $allowedHosts += $env:DJANGO_ALLOWED_HOSTS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
$allowedHosts += '.trycloudflare.com'
$env:DJANGO_ALLOWED_HOSTS = ($allowedHosts | Select-Object -Unique) -join ','
$trustedOrigins = @()
if ($env:DJANGO_CSRF_TRUSTED_ORIGINS) {
  $trustedOrigins += $env:DJANGO_CSRF_TRUSTED_ORIGINS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
$trustedOrigins += 'https://*.trycloudflare.com'
$env:DJANGO_CSRF_TRUSTED_ORIGINS = ($trustedOrigins | Select-Object -Unique) -join ','
$stdoutPath = Join-Path $env:TEMP ('face-login-' + [guid]::NewGuid().ToString() + '.out')
$stderrPath = Join-Path $env:TEMP ('face-login-' + [guid]::NewGuid().ToString() + '.err')
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @('manage.py', 'runserver', '0.0.0.0:8000') -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
try {
  $ready = $false
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($serverProcess.HasExited) {
      $details = @()
      if (Test-Path -LiteralPath $stderrPath) { $details += Get-Content -LiteralPath $stderrPath -Raw }
      if (Test-Path -LiteralPath $stdoutPath) { $details += Get-Content -LiteralPath $stdoutPath -Raw }
      throw ("The Face Login server did not start. " + ($details -join [Environment]::NewLine))
    }
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
      $ready = $true
      break
    }
  }
  if (-not $ready) {
    throw 'The Face Login server did not open port 8000.'
  }
  Start-Process 'http://127.0.0.1:8000'
  & $cloudflaredCommand.Source tunnel --url 'http://127.0.0.1:8000'
} finally {
  if (-not $serverProcess.HasExited) {
    Stop-Process -Id $serverProcess.Id -Force
  }
  Remove-Item -LiteralPath $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
}
