$ErrorActionPreference = 'Stop'
$root = 'C:\Users\Fluke\Desktop\Spitfire_XP_Test_20261027'
$run = Join-Path $root 'xp_external_20261027_run01'
$s = Get-Content (Join-Path $run 'status.json') -Raw | ConvertFrom-Json
if ($s.status -ne 'LISTENING' -or $s.last_control_seq -ne 2) { throw 'Unexpected fixture state' }
$stages = @(
    @{seq=3;stage='tdg_module_comm_fault';overrides=@{'1068'='1';'1019'='2048';'1089'='2'}},
    @{seq=4;stage='tdg_module_recovery';overrides=@{'1068'='1';'1089'='4'}},
    @{seq=5;stage='tcu_module_comm_fault';overrides=@{'1068'='1';'1028'='2048';'1089'='8'}},
    @{seq=6;stage='tcu_module_recovery';overrides=@{'1068'='1';'1089'='4'}},
    @{seq=7;stage='head_module_comm_fault';overrides=@{'1068'='1';'1015'='2048';'1089'='4'}},
    @{seq=8;stage='head_module_recovery';overrides=@{'1068'='1';'1089'='4'}}
)
foreach ($stage in $stages) {
    $s = Get-Content (Join-Path $run 'status.json') -Raw | ConvertFrom-Json
    if ($s.status -ne 'LISTENING' -or $s.last_control_seq -ne ($stage.seq - 1)) { throw 'Fixture stopped or stage mismatch' }
    $name = '{0:D6}' -f $stage.seq
    $pending = Join-Path $run ('controls\' + $name + '.pending')
    $target = Join-Path $run ('controls\' + $name + '.json')
    $stage.note = 'Synthetic status only; no physical hardware; external opt-out readback remains 1'
    [IO.File]::WriteAllText($pending, ($stage | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $pending -Destination $target
    Start-Sleep -Seconds 12
    & (Join-Path $root 'VM-LiveConsole.ps1') -Action capture -Name ('module_' + $name + '_' + $stage.stage)
    $s = Get-Content (Join-Path $run 'status.json') -Raw | ConvertFrom-Json
    [pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');stage=$s.stage;last_seq=$s.last_control_seq;transactions=$s.transactions} | ConvertTo-Json -Compress
}
