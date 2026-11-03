param(
 [string]$Base='C:\Users\Fluke\Desktop\Spitfire_Original_Runs',
 [switch]$EnableOptOut,
 [ValidateRange(600,3600)][int]$Seconds=2400,
 [ValidateRange(30,1200)][int]$GuestReadyTimeoutSeconds=600
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Run from an elevated p07 PowerShell'}
if([Environment]::MachineName -ine '20255566-p07'){throw 'Wrong host; only 20255566-p07 is allowed'}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')+'_'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$out=Join-Path ([IO.Path]::GetFullPath($Base)) $stamp
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
$files=@('guest_driver.exe','guest_driver.c','optout_guard.c.inc','guest_driver.pe-validation.json','guest_driver.sha256','host_server.py','Prepare-Host.ps1','Issue-Action.ps1','Run-ReadOnlyScenario.ps1','Start-NewRun.ps1','pcap_audit.py','analyze_run.py','DRIVER_README.txt')
foreach($name in $files){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $out $name)}
# Generate per-run copies; never edit the executed historical HTAs.
foreach($name in @('bootstrap.hta','controller-local.hta')) {
 $text=[IO.File]::ReadAllText((Join-Path $PSScriptRoot $name))
 if(!$text.Contains('SPF_ORIGINAL_CAPTURE_20261101')){throw 'Unexpected HTA template; unique guest path replacement not safe'}
 $text=$text.Replace('SPF_ORIGINAL_CAPTURE_20261101',('SPF_ORIGINAL_CAPTURE_'+$stamp)).Replace('SPF_ORIGINAL_BOOT_20261101',('SPF_ORIGINAL_BOOT_'+$stamp)).Replace('SPF original capture 20261101',('SPF original capture '+$stamp))
 [IO.File]::WriteAllText((Join-Path $out $name),$text,[Text.Encoding]::ASCII)
}
New-Item -ItemType Directory -Path (Join-Path $out 'received')|Out-Null
[IO.File]::WriteAllText((Join-Path $out 'control.txt'),'0|inventory',[Text.Encoding]::ASCII)
([ordered]@{utc=[DateTime]::UtcNow.ToString('o');seq=0;action='inventory';previous_seq=$null}|ConvertTo-Json -Compress)|Set-Content -Encoding ASCII (Join-Path $out 'actions-issued.jsonl')
$python=(Get-Command python -ErrorAction Stop).Source
& $python -c 'import sys; assert sys.version_info >= (3,9)'
if($LASTEXITCODE -ne 0){throw 'Python runtime check failed'}
& (Join-Path $out 'Prepare-Host.ps1') -Out $out | Out-File (Join-Path $out 'host-check.log')
if(Get-NetTCPConnection -State Listen -LocalPort 18979 -ErrorAction SilentlyContinue){throw 'HTTP18979 already occupied'}
$list=@(& pktmon list);if($LASTEXITCODE -ne 0){throw 'Pktmon list failed'}
$list|Out-File (Join-Path $out 'pktmon-components-before.txt')
$component=@($list|Where-Object {$_ -match '^\s*(\d+)\s+.*VMware Virtual Ethernet Adapter for VMnet1\s*$'}|ForEach-Object {[regex]::Match($_,'^\s*(\d+)').Groups[1].Value})
if($component.Count -ne 1){throw 'Cannot uniquely identify current VMnet1 Pktmon component'}
$status=@(& pktmon status);if($LASTEXITCODE -ne 0){throw 'Pktmon status failed'}
$filters=@(& pktmon filter list);if($LASTEXITCODE -ne 0){throw 'Pktmon filter list failed'}
$status|Out-File (Join-Path $out 'pktmon-status-before.txt')
$filters|Out-File (Join-Path $out 'pktmon-filters-before.txt')
if(($status -join "`n") -notmatch '(not running|\uc2e4\ud589\ub418\uace0 \uc788\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4)'){throw 'Pktmon is active or status language unrecognized; no existing session will be stopped'}
if(($filters -join "`n") -notmatch '(None|\uC5C6\uC74C)' -or ($filters -join "`n") -match '(?m)^\s*\d+\s+'){throw 'Existing Pktmon filters or unrecognized status; no existing filter will be removed'}
$source='C:\Users\Fluke\Desktop\Spitfire_LogAudit_20261030\reply-values.json'
$fixture=Get-Content -LiteralPath $source -Raw|ConvertFrom-Json
if($fixture.'1068' -notin @('0','1') -or $fixture.'1067' -ne 'INT' -or $fixture.'1085' -ne '0'){throw 'Fixture does not match reviewed initial policy'}
$filter='SPF_ORIGINAL_'+$stamp
$createdRules=@();$filterCreated=$false;$captureStarted=$false;$service=$null
$failure=$null;$cleanupErrors=@()
try {
 foreach($spec in @(@('HTTP','TCP',18979),@('UDP','UDP',1024))) {
  $name=$filter+'_'+$spec[0]
  New-NetFirewallRule -Name $name -DisplayName $name -Direction Inbound -Action Allow -Protocol $spec[1] -LocalAddress 10.19.70.13 -LocalPort $spec[2] -RemoteAddress 10.19.70.2 -InterfaceAlias 'VMware Network Adapter VMnet1' -Profile Any|Out-Null
  $createdRules+=$name
 }
 $arguments='"'+(Join-Path $out 'host_server.py')+'" --root "'+$out+'" --values "'+$source+'" --seconds '+$Seconds
 $service=Start-Process -FilePath $python -ArgumentList $arguments -PassThru -RedirectStandardOutput (Join-Path $out 'server.stdout.txt') -RedirectStandardError (Join-Path $out 'server.stderr.txt')
 $deadline=[DateTime]::UtcNow.AddSeconds(15)
 do {
  Start-Sleep -Milliseconds 400;$service.Refresh()
  if($service.HasExited){throw 'Isolated simulator exited during startup'}
  $udp=Get-NetUDPEndpoint -LocalAddress 10.19.70.13 -LocalPort 1024 -ErrorAction SilentlyContinue
  $http=Get-NetTCPConnection -LocalAddress 10.19.70.13 -LocalPort 18979 -State Listen -ErrorAction SilentlyContinue
 } while((!$udp -or !$http) -and [DateTime]::UtcNow -lt $deadline)
 if(!$udp -or !$http -or @($udp|Where-Object OwningProcess -ne $service.Id).Count -or @($http|Where-Object OwningProcess -ne $service.Id).Count){throw 'Simulator/HTTP port ownership is not the process just started'}
 & pktmon filter add $filter -i 10.19.70.2 -t UDP -p 1024 | Out-File (Join-Path $out 'capture.log')
 if($LASTEXITCODE -ne 0){throw 'Own Pktmon filter creation failed'};$filterCreated=$true
 & pktmon start --capture --comp $component[0] --pkt-size 0 --file-name (Join-Path $out 'original.etl') --file-size 64 --log-mode multi-file | Out-File (Join-Path $out 'capture.log') -Append
 if($LASTEXITCODE -ne 0){throw 'Capture start failed; no existing session will be stopped'};$captureStarted=$true
 [ordered]@{utc=[DateTime]::UtcNow.ToString('o');session=$stamp;root=$out;guest_directory=('C:\SPF_ORIGINAL_CAPTURE_'+$stamp);pktmon_component=$component[0];server_pid=$service.Id;explicit_enable_optout=[bool]$EnableOptOut;new_wrapper_end_to_end_tested=$false}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $out 'session.json')
 Write-Host ('Capture ready. Fresh evidence directory: '+$out)
 Write-Host 'Run once INSIDE XP Start > Run: mshta http://10.19.70.13:18979/bootstrap.hta'
 Write-Host 'This fresh run needs a new guest-local controller; VMware Tools are not assumed.'
 & (Join-Path $out 'Run-ReadOnlyScenario.ps1') -Root $out -EnableOptOut:$EnableOptOut -ReadyTimeoutSeconds $GuestReadyTimeoutSeconds
}
catch {$failure=$_.Exception.Message}
finally {
 if($captureStarted) {
  & pktmon counters|Out-File (Join-Path $out 'capture-counters.txt')
  & pktmon stop|Out-File (Join-Path $out 'capture-stop.txt')
  if($LASTEXITCODE -ne 0){$cleanupErrors+='Own Pktmon session did not stop cleanly'}
 }
 if($filterCreated) {
  & pktmon filter remove $filter|Out-File (Join-Path $out 'capture-filter-cleanup.txt')
  if($LASTEXITCODE -ne 0){$cleanupErrors+='Own Pktmon filter removal failed'}
 }
 New-Item -ItemType File -Path (Join-Path $out 'STOP') -Force|Out-Null
 if($service){
  $service.WaitForExit(10000)|Out-Null;$service.Refresh()
  if(!$service.HasExited){try{Stop-Process -InputObject $service -ErrorAction Stop;$cleanupErrors+='Owned simulator required termination after STOP timeout'}catch{$cleanupErrors+='Owned simulator termination failed; inspect server PID in session.json'}}
 }
 foreach($name in $createdRules){try{Get-NetFirewallRule -Name $name -ErrorAction Stop|Remove-NetFirewallRule -ErrorAction Stop}catch{$cleanupErrors+=('Own firewall rule cleanup failed: '+$name)}}
}
# Preserve every ETL segment; pcapng concatenation retains their original sections.
try {
 $segments=@()
 foreach($part in @(Get-ChildItem -LiteralPath $out -Filter 'original*.etl'|Sort-Object Name)) {
  $converted=Join-Path $out ('segment-'+$part.BaseName+'.pcapng')
  & pktmon etl2pcap $part.FullName --out $converted|Out-File (Join-Path $out 'conversion.log') -Append
  if($LASTEXITCODE -ne 0){throw 'ETL segment conversion failed'}
  $segments+=$converted
 }
 if($segments.Count) {
  $combined=[IO.File]::Create((Join-Path $out 'original.pcapng'))
  try{foreach($segment in $segments){$segmentStream=[IO.File]::OpenRead($segment);try{$segmentStream.CopyTo($combined)}finally{$segmentStream.Dispose()}}}finally{$combined.Dispose()}
  & $python (Join-Path $out 'pcap_audit.py') (Join-Path $out 'original.pcapng') (Join-Path $out 'original.pcap') --provenance original
  if($LASTEXITCODE -ne 0){throw 'Capture audit failed: both directions and untruncated packets are required; partial evidence is retained'}
 } else {throw 'No ETL segments were produced'}
 if(Test-Path (Join-Path $out 'udp-original.jsonl')){& $python (Join-Path $out 'analyze_run.py') $out;if($LASTEXITCODE -ne 0){throw 'Communication analysis failed'}}
} catch {if(!$failure){$failure=$_.Exception.Message}else{$cleanupErrors+=$_.Exception.Message}}
[ordered]@{utc=[DateTime]::UtcNow.ToString('o');success=(!$failure -and !$cleanupErrors.Count);failure=$failure;cleanup_errors=$cleanupErrors;root=$out;scope='isolated original XP + synthetic replies only';new_wrapper_end_to_end_tested=$false}|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 (Join-Path $out 'run-result.json')
Get-ChildItem -LiteralPath $out -Recurse -File|Where-Object Name -ne 'artifact-sha256.csv'|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash|Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $out 'artifact-sha256.csv')
Write-Host ('Evidence retained: '+$out)
if($failure){throw $failure}
if($cleanupErrors.Count){throw ($cleanupErrors -join '; ')}
