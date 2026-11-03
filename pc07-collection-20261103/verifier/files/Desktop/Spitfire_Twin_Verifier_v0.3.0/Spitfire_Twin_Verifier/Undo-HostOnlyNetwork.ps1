$ErrorActionPreference = "Stop"
$statePath = Join-Path $PSScriptRoot ".spitfire-network-changes.json"
if (-not (Test-Path $statePath)) {
    throw "설정 기록 $statePath 이 없습니다. 자동으로 제거할 대상을 추측하지 않습니다."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "PowerShell을 관리자 권한으로 실행해야 합니다."
}

$state = Get-Content $statePath -Raw | ConvertFrom-Json
foreach ($address in @($state.added_addresses)) {
    $items = @(Get-NetIPAddress -InterfaceAlias $state.interface_alias -AddressFamily IPv4 -IPAddress $address -ErrorAction SilentlyContinue)
    foreach ($item in $items) {
        Remove-NetIPAddress -InputObject $item -Confirm:$false
        Write-Host "제거: $($state.interface_alias) <- $address"
    }
}
if ($state.firewall_added) {
    Get-NetFirewallRule -DisplayName $state.firewall_name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Host "방화벽 규칙 제거: $($state.firewall_name)"
}
Remove-Item $statePath -Force
Write-Host "이 스크립트가 추가했던 설정을 제거했습니다."

