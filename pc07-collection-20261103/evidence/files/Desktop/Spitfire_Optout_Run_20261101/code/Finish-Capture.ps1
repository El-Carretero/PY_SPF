$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$r=$PSScriptRoot
$last=Get-Content (Join-Path $r 'received\22-exit-result.json') -Raw|ConvertFrom-Json
if($last.exit_code -ne 0 -or $last.original_exact_count -ne 0){throw 'Original must be confirmed exited'}
& (Join-Path $r 'Issue-Action.ps1') -Seq 23 -Action quit_agent
$until=[DateTime]::UtcNow.AddSeconds(20)
while(!(Test-Path (Join-Path $r 'received\23-quit_agent.txt'))){
 if([DateTime]::UtcNow -gt $until){throw 'Guest controller stop acknowledgement missing'}
 Start-Sleep -Milliseconds 500
}
pktmon counters | Out-File -Encoding utf8 (Join-Path $r 'pktmon-final-counters.txt')
pktmon status | Out-File -Encoding utf8 (Join-Path $r 'pktmon-final-status.txt')
pktmon stop | Out-File -Encoding utf8 (Join-Path $r 'pktmon-stop.txt')
[IO.File]::WriteAllText((Join-Path $r 'STOP'),'capture complete')
Get-NetFirewallRule -Name 'SPF_ORIGINAL_HTTP_20261101','SPF_ORIGINAL_UDP_20261101' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
pktmon filter list | Out-File -Encoding utf8 (Join-Path $r 'pktmon-filters-before-cleanup.txt')
pktmon filter remove | Out-File -Encoding utf8 (Join-Path $r 'pktmon-filter-cleanup.txt')
foreach($f in Get-ChildItem -LiteralPath $r -Filter 'original*.etl'){
 $out=$f.FullName+'.pcapng'
 & pktmon etl2pcap $f.FullName --out $out | Out-File -Encoding utf8 ($f.FullName+'.convert.txt')
 if($LASTEXITCODE -ne 0){throw 'Pktmon conversion failed'}
}
[pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');original_exited=$true;guest_controller_stopped=$true;capture_stopped=$true;temporary_firewall_rules_removed=$true;original_physical_pc_accessed=$false}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $r 'capture-finish.json')
Get-ChildItem -LiteralPath $r -Filter '*.pcapng'|Select Name,Length

