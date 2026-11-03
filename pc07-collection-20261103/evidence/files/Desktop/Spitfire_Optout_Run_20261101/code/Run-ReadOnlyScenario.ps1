param(
 [Parameter(Mandatory=$true)][string]$Root,
 [switch]$EnableOptOut,
 [ValidateRange(30,1200)][int]$ReadyTimeoutSeconds=600,
 [ValidateRange(30,300)][int]$ActionTimeoutSeconds=180,
 [ValidateRange(10,60)][int]$StableSeconds=30
)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root)
$received=Join-Path $Root 'received'
$script:seq=0
$script:previous='inventory'
$script:steps=@()
$script:ownedOriginal=$false
$script:launchPending=$false
$script:ready=$false
$failure=$null
$cleanupErrors=@()
function Read-JsonFile([string]$Path) {
 for($attempt=0;$attempt -lt 10;$attempt++) {
  try { return (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop) }
  catch { if($attempt -eq 9){throw};Start-Sleep -Milliseconds 150 }
 }
}
function Wait-Artifact([string]$Name,[int]$Seconds) {
 $path=Join-Path $received $Name
 $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
 while(!(Test-Path -LiteralPath $path)) {
  if([DateTime]::UtcNow -ge $deadline){throw ('Timed out waiting for guest artifact: '+$Name)}
  Start-Sleep -Milliseconds 500
 }
 return $path
}
function Get-Step([int]$Number,[string]$Action) {
 $prefix=[string]$Number+'-'+$Action
 $result=Read-JsonFile (Join-Path $received ($prefix+'-result.json'))
 $state=Read-JsonFile (Join-Path $received ($prefix+'-original-state.json'))
 $step=[pscustomobject]@{seq=$Number;action=$Action;result=$result;state=$state}
 $script:steps+=$step
 if($result.exit_code -ne 0){throw ('Guest action failed: '+$prefix+' exit='+$result.exit_code)}
 return $step
}
function Invoke-Guest([string]$Action) {
 $next=$script:seq+1
 & (Join-Path $Root 'Issue-Action.ps1') -Seq $next -Action $Action | Out-Null
 $script:seq=$next;$script:previous=$Action
 Wait-Artifact ([string]$next+'-'+$Action+'-complete.txt') $ActionTimeoutSeconds | Out-Null
 $step=Get-Step $next $Action
 Write-Host ('Completed '+$next+' '+$Action)
 return $step
}
function Assert-On($Step) {
 if(!$Step.state.state_valid -or !$Step.state.hash_matches -or $Step.state.emp_optout -ne 1){throw 'Original application Empower Opt-out is not verified ON'}
 $fixture=Read-JsonFile (Join-Path $Root 'fixture-state.json')
 if($fixture.optout -ne '1'){throw 'Simulator RAM Empower Opt-out is not ON'}
}
try {
 Wait-Artifact 'controller-ready.txt' $ReadyTimeoutSeconds | Out-Null
 $script:ready=$true
 Wait-Artifact '0-inventory-complete.txt' $ActionTimeoutSeconds | Out-Null
 $first=Get-Step 0 'inventory'
 if($first.result.original_exact_count -ne 0 -or $first.result.foreign_original_name){throw 'Close any existing original Spitfire before a new capture; this run will not take ownership of it'}
 $source=Read-JsonFile (Join-Path $Root 'fixture-source.json')
 if($source.initial_optout -ne '1' -and !$EnableOptOut){throw 'Opt-out is OFF in the isolated fixture. Default read-only run stopped before original launch. Use -EnableOptOut only when enabling it is explicitly authorized.'}
 $script:launchPending=$true
 $launch=Invoke-Guest 'launch';$script:ownedOriginal=$true;$script:launchPending=$false
 Start-Sleep -Seconds $StableSeconds
 $state=Invoke-Guest 'inventory'
 if(!$state.state.state_valid -or !$state.state.hash_matches){throw 'Original state/identity could not be verified after startup'}
 if($state.state.emp_optout -eq 0) {
  if(!$EnableOptOut){throw 'Original Opt-out is OFF; no Opt-out input was sent'}
  $service=Invoke-Guest 'regensvc'
  $temperature=Invoke-Guest 'temperature'
  $enabled=Invoke-Guest 'optout_on'
  Assert-On $enabled
 } elseif($state.state.emp_optout -ne 1) { throw 'Unknown Opt-out state' }
 else { Assert-On $state }
 # Show the user-level Temperature panel when startup is already ON.
 if($state.state.gAccessLevel -eq 0 -and $state.state.emp_optout -eq 1){$display=Invoke-Guest 'temperature';Assert-On $display}
 $current=Invoke-Guest 'inventory';Assert-On $current
 if($current.state.gAccessLevel -eq 0){$service=Invoke-Guest 'regensvc';Assert-On $service}
 foreach($action in @('temperature','timing','faults','setup','about')) {
  $display=Invoke-Guest $action;Assert-On $display
 }
 $closed=Invoke-Guest 'exit'
 if($closed.result.original_exact_count -ne 0){throw 'Original application did not exit'}
 $script:ownedOriginal=$false
 $script:launchPending=$true
 $restarted=Invoke-Guest 'launch';$script:ownedOriginal=$true;$script:launchPending=$false
 Start-Sleep -Seconds $StableSeconds
 $restartState=Invoke-Guest 'inventory';Assert-On $restartState
 $display=Invoke-Guest 'temperature';Assert-On $display
 $closed=Invoke-Guest 'exit'
 if($closed.result.original_exact_count -ne 0){throw 'Restarted application did not exit'}
 $script:ownedOriginal=$false
}
catch { $failure=$_.Exception.Message }
finally {
 # Only queue a cleanup Exit if the action in flight has fully uploaded.
 $previousComplete=Join-Path $received ([string]$script:seq+'-'+$script:previous+'-complete.txt')
 if($script:ownedOriginal -and (Test-Path -LiteralPath $previousComplete)) {
  try {$closed=Invoke-Guest 'exit';if($closed.result.original_exact_count -ne 0){throw 'Cleanup Exit did not close original'};$script:ownedOriginal=$false}
  catch {$cleanupErrors+=$_.Exception.Message}
 }
 $previousComplete=Join-Path $received ([string]$script:seq+'-'+$script:previous+'-complete.txt')
 if($script:ready -and (Test-Path -LiteralPath $previousComplete)) {
  try {
   $next=$script:seq+1
   & (Join-Path $Root 'Issue-Action.ps1') -Seq $next -Action 'quit_agent' | Out-Null
   Wait-Artifact ([string]$next+'-quit_agent.txt') 30 | Out-Null
  } catch {$cleanupErrors+=$_.Exception.Message}
 }
 $summary=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');wrapper_end_to_end_previously_tested=$false;enable_optout_explicitly_requested=[bool]$EnableOptOut;success=(!$failure -and !$cleanupErrors.Count);failure=$failure;cleanup_errors=$cleanupErrors;original_may_still_be_running=($script:ownedOriginal -or $script:launchPending);launch_completion_unknown=$script:launchPending;steps=$script:steps;positive_optout_driver_note='Guarded ON path exists, but the original recorded session had a user-confirmed ON transition and the helper subsequently skipped an already-ON state. This wrapper is a new orchestration, not an assertion of prior positive automatic Opt-out validation.'}
 $summary|ConvertTo-Json -Depth 12|Set-Content -Encoding UTF8 (Join-Path $Root 'scenario-result.json')
}
if($failure){throw $failure}
if($cleanupErrors.Count){throw ($cleanupErrors -join '; ')}
Write-Host 'Read-only scenario complete, restart ON verified, original exited.'
