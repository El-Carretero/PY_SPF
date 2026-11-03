param([string]$Base='C:\Users\Fluke\Desktop\Spitfire_Capture_Runs',[int]$Seconds=600)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
if($Seconds -lt 30 -or $Seconds -gt 900){throw 'Seconds must be 30..900'}
$cleanupErrors=@()
$stamp=[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')
$out=Join-Path $Base $stamp
New-Item -ItemType Directory -Path $out -ErrorAction Stop|Out-Null
foreach($n in @('host_service.py','guest_probe.exe','pcap_audit.py','Prepare-Host.ps1')){Copy-Item (Join-Path $PSScriptRoot $n) (Join-Path $out $n)}
$hta=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'bootstrap.hta')).Replace('SPFCAP_20261101',('SPFCAP_'+$stamp)).Replace('SPFCAP_BOOT_20261101',('SPFCAP_BOOT_'+$stamp)).Replace('SPF safe preflight',('SPF safe preflight '+$stamp))
[IO.File]::WriteAllText((Join-Path $out 'bootstrap.hta'),$hta,[Text.Encoding]::ASCII)
& (Join-Path $out 'Prepare-Host.ps1') -Out $out | Out-File (Join-Path $out 'host-check.log')
$python=(Get-Command python -ErrorAction Stop).Source
$component=@(pktmon list | Where-Object {$_ -match '^\s*(\d+)\s+.*VMware Virtual Ethernet Adapter for VMnet1\s*$'} | ForEach-Object {[regex]::Match($_,'^\s*(\d+)').Groups[1].Value})
if($component.Count -ne 1){throw 'Cannot uniquely identify VMnet1 Pktmon component'}
# This Pktmon workflow requires no existing global filters or capture.
# Save evidence and reject nonempty filters; never clear another capture's configuration.
$st=@(pktmon status);$fl=@(pktmon filter list)
$st|Out-File (Join-Path $out 'pktmon-status-before.txt');$fl|Out-File (Join-Path $out 'pktmon-filters-before.txt')
if(($st -join '
') -notmatch '(not running|\uc2e4\ud589\ub418\uace0 \uc788\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4)'){throw 'Pktmon is active or status language unrecognized'}
if(($fl -join '
') -notmatch '(None|\uC5C6\uC74C)' -or ($fl -join '
') -match '(?m)^\s*\d+\s+'){throw 'Existing Pktmon filters or unrecognized status; no changes made'}
$filter='SPF_PREFLIGHT_'+$stamp;$httpRule=$filter+'_HTTP';$udpRule=$filter+'_UDP';$started=$false;$service=$null;$filterCreated=$false
try {
 New-NetFirewallRule -Name $httpRule -DisplayName $httpRule -Direction Inbound -Action Allow -Protocol TCP -LocalAddress 10.19.70.13 -LocalPort 18978 -RemoteAddress 10.19.70.2 -InterfaceAlias 'VMware Network Adapter VMnet1' -Profile Any|Out-Null
 New-NetFirewallRule -Name $udpRule -DisplayName $udpRule -Direction Inbound -Action Allow -Protocol UDP -LocalAddress 10.19.70.13 -LocalPort 1024 -RemoteAddress 10.19.70.2 -InterfaceAlias 'VMware Network Adapter VMnet1' -Profile Any|Out-Null
 $source='C:\Users\Fluke\Desktop\Spitfire_LogAudit_20261030\reply-values.json'
 $arg='"'+(Join-Path $out 'host_service.py')+'" --root "'+$out+'" --values "'+$source+'" --seconds '+$Seconds
 $service=Start-Process -FilePath $python -ArgumentList $arg -PassThru -RedirectStandardOutput (Join-Path $out 'service.stdout.txt') -RedirectStandardError (Join-Path $out 'service.stderr.txt')
 Start-Sleep -Seconds 2
 $ep=Get-NetUDPEndpoint -LocalAddress 10.19.70.13 -LocalPort 1024 -ErrorAction Stop
 if($ep.OwningProcess -ne $service.Id){throw 'Unexpected simulator owner'}
 pktmon filter add $filter -i 10.19.70.2 -t UDP -p 1024 | Out-File (Join-Path $out 'capture.log')
 if($LASTEXITCODE -ne 0){throw 'Filter failed'};$filterCreated=$true
 pktmon start --capture --comp $component[0] --pkt-size 0 --file-name (Join-Path $out 'preflight.etl') --file-size 32 --log-mode multi-file | Out-File (Join-Path $out 'capture.log') -Append
 if($LASTEXITCODE -ne 0){throw 'Capture start failed; existing session was not stopped'};$started=$true
 Write-Host 'In XP Run once: mshta http://10.19.70.13:18978/bootstrap.hta'
 Write-Host 'No original Spitfire launch; this diagnostic only records existing Opt-out.'
 $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
 while([DateTime]::UtcNow -lt $deadline -and !(Test-Path (Join-Path $out 'received\bootstrap-status.txt')) -and !$service.HasExited){Start-Sleep -Seconds 1;$service.Refresh()}
}
finally {
 if($started){pktmon counters | Out-File (Join-Path $out 'capture-counters.txt');pktmon stop | Out-File (Join-Path $out 'capture-stop.txt');if($LASTEXITCODE -ne 0){$cleanupErrors+='Pktmon stop failed'}}
 if($filterCreated){pktmon filter remove $filter | Out-File (Join-Path $out 'capture-filter-cleanup.txt');if($LASTEXITCODE -ne 0){$cleanupErrors+='Filter removal failed'}}
 New-Item -ItemType File -Path (Join-Path $out 'STOP') -Force|Out-Null
 if($service){$service.WaitForExit(5000)|Out-Null}
 foreach($name in @($httpRule,$udpRule)){Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue|Remove-NetFirewallRule}
}
if($cleanupErrors.Count){throw ($cleanupErrors -join '; ')}
$etl=@(Get-ChildItem $out -Filter 'preflight*.etl' | Sort-Object LastWriteTime)
if(!$etl.Count){throw 'No ETL capture segments'}
$segments=@(foreach($part in $etl){
 $converted=Join-Path $out ('segment-'+$part.BaseName+'.pcapng')
 pktmon etl2pcap $part.FullName --out $converted | Out-File (Join-Path $out 'conversion.log') -Append
 if($LASTEXITCODE -ne 0){throw 'Pktmon segment conversion failed'}
 $converted
})
$combined=[IO.File]::Create((Join-Path $out 'preflight.pcapng'))
try {foreach($part in $segments){$segmentStream=[IO.File]::OpenRead($part);try{$segmentStream.CopyTo($combined)}finally{$segmentStream.Dispose()}}}finally{$combined.Dispose()}
# Multiple pcapng sections preserve all segments and their timestamp metadata.
& $python (Join-Path $out 'pcap_audit.py') (Join-Path $out 'preflight.pcapng') (Join-Path $out 'preflight.pcap') --provenance diagnostic
if($LASTEXITCODE -ne 0){throw 'Capture validation failed; artifacts retained, no success claimed'}
Write-Host ('Evidence: '+$out)
