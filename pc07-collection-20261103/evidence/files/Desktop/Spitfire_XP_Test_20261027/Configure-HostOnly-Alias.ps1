param()
# Revision 2: supersedes the failed persistent-only attempt. This revised script
# has NOT completed a live end-to-end run. Parser validation is syntax-only.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$work='C:\Users\Fluke\Desktop\Spitfire_XP_Test_20261027'
$nic='VMware Network Adapter VMnet1'
$idx=31
$ip='10.19.70.13'
$utf8=New-Object Text.UTF8Encoding($false)
function Save-Json($path,$value){[IO.File]::WriteAllText($path,($value | ConvertTo-Json -Depth 12),$utf8)}
function Same-Value($left,$right){
 (ConvertTo-Json -InputObject $left -Depth 12 -Compress) -eq (ConvertTo-Json -InputObject $right -Depth 12 -Compress)
}
function Get-State {
 [ordered]@{
  Addresses=@(Get-NetIPAddress -AddressFamily IPv4 -PolicyStore ActiveStore | Select-Object InterfaceIndex,IPAddress,PrefixLength,PrefixOrigin,SkipAsSource | Sort-Object InterfaceIndex,IPAddress)
  PersistentAddresses=@(Get-NetIPAddress -AddressFamily IPv4 -PolicyStore PersistentStore | Select-Object InterfaceIndex,IPAddress,PrefixLength,PrefixOrigin,SkipAsSource | Sort-Object InterfaceIndex,IPAddress)
  Interfaces=@(Get-NetIPInterface -AddressFamily IPv4 -PolicyStore ActiveStore | Select-Object InterfaceIndex,Dhcp,Forwarding | Sort-Object InterfaceIndex)
  Routes=@(Get-NetRoute -AddressFamily IPv4 -PolicyStore ActiveStore | Select-Object InterfaceIndex,DestinationPrefix,NextHop,RouteMetric | Sort-Object InterfaceIndex,DestinationPrefix,NextHop)
  PersistentRoutes=@(Get-NetRoute -AddressFamily IPv4 -PolicyStore PersistentStore | Select-Object InterfaceIndex,DestinationPrefix,NextHop,RouteMetric | Sort-Object InterfaceIndex,DestinationPrefix,NextHop)
  Dns=@(Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object InterfaceIndex,ServerAddresses | Sort-Object InterfaceIndex)
 }
}
function Invoke-Native([string[]]$arguments){
 $out=@(& netsh @arguments 2>&1)
 $code=$LASTEXITCODE
 $out | ForEach-Object {Write-Host $_}
 if($code -ne 0){throw "netsh failed with exit code ${code}: $($arguments -join ' ')"}
 $out
}
function Read-Coexistence([string]$store){
 if($store -notin @('active','persistent')){throw 'Unexpected network store'}
 $lines=@(Invoke-Native -arguments @('interface','ipv4','show','interfaces',"interface=$idx",'level=verbose',"store=$store"))
 # Match only the exact coexistence field, never another DHCP setting.
 $pattern='^\s*(?:DHCP\s*/\s*Static\s+IP\s+Coexistence|DHCP\s*/\s*\uace0\uc815\s+IP\s+\ub3d9\uc2dc\s+\uc874\uc7ac|DHCP\s*/\s*\uc815\uc801\s*IP\s*\uacf5\uc874)\s*:\s*(enabled|disabled|\uc0ac\uc6a9|\uc0ac\uc6a9 \uc548 \ud568|\uc0ac\uc6a9\ud558\uc9c0 \uc54a\uc74c|\ud65c\uc131\ud654\ub428|\ube44\ud65c\uc131\ud654\ub428)\s*$'
 $found=@($lines | ForEach-Object {
  $match=[regex]::Match([string]$_,$pattern,[Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if($match.Success){$match.Groups[1].Value}
 })
 if($found.Count -ne 1){throw "Cannot identify exactly one DHCP/static coexistence field in $store store"}
 [pscustomobject]@{Store=$store;Enabled=($found[0] -match '^(enabled|\uc0ac\uc6a9|\ud65c\uc131\ud654\ub428)$');Lines=$lines}
}
function Get-TestAlias([string]$store){
 $policy=if($store -eq 'active'){'ActiveStore'}elseif($store -eq 'persistent'){'PersistentStore'}else{throw 'Unexpected network store'}
 @(Get-NetIPAddress -AddressFamily IPv4 -PolicyStore $policy | Where-Object {$_.InterfaceIndex -eq $idx -and $_.IPAddress -eq $ip})
}
function Assert-Dhcp {
 $current=Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -PolicyStore ActiveStore
 if($current.Dhcp -ne 'Enabled'){throw 'Original DHCP configuration is not enabled'}
}
function Assert-OriginalAddresses($baseline){
 $current=@(Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -PolicyStore ActiveStore | Where-Object {$_.IPAddress -ne $ip} | Select-Object InterfaceIndex,IPAddress,PrefixLength,PrefixOrigin,SkipAsSource | Sort-Object InterfaceIndex,IPAddress)
 $expected=@($baseline.Addresses | Where-Object {$_.InterfaceIndex -eq $idx})
 if(!(Same-Value -left $expected -right $current)){throw 'Original VMnet1 addresses changed'}
}
if(!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator required'}
$a=Get-NetAdapter -InterfaceIndex $idx
if($a.Name -ne $nic -or $a.HardwareInterface -or $a.Status -ne 'Up'){throw 'Unexpected VMnet1 adapter'}
$running=@(& 'C:\Program Files\VMware\VMware Workstation\vmrun.exe' list)
if($LASTEXITCODE -ne 0 -or $running.Count -ne 1 -or $running[0] -ne 'Total running VMs: 0'){throw 'All VMs must remain powered off'}
$before=Get-State
if(@($before.Interfaces | Where-Object {$_.Forwarding -ne 0}).Count){throw 'IPv4 forwarding enabled; inspect isolation'}
Assert-Dhcp
$old=@(Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -PolicyStore ActiveStore)
if($old.Count -ne 1 -or $old[0].IPAddress -ne '192.168.37.1' -or $old[0].PrefixLength -ne 24){throw 'Unexpected existing VMnet1 addresses'}
foreach($key in @('Addresses','PersistentAddresses')){
 if(@($before[$key] | Where-Object {$_.IPAddress -like '10.19.70.*'}).Count){throw "Test address range already configured in $key"}
}
foreach($key in @('Routes','PersistentRoutes')){
 if(@($before[$key] | Where-Object {$_.DestinationPrefix -like '10.19.70.*'}).Count){throw "Test range route exists in $key"}
}
$beforeCoexist=[ordered]@{}
foreach($store in @('persistent','active')){
 $beforeCoexist[$store]=Read-Coexistence -store $store
 if($beforeCoexist[$store].Enabled){throw "Expected original coexistence disabled in $store store; inspect before proceeding"}
}
$dir=Join-Path $work ('host_network_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
if(Test-Path -LiteralPath $dir){throw 'Evidence path collision'}
New-Item -ItemType Directory -Path $dir | Out-Null
Save-Json -path (Join-Path $dir 'before.json') -value $before
Save-Json -path (Join-Path $dir 'before_coexistence.json') -value $beforeCoexist
$coexistAttempted=@()
$aliasAttempted=$false
try {
 # Configure and read back BOTH stores before adding any address.
 foreach($store in @('persistent','active')){
  $coexistAttempted+=$store
  Invoke-Native -arguments @('interface','ipv4','set','interface',"interface=$idx",'dhcpstaticipcoexistence=enabled',"store=$store") | Out-Null
  if(!(Read-Coexistence -store $store).Enabled){throw "Coexistence did not become enabled in $store store"}
  Assert-Dhcp
  Assert-OriginalAddresses -baseline $before
 }
 foreach($store in @('persistent','active')){
  if(!(Read-Coexistence -store $store).Enabled){throw "Coexistence lost in $store store before address addition"}
  if(@(Get-TestAlias -store $store).Count){throw "Test alias appeared in $store store; refusing duplicate addition"}
 }
 $aliasAttempted=$true
 Invoke-Native -arguments @('interface','ipv4','add','address',"name=$idx","address=$ip",'mask=255.255.255.0','skipassource=true','store=persistent') | Out-Null
 Assert-Dhcp
 Assert-OriginalAddresses -baseline $before
 # Do not add active first: it can make a later persistent add fail AlreadyExists.
 # Add live only if persistent add has left the active store without the alias.
 if(@(Get-TestAlias -store 'active').Count -eq 0){
  Invoke-Native -arguments @('interface','ipv4','add','address',"name=$idx","address=$ip",'mask=255.255.255.0','skipassource=true','store=active') | Out-Null
 }
 Assert-Dhcp
 Assert-OriginalAddresses -baseline $before
 $new=@()
 for($i=0;$i -lt 15;$i++){
  $new=@(Get-TestAlias -store 'active')
  if($new.Count -eq 1 -and $new[0].AddressState -eq 'Preferred'){break}
  Start-Sleep -Seconds 1
 }
 if($new.Count -ne 1 -or $new[0].AddressState -ne 'Preferred' -or $new[0].PrefixLength -ne 24 -or !$new[0].SkipAsSource){throw 'Test alias did not become Preferred / expected configuration'}
 $persisted=@(Get-TestAlias -store 'persistent')
 if($persisted.Count -ne 1 -or $persisted[0].PrefixLength -ne 24 -or !$persisted[0].SkipAsSource){throw 'Test alias was not persisted with expected configuration'}
 $after=Get-State
 Save-Json -path (Join-Path $dir 'after.json') -value $after
 foreach($key in @('Interfaces','Dns')){
  if(!(Same-Value -left $before[$key] -right $after[$key])){throw "Existing $key unexpectedly changed"}
 }
 foreach($key in @('Addresses','PersistentAddresses')){
  $withoutNew=@($after[$key] | Where-Object {!($_.InterfaceIndex -eq $idx -and $_.IPAddress -eq $ip)})
  if(!(Same-Value -left $before[$key] -right $withoutNew)){throw "Existing $key unexpectedly changed"}
 }
 foreach($key in @('Routes','PersistentRoutes')){
  $withoutNew=@($after[$key] | Where-Object {!($_.InterfaceIndex -eq $idx -and $_.DestinationPrefix -in @('10.19.70.0/24','10.19.70.13/32','10.19.70.255/32'))})
  if(!(Same-Value -left $before[$key] -right $withoutNew)){throw "Existing $key unexpectedly changed"}
 }
 $afterCoexist=[ordered]@{}
 foreach($store in @('persistent','active')){
  $afterCoexist[$store]=Read-Coexistence -store $store
  if(!$afterCoexist[$store].Enabled){throw "Coexistence lost after alias setup in $store store"}
 }
 Save-Json -path (Join-Path $dir 'after_coexistence.json') -value $afterCoexist
 $report=[ordered]@{Status='PASS';CreatedUtc=[DateTime]::UtcNow.ToString('o');ScriptRevision=2;Interface=$nic;InterfaceIndex=$idx;AddedAddress=$ip;PrefixLength=24;AliasVerifiedInBothStores=$true;DhcpPreserved=$true;ExistingAddressesPreserved=$true;ExistingRoutesPreserved=$true;DnsPreserved=$true;ForwardingDisabled=$true;FirewallChanged=$false;EvidenceDirectory=$dir}
 Save-Json -path (Join-Path $dir 'result.json') -value $report
 $report | ConvertTo-Json
} catch {
 $failure=$_.Exception.Message
 $rollback=@()
 if($aliasAttempted){
  foreach($store in @('persistent','active')){
   try {
    if(@(Get-TestAlias -store $store).Count){
     Invoke-Native -arguments @('interface','ipv4','delete','address',"name=$idx","address=$ip","store=$store") | Out-Null
    }
    if(@(Get-TestAlias -store $store).Count){throw "Test alias remains in $store store"}
   } catch {$rollback+=$_.Exception.Message}
  }
 }
 foreach($store in $coexistAttempted){
  try {
   $wanted=if($beforeCoexist[$store].Enabled){'enabled'}else{'disabled'}
   if((Read-Coexistence -store $store).Enabled -ne $beforeCoexist[$store].Enabled){
    Invoke-Native -arguments @('interface','ipv4','set','interface',"interface=$idx","dhcpstaticipcoexistence=$wanted","store=$store") | Out-Null
   }
   if((Read-Coexistence -store $store).Enabled -ne $beforeCoexist[$store].Enabled){throw "Coexistence was not restored in $store store"}
  } catch {$rollback+=$_.Exception.Message}
 }
 try {
  $current=Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -PolicyStore ActiveStore
  # DHCP is an ActiveStore property that persists across reboot. Avoid the native
  # already-enabled error; never convert the original DHCP lease to a static IP.
  if($current.Dhcp -ne 'Enabled'){
   Invoke-Native -arguments @('interface','ipv4','set','address',"name=$idx",'source=dhcp','store=active') | Out-Null
  }
  Assert-Dhcp
 } catch {$rollback+=$_.Exception.Message}
 $rollbackState=$null
 $rollbackMatches=$false
 try {
  for($i=0;$i -lt 20;$i++){
   $rollbackState=Get-State
   $rollbackMatches=Same-Value -left $before -right $rollbackState
   if($rollbackMatches){break}
   Start-Sleep -Seconds 1
  }
  if(!$rollbackMatches){$rollback+='Network state differs from before; inspect evidence. No broad reset or static lease conversion attempted.'}
 } catch {$rollback+=$_.Exception.Message}
 $rollbackCoexist=[ordered]@{}
 foreach($store in @('persistent','active')){
  try {
   $rollbackCoexist[$store]=Read-Coexistence -store $store
   if($rollbackCoexist[$store].Enabled -ne $beforeCoexist[$store].Enabled){$rollback+="Coexistence differs from before in $store store"}
  } catch {$rollback+=$_.Exception.Message}
 }
 Save-Json -path (Join-Path $dir 'failure.json') -value ([ordered]@{Status='FAIL';ScriptRevision=2;Error=$failure;RollbackVerified=($rollbackMatches -and $rollback.Count -eq 0);RollbackErrors=$rollback;State=$rollbackState;Coexistence=$rollbackCoexist})
 throw "Host-only setup failed: $failure. Rollback errors: $($rollback -join '; ')"
}
