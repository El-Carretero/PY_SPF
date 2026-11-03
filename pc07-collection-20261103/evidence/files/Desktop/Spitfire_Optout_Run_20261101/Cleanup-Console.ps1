$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$vm='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
if(!(Test-Path (Join-Path $r 'capture-finish.json'))){throw 'Stop capture and original first'}
$backup=[IO.File]::ReadAllText((Join-Path $r 'vmx-before-console.vmx'))
if($backup -match '(?im)^remoteDisplay\.vnc\.'){throw 'Original VNC settings require exact restoration'}
& $vmrun suspend $vm hard
if($LASTEXITCODE -ne 0){throw 'Could not suspend VM'}
$v=[IO.File]::ReadAllText($vm)
$v=[regex]::Replace($v,'(?im)^remoteDisplay\.vnc\.[^\r\n]*(?:\r?\n)?','')
[IO.File]::WriteAllText($vm,$v,[Text.UTF8Encoding]::new($false))
Remove-Item (Join-Path $r 'console-password.tmp')
[IO.File]::WriteAllText((Join-Path $r 'console-cleanup-pending.txt'),[DateTime]::UtcNow.ToString('o'))
& $vmrun start $vm
if($LASTEXITCODE -ne 0){throw 'Could not resume VM'}
[pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');temporary_vnc_keys_removed=($v -notmatch '(?im)^remoteDisplay\.vnc\.');temporary_password_file_removed=(!(Test-Path (Join-Path $r 'console-password.tmp')));running_vms=(& $vmrun list);vnc_5905_listeners=@(Get-NetTCPConnection -LocalPort 5905 -State Listen -ErrorAction SilentlyContinue).Count;vm_network_hostonly=($v -match 'ethernet0.connectionType = "hostonly"')}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $r 'console-cleanup.json')
