# Opens the Truth Guardian site full screen once its server answers, for TruthGuardian-HTML.bat: Chrome, else Edge,
# as an app window (no address bar, tabs or extensions) started full screen, like a film. F11 leaves full screen and
# Alt+F4 closes it. Its own browser profile in runtime\browser-profile makes it a window of its own even when the
# browser is already open, so the full-screen start always applies; nothing of the user's own profile is touched.
param([int]$Port = 8766)

$url = "http://127.0.0.1:$Port"
for ($i = 0; $i -lt 360; $i++) {
  try {
    if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$url/api/health").StatusCode -eq 200) { break }
  } catch { }
  Start-Sleep -Milliseconds 500
}

$browsers = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)
$browser = $browsers | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $browser) { Start-Process "$url/"; exit 0 }

$profileDir = Join-Path (Split-Path $PSScriptRoot -Parent) "runtime\browser-profile"
Start-Process $browser -ArgumentList @(
  "--user-data-dir=`"$profileDir`"",
  "--no-first-run",
  "--no-default-browser-check",
  "--start-fullscreen",
  "--app=$url/"
)
