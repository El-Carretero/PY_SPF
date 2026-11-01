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

function Get-PythonProbe([string]$Executable, [int]$Bits) {
    $probe = [ordered]@{path = $Executable; required_bits = $Bits; exists = $false;
        compatible = $false; exit_code = $null; stdout = ''; stderr = ''; reason = ''}
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        $probe.reason = 'Executable not found'
        return [PSCustomObject]$probe
    }
    $probe.exists = $true
    $child = $null
    try {
        $code = "import json, struct, sys; bits=struct.calcsize('P')*8; print(json.dumps({'version':sys.version.split()[0],'bits':bits,'executable':sys.executable})); raise SystemExit(not (sys.version_info >= (3,10) and bits == $Bits))"
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $Executable
        $startInfo.Arguments = '-I -c "' + $code + '"'
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $child = New-Object System.Diagnostics.Process
        $child.StartInfo = $startInfo
        $null = $child.Start()
        $stdoutTask = $child.StandardOutput.ReadToEndAsync()
        $stderrTask = $child.StandardError.ReadToEndAsync()
        if (-not $child.WaitForExit(10000)) {
            # A Windows venv launcher can own a child which still holds the
            # output pipes. Stop only this probe's process tree, not Python
            # processes belonging to other applications.
            try {
                & "$env:SystemRoot\System32\taskkill.exe" /PID $child.Id /T /F 2>$null | Out-Null
            } catch { }
            if (-not $child.HasExited) { $child.Kill() }
            $null = $child.WaitForExit(2000)
            $probe.reason = 'Interpreter probe timed out after 10 seconds'
        } else {
            $probe.exit_code = $child.ExitCode
            $probe.reason = 'Interpreter probe failed'
        }
        if ($stdoutTask.Wait(1000)) { $probe.stdout = $stdoutTask.Result.Trim() }
        if ($stderrTask.Wait(1000)) { $probe.stderr = $stderrTask.Result.Trim() }
        if ($probe.exit_code -eq 0) {
            try {
                $identity = $probe.stdout | ConvertFrom-Json
                $probe.compatible = $identity.bits -eq $Bits -and [bool]$identity.executable
            } catch { }
            $probe.reason = if ($probe.compatible) { 'Compatible' } else { 'No matching Python identity returned' }
        }
    } catch {
        $probe.reason = $_.Exception.Message
    } finally {
        if ($child) { $child.Dispose() }
    }
    return [PSCustomObject]$probe
}

function Test-CompatiblePython([string]$Executable, [int]$Bits) {
    $probe = Get-PythonProbe $Executable $Bits
    if (-not (Get-Variable -Name pythonProbeResults -Scope Script -ErrorAction SilentlyContinue)) {
        $script:pythonProbeResults = New-Object 'System.Collections.Generic.List[object]'
    }
    $script:pythonProbeResults.Add($probe)
    return $probe.compatible
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
            $candidates += & $launcher.Source $selector -I -c 'import sys; print(sys.executable)' 2>$null
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

function Find-SetupPython32([string]$Target, [string]$SetupLog) {
    $requested = Join-Path $Target 'python.exe'
    if (Test-CompatiblePython $requested 32) { return $requested }
    $discovered = Find-Python 32
    if ($discovered) { return $discovered }
    # Burn maintenance may ignore TargetDir for already-present MSI packages.
    # Retain the old detected directory as a candidate, even if registration
    # was updated by the maintenance session or a project folder was moved.
    if (Test-Path -LiteralPath $SetupLog) {
        foreach ($line in (Get-Content -LiteralPath $SetupLog)) {
            if ($line -match "Setting string variable 'TargetDir' to value '([^']+)'" -and $Matches[1]) {
                $candidate = Join-Path $Matches[1] 'python.exe'
                if (Test-CompatiblePython $candidate 32) { return $candidate }
            }
        }
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
    Write-Host "No compatible 32-bit Python found. Preparing official Python $version ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $signature = if (Test-Path -LiteralPath $installer) { Get-AuthenticodeSignature -LiteralPath $installer } else { $null }
    if (-not $signature -or $signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Python Software Foundation(?:,|$)') {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
    }
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Python Software Foundation(?:,|$)') {
        throw 'The downloaded Python installer does not have a valid Python Software Foundation signature.'
    }
    Write-Host "Installing signed 32-bit Python into $target (no PATH or file-association changes) ..."
    $setupLog = Join-Path $logs 'python32-setup.log'
    $arguments = @('/quiet', '/norestart', 'InstallAllUsers=0', ('TargetDir="{0}"' -f $target),
        'Include_core=1', 'Include_exe=1', 'Include_lib=1', 'Include_pip=1',
        'Include_test=0', 'Include_doc=0', 'Include_launcher=0',
        'InstallLauncherAllUsers=0', 'PrependPath=0', 'AppendPath=0',
        'AssociateFiles=0', 'Shortcuts=0', '/log', ('"{0}"' -f $setupLog))
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Python setup exited with code $($process.ExitCode). See logs\python32-setup.log."
    }
    Write-Host "Python setup exit code: $($process.ExitCode). Checking requested and registered locations ..."
    $executable = Find-SetupPython32 $target $setupLog
    if (-not $executable) {
        # An installed MSI product can report success without recreating files
        # removed with an older project folder. Repair the registered product
        # without supplying a new TargetDir, then discover the actual location.
        Write-Host 'Restoring the registered 32-bit Python installation with signed setup ...'
        $repairLog = Join-Path $logs 'python32-repair.log'
        $repairArguments = @('/repair', '/quiet', '/norestart', 'InstallAllUsers=0',
            '/log', ('"{0}"' -f $repairLog))
        $repair = Start-Process -FilePath $installer -ArgumentList $repairArguments -Wait -PassThru
        Write-Host "Python repair exit code: $($repair.ExitCode)"
        if ($repair.ExitCode -notin @(0, 3010)) {
            throw "Python repair failed with exit code $($repair.ExitCode). See logs\python32-repair.log."
        }
        $executable = Find-SetupPython32 $target $setupLog
        if (-not $executable) { $executable = Find-SetupPython32 $target $repairLog }
        if (-not $executable) {
            $details = "No runnable 32-bit Python found after setup and repair. See logs\python-probes.json, python32-setup.log and python32-repair.log."
            if ($process.ExitCode -eq 3010 -or $repair.ExitCode -eq 3010) {
                $details += ' Windows reported that a restart is required; restart Windows and run install.bat again.'
            }
            throw $details
        }
    }
    Write-Host "Using verified 32-bit Python: $executable"
    return $executable
}

function Invoke-Python([string]$Executable, [string[]]$Arguments) {
    & $Executable -I @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
}

try {
    Start-Transcript -LiteralPath (Join-Path $logs "install-$Mode.log") -Append | Out-Null
    $transcriptStarted = $true
    # These affect child build/installer processes which do not inherit -I.
    # Only this PowerShell process is changed, not the user's saved settings.
    foreach ($name in @('PYTHONHOME', 'PYTHONPATH')) {
        if (Test-Path "Env:$name") {
            Write-Host "Ignoring inherited $name for this installation."
            Remove-Item "Env:$name"
        }
    }
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
    if (Get-Variable -Name pythonProbeResults -Scope Script -ErrorAction SilentlyContinue) {
        foreach ($probe in ($script:pythonProbeResults | Where-Object { -not $_.compatible } | Select-Object -Last 4)) {
            Write-Host "Python check: $($probe.path) -- $($probe.reason); exit=$($probe.exit_code)"
            if ($probe.stderr) { Write-Host $probe.stderr }
        }
    }
} finally {
    if (Get-Variable -Name pythonProbeResults -Scope Script -ErrorAction SilentlyContinue) {
        $script:pythonProbeResults.ToArray() | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $logs 'python-probes.json') -Encoding UTF8
    }
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
exit $result
