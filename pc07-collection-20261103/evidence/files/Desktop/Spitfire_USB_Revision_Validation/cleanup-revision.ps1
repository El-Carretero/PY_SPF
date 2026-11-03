$ErrorActionPreference='Stop'
$r='C:\Users\Fluke\Desktop\Spitfire_USB_Revision_Validation'
$v='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
if(!(Test-Path -LiteralPath ($r+'\received\rev-final-quit-complete.txt'))){throw 'Guest transport quit evidence required'}
if(!(Test-Path -LiteralPath ($r+'\guest-cleanup-verified.json'))){throw 'Guest font/original cleanup verification required'}
$active=@(& $vmrun list)
if($active -contains $v){throw 'Guest must be fully powered off before VMX cleanup'}
if(Get-NetTCPConnection -LocalPort 18979 -State Listen -ErrorAction SilentlyContinue){throw 'Fixture HTTP still active'}
if(Get-NetUDPEndpoint -LocalPort 1024 -ErrorAction SilentlyContinue | Where-Object {$_.LocalAddress -eq '10.19.70.13'}){throw 'Fixture UDP still active'}
foreach($name in @('Spitfire USB revision HTTP hostonly','Spitfire USB revision UDP hostonly')){
 $rules=@(Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)
 if($rules.Count -gt 1){throw 'Unexpected duplicate revision firewall rule'}
 if($rules.Count -eq 1){$rules | Remove-NetFirewallRule}
}
$before=[IO.File]::ReadAllText($v)
$after=[regex]::Replace($before,'(?im)^remoteDisplay\.vnc\.[^\r\n]*(?:\r?\n|$)','')
if($after -eq $before){throw 'Temporary VNC keys absent unexpectedly'}
[IO.File]::WriteAllText($v,$after,(New-Object Text.UTF8Encoding($false)))
Remove-Item -LiteralPath ($r+'\console-password.tmp') -Force
$ics=New-Object -ComObject HNetCfg.HNetShare
$sharing=@($ics.EnumEveryConnection | ForEach-Object {$ics.INetSharingConfigurationForINetConnection($_).SharingEnabled})
$forward=@(Get-NetIPInterface | Where-Object {$_.Forwarding -ne 'Disabled'} | Select-Object InterfaceAlias,AddressFamily,Forwarding)
$record=@{utc=[DateTime]::UtcNow.ToString('o');baseline_vm_power='off';final_vm_power='off';running_vms=@(& $vmrun list);only_vnc_keys_removed=$true;secret_removed=(!(Test-Path -LiteralPath ($r+'\console-password.tmp')));remaining_vnc_keys=@([IO.File]::ReadAllLines($v) | Where-Object {$_ -like 'remoteDisplay.vnc.*'});remaining_tcp_listeners=@(Get-NetTCPConnection -LocalPort 18979,5905 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort);remaining_udp_1024=@(Get-NetUDPEndpoint -LocalPort 1024 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort);remaining_rules=@(Get-NetFirewallRule -DisplayName 'Spitfire USB revision *' -ErrorAction SilentlyContinue | Select-Object DisplayName);forwarding_enabled=$forward;ics_sharing_flags=$sharing;bridge_bindings=@(Get-NetAdapterBinding -ComponentID ms_bridge -ErrorAction SilentlyContinue | Where-Object Enabled | Select-Object Name,ComponentID,Enabled);vmx_sha256=(Get-FileHash -LiteralPath $v).Hash.ToLower();physical_original_accessed=$false}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ($r+'\cleanup-final.json') -Encoding UTF8
$record | ConvertTo-Json -Depth 5
