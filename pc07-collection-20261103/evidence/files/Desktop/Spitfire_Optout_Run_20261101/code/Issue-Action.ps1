param([Parameter(Mandatory=$true)][int]$Seq,[Parameter(Mandatory=$true)][ValidateSet('inventory','launch','about','temperature','timing','faults','setup','exit','regensvc','close','optout_on','update','quit_agent')][string]$Action)
$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$old=([IO.File]::ReadAllText((Join-Path $r 'control.txt'))).Trim().Split('|')
if($Seq -ne ([int]$old[0]+1)){throw 'Action sequence must increase by exactly one'}
$complete=Join-Path $r ('received\'+$old[0]+'-'+$old[1]+'-complete.txt')
if(!(Test-Path $complete)){throw 'Previous guest action has not uploaded completion'}
$stamp=[DateTime]::UtcNow.ToString('o')
$record=[ordered]@{utc=$stamp;seq=$Seq;action=$Action;previous_seq=[int]$old[0]}
Add-Content -Encoding ASCII -Path (Join-Path $r 'actions-issued.jsonl') -Value ($record|ConvertTo-Json -Compress)
[IO.File]::WriteAllText((Join-Path $r 'control.pending'),([string]$Seq+'|'+$Action),[Text.Encoding]::ASCII)
Move-Item -Force (Join-Path $r 'control.pending') (Join-Path $r 'control.txt')
$record|ConvertTo-Json -Compress
