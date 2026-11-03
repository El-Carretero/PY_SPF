$ErrorActionPreference='Stop'
$r='C:\Users\Fluke\Desktop\Spitfire_USB_Revision_Validation'
$v='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
$active=@(& $vmrun list)
if($active -contains $v -or (Get-Process vmware-vmx -ErrorAction SilentlyContinue)){throw 'VM must be stopped before temporary console configuration'}
$lines=[IO.File]::ReadAllLines($v)
$nic=@($lines | Where-Object {$_ -match '^ethernet\d+\.present\s*=\s*"TRUE"'})
if($nic.Count -ne 1 -or !($lines -contains 'ethernet0.connectionType = "hostonly"')){throw 'Expected single host-only VM adapter'}
if(@($lines | Where-Object {$_ -match '^remoteDisplay\.vnc\.'}).Count){throw 'VNC configuration already exists'}
if(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$_.LocalPort -in 5905,18979}){throw 'Temporary TCP port already in use'}
if(Get-NetUDPEndpoint -LocalPort 1024 -ErrorAction SilentlyContinue){throw 'UDP1024 already in use'}
if(Get-NetIPInterface -AddressFamily IPv4 | Where-Object {[int]$_.Forwarding -ne 0}){throw 'Host forwarding enabled'}
if((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters').IPEnableRouter -ne 0){throw 'IP router enabled'}
if(Get-NetAdapterBinding -ComponentID ms_bridge -ErrorAction SilentlyContinue){throw 'Bridge binding exists'}
$share=New-Object -ComObject HNetCfg.HNetShare
$ics=@($share.EnumEveryConnection() | ForEach-Object {$p=$share.NetConnectionProps($_);$c=$share.INetSharingConfigurationForINetConnection($_);[pscustomobject]@{name=[string]$p.Name;enabled=[bool]$c.SharingEnabled}})
if($ics | Where-Object {$_.enabled}){throw 'ICS sharing enabled'}
if(!(Get-NetIPAddress -InterfaceAlias 'VMware Network Adapter VMnet1' -IPAddress '10.19.70.13' -ErrorAction SilentlyContinue)){throw 'Required simulator hostonly IP absent'}
Copy-Item -LiteralPath $v -Destination ($r+'\vmx-before-revision.vmx')
[pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');vm_was_running=$false;vmx_ethernet=@($lines | Where-Object {$_ -match '^ethernet'});ics=$ics;forwarding_enabled=$false;router_enabled=$false;bridge_present=$false;original_controller_accessed=$false;vmx_sha256=(Get-FileHash -LiteralPath $v).Hash.ToLower()} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ($r+'\isolation-before.json') -Encoding UTF8
$random=New-Object byte[] 4
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($random);$rng.Dispose()
$password=([BitConverter]::ToString($random)).Replace('-','')
[IO.File]::WriteAllText(($r+'\console-password.tmp'),$password,[Text.Encoding]::ASCII)
$keys=@('remoteDisplay.vnc.enabled = "TRUE"','remoteDisplay.vnc.port = "5905"','remoteDisplay.vnc.ip = "127.0.0.1"',('remoteDisplay.vnc.password = "'+$password+'"'))
$nl=[Environment]::NewLine
[IO.File]::WriteAllText($v,([IO.File]::ReadAllText($v).TrimEnd()+$nl+($keys -join $nl)+$nl),(New-Object Text.UTF8Encoding($false)))
New-NetFirewallRule -DisplayName 'Spitfire USB revision HTTP hostonly' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18979 -LocalAddress 10.19.70.13 -RemoteAddress 10.19.70.2 -InterfaceAlias 'VMware Network Adapter VMnet1' | Out-Null
New-NetFirewallRule -DisplayName 'Spitfire USB revision UDP hostonly' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 1024 -LocalAddress 10.19.70.13 -RemoteAddress 10.19.70.2 -InterfaceAlias 'VMware Network Adapter VMnet1' | Out-Null
$p=Start-Process -FilePath 'C:\Users\Fluke\AppData\Local\Programs\Python\Python313\python.exe' -ArgumentList @(($r+'\harness_server.py'),'--root',$r,'--values',($r+'\reply-values-optout1.json'),'--seconds','3600') -WindowStyle Hidden -PassThru -RedirectStandardOutput ($r+'\server.stdout.txt') -RedirectStandardError ($r+'\server.stderr.txt')
[pscustomobject]@{fixture_pid=$p.Id;vnc_password_recorded_not_printed=$true;original_was_started=$false;temporary_rules=2} | ConvertTo-Json -Compress
