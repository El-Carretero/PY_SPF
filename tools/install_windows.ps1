[CmdletBinding()]
param(
    [ValidateSet('native', 'qt', 'auto')]
    [string]$Mode = 'native',
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
if ($Mode -eq 'auto') { $Mode = 'native' }
$logs = Join-Path $project 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$transcriptStarted = $false
$result = 1

function Test-CompatiblePython([string]$Executable, [int]$Bits) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -c "import struct, sys; raise SystemExit(not (sys.version_info >= (3, 10) and struct.calcsize('P') * 8 == $Bits))" 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-Python([int]$Bits) {
    $candidates = @()
    if ($Bits -eq 32) {
        $candidates += Join-Path $project '.python32\python.exe'
        $candidates += Join-Path $project '.venv\Scripts\python.exe'
    }
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $selector = if ($Bits -eq 32) { '-3-32' } else { '-3-64' }
            $candidates += & $launcher.Source $selector -c 'import sys; print(sys.executable)' 2>$null
        } catch { }
    }
    $python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($python) { $candidates += $python.Source }
    if ($Bits -eq 32 -and $env:LOCALAPPDATA) {
        $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*-32\python.exe') -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    }
    # Reuse registered custom-location installations before running maintenance
    # setup for an already-installed CPython version.
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $baseKey = $null
            $coreKey = $null
            try {
                $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
                $coreKey = $baseKey.OpenSubKey('Software\Python\PythonCore')
                if ($coreKey) {
                    foreach ($version in $coreKey.GetSubKeyNames()) {
                        $installKey = $coreKey.OpenSubKey("$version\InstallPath")
                        if ($installKey) {
                            try {
                                $executable = $installKey.GetValue('ExecutablePath')
                                if ($executable) { $candidates += [string]$executable }
                                $directory = $installKey.GetValue('')
                                if ($directory) { $candidates += Join-Path $directory 'python.exe' }
                            } finally { $installKey.Close() }
                        }
                    }
                }
            } catch { }
            finally {
                if ($coreKey) { $coreKey.Close() }
                if ($baseKey) { $baseKey.Close() }
            }
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-CompatiblePython $candidate $Bits) { return [string]$candidate }
    }
    return $null
}

function Install-ProjectPython32 {
    $version = '3.13.9'
    $cache = Join-Path $project '.installer-cache'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $installer = Join-Path $cache "python-$version-win32.exe"
    $target = Join-Path $project '.python32'
    $url = "https://www.python.org/ftp/python/$version/python-$version.exe"
    Write-Host "No compatible 32-bit Python found. Downloading official Python $version ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Python Software Foundation(?:,|$)') {
        throw 'The downloaded Python installer does not have a valid Python Software Foundation signature.'
    }
    Write-Host "Installing signed 32-bit Python into $target (no PATH or file-association changes) ..."
    $setupLog = Join-Path $logs 'python32-setup.log'
    $arguments = @('/quiet', '/norestart', 'InstallAllUsers=0', ('TargetDir="{0}"' -f $target),
        'Include_pip=1', 'Include_test=0', 'Include_doc=0', 'Include_launcher=0',
        'InstallLauncherAllUsers=0', 'PrependPath=0', 'AppendPath=0',
        'AssociateFiles=0', 'Shortcuts=0', '/log', ('"{0}"' -f $setupLog))
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Python setup exited with code $($process.ExitCode). See logs\python32-setup.log."
    }
    $executable = Join-Path $target 'python.exe'
    if (-not (Test-CompatiblePython $executable 32)) {
        throw 'Python setup did not produce a working 32-bit Python 3.10 or newer.'
    }
    return $executable
}

function Invoke-Python([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
}

try {
    Start-Transcript -LiteralPath (Join-Path $logs "install-$Mode.log") -Append | Out-Null
    $transcriptStarted = $true
    $bits = if ($Mode -eq 'native') { 32 } else { 64 }
    $venvName = if ($Mode -eq 'native') { '.venv-native' } else { '.venv' }
    $venv = Join-Path $project $venvName
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-CompatiblePython $venvPython $bits)) {
        if ($PythonPath) {
            $basePython = (Resolve-Path -LiteralPath $PythonPath).Path
            if (-not (Test-CompatiblePython $basePython $bits)) {
                throw "$Mode mode requires $bits-bit Python 3.10 or newer; the supplied executable is incompatible."
            }
        } else {
            $basePython = Find-Python $bits
            if (-not $basePython -and $Mode -eq 'native') { $basePython = Install-ProjectPython32 }
            if (-not $basePython) { throw 'Qt mode requires 64-bit Python 3.10 or newer. Install it or supply its executable path.' }
        }
        if (Test-Path -LiteralPath $venv) {
            if ($Mode -ne 'native') { throw 'The existing .venv is incompatible. Move it aside before installing Qt mode.' }
            $backup = "$venv.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')-$([Guid]::NewGuid().ToString('N').Substring(0, 6))"
            Move-Item -LiteralPath $venv -Destination $backup
            Write-Host "Preserved incompatible native environment as $backup"
        }
        Invoke-Python -Executable $basePython -Arguments @('-m', 'venv', $venv)
    }
    if (-not (Test-CompatiblePython $venvPython $bits)) { throw 'The virtual environment interpreter is incompatible.' }
    Write-Host "Installing $Mode mode in $venv ..."
    Invoke-Python -Executable $venvPython -Arguments @('-m', 'ensurepip', '--upgrade')
    Invoke-Python -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
    if ($Mode -eq 'qt') {
        Invoke-Python -Executable $venvPython -Arguments @('-m', 'pip', 'install', '-r', 'requirements.txt')
    }
    Invoke-Python -Executable $venvPython -Arguments @('-m', 'pip', 'install', '.')
    Invoke-Python -Executable $venvPython -Arguments @('-m', 'pip', 'check')
    Write-Host 'Installation completed. No instrument connection was opened.'
    if ($Mode -eq 'native') { Write-Host 'Original NI GUI: run_native.bat    Simulator: run_demo.bat' }
    else { Write-Host 'Qt mode installed in .venv. Existing native environment was preserved.' }
    $result = 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Installation log: $(Join-Path $logs "install-$Mode.log")"
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
exit $result
