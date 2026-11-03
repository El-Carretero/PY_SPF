param([string]$Out='C:\Users\Fluke\Desktop\Spitfire_Optout_Run_20261101')
$ErrorActionPreference='Stop'
if([Environment]::MachineName -ine '20255566-p07'){throw 'Wrong host'}
$vm='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
$v=Get-Content -LiteralPath $vm -Raw
if($v -notmatch 'ethernet0.connectionType = "hostonly"'){throw 'Not host-only'}
if($v -match '(ethernet[1-9]|serial[0-9]|parallel[0-9])\.present = "TRUE"'){throw 'Extra network or physical passthrough'}
if($v -match 'usb[^\r\n]*deviceType = "(?!hid|hub)[^"]+"'){throw 'Unexpected USB device'}
$run=& $vmrun list
if($run[0] -ne 'Total running VMs: 1' -or $run[1] -ne $vm){throw 'Unexpected running VMs'}
$ad=Get-NetAdapter -Name 'VMware Network Adapter VMnet1'
$ips=Get-NetIPAddress -InterfaceIndex $ad.ifIndex -AddressFamily IPv4
if('10.19.70.13' -notin $ips.IPAddress){throw 'Host simulator address absent'}
$int=Get-NetIPInterface -AddressFamily IPv4
if(@($int|Where-Object Forwarding -ne 'Disabled').Count){throw 'IPv4 forwarding enabled'}
$bind=Get-NetAdapterBinding -Name $ad.Name
if(@($bind|Where-Object {$_.ComponentID -in @('vmware_bridge','ms_bridge','vms_pp') -and $_.Enabled}).Count){throw 'VMnet1 bridging enabled'}
if(@(Get-NetAdapter|Where-Object InterfaceDescription -match 'MAC Bridge').Count){throw 'Network bridge found'}
$share=New-Object -ComObject HNetCfg.HNetShare
$shares=@(foreach($c in $share.EnumEveryConnection()){ $p=$share.NetConnectionProps($c);$s=$share.INetSharingConfigurationForINetConnection($c);[pscustomobject]@{Name=$p.Name;SharingEnabled=$s.SharingEnabled} })
if(@($shares|Where-Object SharingEnabled).Count){throw 'ICS sharing enabled'}
if(Get-NetUDPEndpoint -LocalPort 1024 -ErrorAction SilentlyContinue){throw 'UDP1024 already in use'}
$routes=Get-NetRoute -AddressFamily IPv4
$simroutes=@($routes|Where-Object {$_.DestinationPrefix -eq '10.19.70.0/24'})
if($simroutes.Count -ne 1 -or $simroutes[0].InterfaceIndex -ne $ad.ifIndex -or $simroutes[0].NextHop -ne '0.0.0.0'){throw 'Ambiguous simulator route'}
$source='C:\Users\Fluke\Desktop\Spitfire_LogAudit_20261030\reply-values.json'
$val=Get-Content $source -Raw|ConvertFrom-Json
if($val.'1068' -notin @('0','1')){throw 'Existing fixture has unknown Opt-out'}
$utc=[DateTime]::UtcNow.ToString('o')
$e=[ordered]@{verified_utc=$utc;host=[Environment]::MachineName;vmx=$vm;vmx_sha256=(Get-FileHash $vm).Hash;running_vms=$run;ipv4_interfaces=@($int|Select-Object InterfaceAlias,InterfaceIndex,Forwarding);vmnet1_ips=@($ips|Select-Object IPAddress,PrefixLength);vmnet1_bindings=@($bind|Select-Object ComponentID,Enabled);sharing=$shares;routes=@($routes|Select-Object DestinationPrefix,NextHop,InterfaceIndex);simulator_source=$source;simulator_sha256=(Get-FileHash $source).Hash;unchanged_optout=$val.'1068';pktmon_version=(Get-Item C:\Windows\System32\pktmon.exe).VersionInfo.FileVersion;scope='p07 only; original physical PC not accessed'}
$e|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 (Join-Path $Out 'host-isolation.json')
Copy-Item -LiteralPath $vm -Destination (Join-Path $Out 'vmx-observed.txt')
$proof=@"
schema=spitfire-isolation-v1
vm_host=20255566-p07
vm_network=hostonly
host_ip_forwarding=disabled
host_ics_on_vmnet1=disabled
host_bridge_on_vmnet1=absent
physical_passthrough=absent
simulator_bind=10.19.70.13:1024
simulator_peer=10.19.70.2
simulator_policy=queries-and-empower-optout-on-only
guest_ip=10.19.70.2
authorization=xp-optout-on-and-readonly-navigation
verified_utc=$utc
"@
[IO.File]::WriteAllText((Join-Path $Out 'host-isolation-proof.txt'),$proof,[Text.Encoding]::ASCII)
$e|ConvertTo-Json -Depth 3
