$ErrorActionPreference='Stop'
$r='C:\Users\Fluke\Desktop\Spitfire_USB_Validation'
$v='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
if (!(Test-Path -LiteralPath ($r+'\received\guest-cleanup-complete.txt'))) {throw 'Guest cleanup evidence required first'}
$stopped=Get-NetTCPConnection -LocalPort 18979 -State Listen -ErrorAction SilentlyContinue
$udp=Get-NetUDPEndpoint -LocalPort 1024 -ErrorAction SilentlyContinue | Where-Object {$_.LocalAddress -eq '10.19.70.13'}
if($stopped -or $udp){throw 'Stop validation fixture and preserve its ledger before console cleanup'}
$rules=@(Get-NetFirewallRule -DisplayName 'Spitfire USB validation hostonly' -ErrorAction SilentlyContinue)
if($rules.Count -gt 1){throw 'Unexpected duplicate validation firewall rule'}
if($rules.Count -eq 1){$rules | Remove-NetFirewallRule}
& $vmrun suspend $v hard
if($LASTEXITCODE -ne 0){throw 'VM suspend failed; VMX not changed'}
$active=& $vmrun list
if($active -contains $v){throw 'VM still running; VMX not changed'}
$before=[IO.File]::ReadAllText($v)
$after=[regex]::Replace($before,'(?im)^remoteDisplay\.vnc\.[^\r\n]*(?:\r?\n|$)','')
if($after -eq $before){throw 'Temporary VNC keys unexpectedly absent'}
[IO.File]::WriteAllText($v,$after,(New-Object Text.UTF8Encoding($false)))
Remove-Item -LiteralPath ($r+'\console-password.tmp') -Force
@{utc=[DateTime]::UtcNow.ToString('o');vm_suspended=$true;only_remoteDisplay_vnc_keys_removed=$true;secret_removed=(!(Test-Path -LiteralPath ($r+'\console-password.tmp')));firewall_rule_removed=(!(Get-NetFirewallRule -DisplayName 'Spitfire USB validation hostonly' -ErrorAction SilentlyContinue));vmx_sha256=(Get-FileHash -LiteralPath $v).Hash.ToLower();physical_original_accessed=$false} | ConvertTo-Json | Set-Content -LiteralPath ($r+'\console-cleanup.json') -Encoding UTF8
& $vmrun start $v
if($LASTEXITCODE -ne 0){throw 'VM resume command failed; inspect retained cleanup record'}
'VM resumed with temporary VNC keys removed; verify listeners separately.'
