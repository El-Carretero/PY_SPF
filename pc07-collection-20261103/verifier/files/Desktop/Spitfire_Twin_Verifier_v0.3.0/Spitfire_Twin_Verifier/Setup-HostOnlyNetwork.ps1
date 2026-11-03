[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$InterfaceAlias,
    [string]$PythonAddress = "10.19.70.1",
    [string]$DeviceAddress = "10.19.70.13",
    [ValidateRange(8,30)] [int]$PrefixLength = 24,
    [ValidateRange(1,65535)] [int]$Port = 1024,
    [switch]$AllowRoutedAdapter
)

$ErrorActionPreference = "Stop"
$statePath = Join-Path $PSScriptRoot ".spitfire-network-changes.json"
$firewallName = "Spitfire Twin Verifier UDP $Port"
if (Test-Path $statePath) {
    throw "기존 설정 기록이 있습니다. 먼저 .\Undo-HostOnlyNetwork.ps1을 실행하거나 기록 내용을 확인하십시오."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "PowerShell을 관리자 권한으로 실행해야 합니다."
}

$adapter = Get-NetAdapter -InterfaceAlias $InterfaceAlias -ErrorAction Stop
$gateways = @(Get-NetIPConfiguration -InterfaceAlias $InterfaceAlias).IPv4DefaultGateway
if ($gateways.Count -gt 0 -and -not $AllowRoutedAdapter) {
    throw "'$InterfaceAlias'에는 기본 게이트웨이가 있습니다. Host-only 어댑터를 선택하십시오. 의도한 선택이면 -AllowRoutedAdapter를 명시하십시오."
}

$added = @()
$state = [ordered]@{
    interface_alias = $InterfaceAlias
    prefix_length = $PrefixLength
    added_addresses = @()
    firewall_name = $firewallName
    firewall_added = $false
    created_at = (Get-Date).ToString("o")
}
$state | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8
foreach ($address in @($PythonAddress, $DeviceAddress)) {
    $elsewhere = @(Get-NetIPAddress -AddressFamily IPv4 -IPAddress $address -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -ne $InterfaceAlias })
    if ($elsewhere.Count -gt 0) {
        throw "$address 주소가 다른 인터페이스 '$($elsewhere[0].InterfaceAlias)'에서 이미 사용 중입니다."
    }
    $present = @(Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 -IPAddress $address -ErrorAction SilentlyContinue)
    if ($present.Count -eq 0) {
        New-NetIPAddress -InterfaceAlias $InterfaceAlias -IPAddress $address -PrefixLength $PrefixLength -AddressFamily IPv4 | Out-Null
        $added += $address
        $state.added_addresses = @($added)
        $state | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8
        Write-Host "추가: $InterfaceAlias <- $address/$PrefixLength"
    } else {
        Write-Host "이미 존재: $InterfaceAlias <- $address"
    }
}

$firewallAdded = $false
if (-not (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $firewallName -Direction Inbound -Action Allow `
        -Protocol UDP -LocalPort $Port -LocalAddress $DeviceAddress -Profile Private | Out-Null
    $firewallAdded = $true
    $state.firewall_added = $true
    $state | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8
    Write-Host "Private 방화벽 규칙 추가: $firewallName"
}

Write-Host ""
Write-Host "완료. XP VM IPv4를 10.19.70.2 / 255.255.255.0으로 설정하십시오."
Write-Host "되돌리기: 관리자 PowerShell에서 .\Undo-HostOnlyNetwork.ps1"
