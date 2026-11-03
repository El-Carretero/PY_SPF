param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$vm='C:\Users\Fluke\Documents\Virtual Machines\Windows XP Professional\Windows XP Professional.vmx'
$work='C:\Users\Fluke\Desktop\Spitfire_XP_Test_20261027'
$iso=Join-Path $work 'Spitfire_160_Installer.iso'
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
$utf8=New-Object Text.UTF8Encoding($false,$true)
$running=@(& $vmrun list)
if($LASTEXITCODE -ne 0 -or $running.Count -ne 1 -or $running[0] -ne 'Total running VMs: 0'){
 throw 'Expected zero running VMs; no changes made.'
}
if(@(Get-Process vmware,vmware-vmx -ErrorAction SilentlyContinue).Count){
 throw 'Close VMware UI and all VM processes before changing VMX.'
}
if((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne 'b4d6b59775448b7f1e6cc18bc7a01ad4607b7ded117df0ef28ec2d5091c6ef8a'){
 throw 'Installer ISO hash mismatch.'
}
$oldBytes=[IO.File]::ReadAllBytes($vm)
$old=$utf8.GetString($oldBytes)
if($old -notmatch '(?m)^cleanShutdown = "TRUE"\r?$' -or
   $old -notmatch '(?m)^softPowerOff = "TRUE"\r?$'){
 throw 'VMX does not record a clean guest shutdown.'
}
$present=[regex]::Matches($old,'(?m)^ethernet\d+\.present = "TRUE"\r?$')
if($present.Count -ne 1 -or $present[0].Value -notmatch '^ethernet0\.present'){
 throw 'Unexpected VM network adapter inventory.'
}
$diskLine=[regex]::Match($old,'(?m)^ide1:1\.fileName = "[^"]+"\r?$').Value
if($diskLine -notmatch 'Windows XP Professional-000001\.vmdk'){
 throw 'Unexpected active snapshot disk; inspect before proceeding.'
}
$updates=[ordered]@{
 'ethernet0.connectionType'='hostonly'
 'ethernet0.startConnected'='TRUE'
 'ide1:0.deviceType'='cdrom-image'
 'ide1:0.fileName'=$iso
 'ide1:0.present'='TRUE'
 'ide1:0.startConnected'='TRUE'
}
$new=$old
$newline=if($old.Contains("`r`n")){"`r`n"}else{"`n"}
foreach($key in $updates.Keys){
 $pattern='(?m)^'+[regex]::Escape($key)+' = "[^"]*"(?=\r?$)'
 $matches=[regex]::Matches($new,$pattern)
 if($matches.Count -gt 1){throw "Duplicate VMX setting: $key"}
 $replacement=$key+' = "'+$updates[$key]+'"'
 if($matches.Count -eq 1){
  $new=[regex]::Replace($new,$pattern,[Text.RegularExpressions.MatchEvaluator]{param($m) $replacement})
 }else{
  if(!$new.EndsWith($newline)){$new+=$newline}
  $new+=$replacement+$newline
 }
}
if([regex]::Match($new,'(?m)^ide1:1\.fileName = "[^"]+"\r?$').Value -ne $diskLine){
 throw 'Refusing an unintended active disk change.'
}
$backupDir=Join-Path $work ('before_offline_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
if(Test-Path -LiteralPath $backupDir){throw 'Backup directory collision.'}
New-Item -ItemType Directory -Path $backupDir | Out-Null
$backup=Join-Path $backupDir 'Windows_XP_Professional.vmx'
[IO.File]::WriteAllBytes($backup,$oldBytes)
$temporary=$vm+'.spitfire-'+[Guid]::NewGuid().ToString('N')+'.tmp'
[IO.File]::WriteAllText($temporary,$new,$utf8)
$current=[IO.File]::ReadAllBytes($vm)
if([Convert]::ToBase64String($current) -ne [Convert]::ToBase64String($oldBytes)){
 throw 'VMX changed during preparation; refusing replacement. Temporary file retained.'
}
$running=@(& $vmrun list)
if($LASTEXITCODE -ne 0 -or $running.Count -ne 1 -or $running[0] -ne 'Total running VMs: 0' -or
   @(Get-Process vmware,vmware-vmx -ErrorAction SilentlyContinue).Count){
 throw 'VMware reopened during preparation; no replacement performed.'
}
[IO.File]::Replace($temporary,$vm,(Join-Path $backupDir 'atomic_replace_backup.vmx'))
$verified=$utf8.GetString([IO.File]::ReadAllBytes($vm))
if($verified -ne $new){throw 'VMX read-back mismatch; backup retained.'}
$report=[ordered]@{
 CreatedUtc=[DateTime]::UtcNow.ToString('o');Status='PASS';VmPath=$vm;Backup=$backup
 Changes=$updates;ActiveDiskLinePreserved=$diskLine.Trim();GuestStarted=$false
 PhysicalNetworkChanged=$false;FirewallChanged=$false
 AfterSha256=(Get-FileHash -LiteralPath $vm -Algorithm SHA256).Hash.ToLowerInvariant()
}
$json=$report | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $backupDir 'change_report.json'),$json,$utf8)
$json
