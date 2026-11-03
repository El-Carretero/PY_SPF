param([int]$StartSeq=14)
$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$steps=@('timing','faults','setup','about','exit','launch','inventory','temperature','exit')
$n=$StartSeq
foreach($a in $steps){
 if($a -ne 'launch' -and $a -ne 'exit'){
  $state=Get-Content (Join-Path $r 'fixture-state.json') -Raw|ConvertFrom-Json
  if($state.optout -ne '1'){throw 'Opt-out ON fixture condition lost'}
 }
 & (Join-Path $r 'Issue-Action.ps1') -Seq $n -Action $a
 $deadline=[DateTime]::UtcNow.AddSeconds(120)
 $done=Join-Path $r ("received\"+$n+"-"+$a+"-complete.txt")
 while(!(Test-Path $done)){
  if([DateTime]::UtcNow -gt $deadline){throw "Guest action timeout $n $a"}
  Start-Sleep -Milliseconds 700
 }
 $result=Get-Content (Join-Path $r ("received\"+$n+"-"+$a+"-result.json")) -Raw|ConvertFrom-Json
 if($result.exit_code -ne 0){throw "Guest action failed: $n $a code $($result.exit_code)"}
 Write-Output ("Completed "+$n+" "+$a)
 if($a -eq 'launch'){Start-Sleep -Seconds 40}
 $n++
}
Write-Output 'Read-only sequence complete; original exited'
