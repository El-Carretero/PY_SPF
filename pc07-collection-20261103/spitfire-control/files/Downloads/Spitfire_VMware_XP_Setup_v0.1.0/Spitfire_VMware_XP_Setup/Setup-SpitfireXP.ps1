# Windows PowerShell 5.1. Creates a NEW virtual machine; never reuses an existing disk.
[CmdletBinding()]
param(
    [string]$XpIso = '',
    [string]$VmwareInstaller = '',
    [string]$DestinationParent = '',
    [switch]$NoLaunch,
    [switch]$ValidateOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Stage = 'preflight'
$script:InstallPage = 'https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion'

function Select-LocalFile([string]$Title, [string]$Filter) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    try {
        $dialog.Title = $Title
        $dialog.Filter = $Filter
        $dialog.CheckFileExists = $true
        $dialog.Multiselect = $false
        $downloads = Join-Path $env:USERPROFILE 'Downloads'
        if (Test-Path -LiteralPath $downloads) { $dialog.InitialDirectory = $downloads }
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return '' }
        return $dialog.FileName
    } finally { $dialog.Dispose() }
}

function Find-Workstation {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($name in @('ProgramFiles', 'ProgramFiles(x86)')) {
        $base = [Environment]::GetEnvironmentVariable($name)
        if ($base) { $candidates.Add((Join-Path $base 'VMware\VMware Workstation\vmware.exe')) }
    }
    foreach ($key in @('HKLM:\SOFTWARE\VMware, Inc.\VMware Workstation',
                       'HKLM:\SOFTWARE\WOW6432Node\VMware, Inc.\VMware Workstation')) {
        $item = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if ($null -ne $item) {
            $prop = $item.PSObject.Properties['InstallPath']
            if ($null -ne $prop -and $prop.Value) {
                $candidates.Add((Join-Path ([string]$prop.Value) 'vmware.exe'))
            }
        }
    }
    foreach ($file in $candidates) {
        if (Test-Path -LiteralPath $file -PathType Leaf) { return $file }
    }
    return ''
}

function Assert-VendorExecutable([string]$File) {
    $sig = Get-AuthenticodeSignature -LiteralPath $File
    if ($sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate) {
        throw "Windows did not validate the executable signature: $File. Use the official VMware/Broadcom installer."
    }
    $subject = $sig.SignerCertificate.Subject
    if ($subject -notmatch '(?i)(?:^|,\s*)(?:CN|O)\s*=\s*"?(?:VMware|Broadcom)(?:\b|\s)') {
        throw "The executable signer is not identified as VMware/Broadcom. This executable was not launched."
    }
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on the Windows 10/11 host PC.' }
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'A 64-bit Windows host is required.' }
    $windowsBuild = [Environment]::OSVersion.Version.Build
    if ($windowsBuild -lt 10240) { throw 'This helper requires Windows 10/11, not Windows XP.' }
    $templateDirectory = Join-Path $PSScriptRoot 'templates'
    $diskTemplate = Join-Path $templateDirectory 'blank-xp.vmdk'
    $vmxTemplate = Join-Path $templateDirectory 'Spitfire-XP.vmx.template'
    foreach ($file in @($diskTemplate, $vmxTemplate)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing package file: $file" }
    }
    $expectedDiskHash = '315EA5611A579C4894ECB83BABF9454B5CEC8E761AADD98095EBC68070BA8107'
    if ((Get-FileHash -LiteralPath $diskTemplate -Algorithm SHA256).Hash -ne $expectedDiskHash) {
        throw 'The blank virtual disk template has changed. Re-extract the original ZIP.'
    }
    $templateText = [IO.File]::ReadAllText($vmxTemplate)
    if ($templateText -notmatch '@@XP_ISO@@') { throw 'Missing ISO placeholder in VMX template.' }
    if ($ValidateOnly) {
        Write-Host 'Package preflight OK. No installer launched; no virtual machine created.' -ForegroundColor Green
        exit 0
    }

    Write-Host 'Spitfire VMware XP setup helper' -ForegroundColor Cyan
    Write-Host 'Select a Windows XP Professional SP3 32-bit ISO. Product key entry happens inside XP Setup.'
    if (-not $XpIso) { $XpIso = Select-LocalFile 'Select Windows XP Professional SP3 32-bit ISO' 'ISO image (*.iso)|*.iso' }
    if (-not $XpIso) { Write-Host 'No XP ISO selected. Nothing installed.'; exit 2 }
    $XpIso = (Resolve-Path -LiteralPath $XpIso).ProviderPath
    if ([IO.Path]::GetExtension($XpIso) -ine '.iso' -or -not (Test-Path -LiteralPath $XpIso -PathType Leaf)) {
        throw 'Select an existing .iso file.'
    }
    if ($XpIso -match '["\r\n]' -or $XpIso.StartsWith('\\')) {
        throw 'Copy the ISO to a local disk and use a normal local file path.'
    }

    $script:Stage = 'VMware installation'
    $vmwareExe = Find-Workstation
    if (-not $vmwareExe) {
        Write-Host 'VMware Workstation was not detected. Select its official installer EXE.'
        if (-not $VmwareInstaller) {
            $VmwareInstaller = Select-LocalFile 'Select VMware Workstation installer (Cancel opens official page)' 'VMware installer (*.exe)|*.exe'
        }
        if (-not $VmwareInstaller) {
            Start-Process -FilePath $script:InstallPage
            Write-Host 'Download the Windows Workstation installer, then run this helper again. Nothing installed.'
            exit 2
        }
        $VmwareInstaller = (Resolve-Path -LiteralPath $VmwareInstaller).ProviderPath
        if ([IO.Path]::GetFileName($VmwareInstaller) -notmatch '(?i)^VMware-workstation.*\.exe$') {
            throw 'Select a VMware-workstation*.exe installer from VMware/Broadcom.'
        }
        Assert-VendorExecutable $VmwareInstaller
        Write-Host 'Complete the VMware installer window. Approve the Windows UAC prompt if shown.'
        $installerProcess = Start-Process -FilePath $VmwareInstaller -Verb RunAs -Wait -PassThru
        if ($installerProcess.ExitCode -in @(3010, 1641)) {
            Write-Host 'Installer requested a restart. Restart Windows, then run this helper again. No VM has been created.'
            exit 3
        }
        if ($installerProcess.ExitCode -ne 0) { throw "VMware installer returned $($installerProcess.ExitCode)." }
        $vmwareExe = Find-Workstation
        if (-not $vmwareExe) {
            throw 'VMware is not detected yet. Finish installation/restart Windows, then run this helper again.'
        }
    }
    Assert-VendorExecutable $vmwareExe

    $script:Stage = 'creating new XP virtual machine'
    if (-not $DestinationParent) { $DestinationParent = Join-Path $env:USERPROFILE 'Virtual Machines' }
    $DestinationParent = [IO.Path]::GetFullPath($DestinationParent)
    if ($DestinationParent.StartsWith('\\')) { throw 'Select a local destination directory.' }
    [IO.Directory]::CreateDirectory($DestinationParent) | Out-Null
    $suffix = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $vmDirectory = Join-Path $DestinationParent ('Spitfire-XP-' + $suffix)
    # Each run uses a new directory. No pre-existing disks, VMs, or physical disks are selected.
    New-Item -ItemType Directory -Path $vmDirectory -ErrorAction Stop | Out-Null
    $diskPath = Join-Path $vmDirectory 'blank-xp.vmdk'
    Copy-Item -LiteralPath $diskTemplate -Destination $diskPath -ErrorAction Stop
    $vmxPath = Join-Path $vmDirectory 'Spitfire-XP.vmx'
    $vmxText = $templateText.Replace('@@XP_ISO@@', $XpIso)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($vmxPath, $vmxText, $utf8)
    $state = [ordered]@{
        helper_version = '0.1.0'
        stage = 'VM_CREATED_XP_NOT_INSTALLED'
        created_utc = [DateTime]::UtcNow.ToString('o')
        vmx = $vmxPath
        xp_iso = $XpIso
        vmware = $vmwareExe
        memory_mb = 1024
        cpu_count = 1
        disk_gib = 20
        firmware = 'bios'
        network = 'hostonly (VMnet1 default)'
        windows_xp_installed = $false
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $vmDirectory 'setup-status.json') -Encoding UTF8
    Write-Host "VM created: $vmxPath" -ForegroundColor Green
    Write-Host 'XP has NOT been installed yet. VMware will boot the selected ISO.' -ForegroundColor Yellow
    Write-Host 'In the XP Setup window: Enter, F8, select the 20 GB virtual disk, NTFS quick format, then your product key.'
    Write-Host 'At the first reboot, do not press a key to boot from the CD again.'
    Write-Host 'If VMware asks whether this VM was moved or copied, select I Copied It.'
    Write-Host 'This helper does not set host or guest IP addresses. See NEXT_STEPS_KO.txt after XP installation.'
    if (-not $NoLaunch) {
        $script:Stage = 'opening VMware'
        Start-Process -FilePath $vmwareExe -ArgumentList @('-x', ('"' + $vmxPath + '"')) | Out-Null
    }
    exit 0
} catch {
    Write-Host "Stopped at: $script:Stage" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'No claim of a completed XP installation is made. Keep any created VM directory for inspection.'
    exit 1
}
