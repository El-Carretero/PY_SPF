$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$address = Get-NetIPAddress -AddressFamily IPv4 -IPAddress '10.19.70.13' -ErrorAction Stop
if ($address.InterfaceAlias -notlike '*VMware*VMnet1*') {
    throw '10.19.70.13 must be the configured VMware VMnet1 host-only alias.'
}
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$run = Join-Path $root ('runs\xp_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $run | Out-Null
$argsForEmulator = @('-u', ('"' + (Join-Path $root 'emulator.py') + '"'),
    '--udp-bind','10.19.70.13','--client','10.19.70.2',
    '--output',('"' + $run + '"'),'--duration','3600')
$proc = Start-Process -FilePath $python -WorkingDirectory $root -ArgumentList $argsForEmulator `
    -RedirectStandardOutput (Join-Path $run 'stdout.txt') `
    -RedirectStandardError (Join-Path $run 'stderr.txt') -PassThru
Write-Output ('Emulator PID: ' + $proc.Id)
Write-Output ('Run directory: ' + $run)
Write-Output 'Open VMware XP and launch the original Spitfire shortcut.'
