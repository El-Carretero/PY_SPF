<#
Build and read back a data-only installer ISO using Windows built-in IMAPI2FS.
Does not install software, execute setup.exe, change a VM, or use physical media.
Run in Windows PowerShell. Mount-DiskImage verification may require elevation.
The output directory must already exist; no existing image is overwritten.

Primary API references:
https://learn.microsoft.com/windows/win32/api/imapi2fs/nf-imapi2fs-ifilesystemimage-createresultimage
https://learn.microsoft.com/windows/win32/api/imapi2fs/nf-imapi2fs-ifilesystemimageresult-get_imagestream
https://learn.microsoft.com/windows/win32/api/imapi2fs/ne-imapi2fs-fsifilesystems
#>
[CmdletBinding()]
param(
    [string]$SourceDirectory = 'C:\Users\Fluke\Downloads\Spitfire_GUI_v_1_6_0',
    [Parameter(Mandatory = $true)][string]$OutputIso
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$expected = [ordered]@{
    'setup.exe' = '7cab04e301994c56d3f44e6f3cf0f8660327b85cdace6ffb6c3a28c5beb765c4'
    'setup.ini' = '507a0f6b4672579b22f1dee8db0e0772c7694ba11585f1a333d0ccb76fdf25d6'
    'Spitfire.msi' = 'a426077a2ced6d735fbcae9bcc47a69d44230c68433ef66be4b08337d7fc7324'
    'DistFile.cab' = 'dd831a4d9cc6980ee98270b1318dcc641eb315083432962bea7de3d7b0170698'
    'instmsi.exe' = '781effbc345bc4a731ff5279103f51ad098e84d995a9d64216956cf2267bd712'
    'instmsiw.exe' = '69e647aa1f9303461b51b127e55992b160625307ba3d77d1b64985bd4b245ae5'
}

function Confirm-InstallerFiles([string]$Directory) {
    $item = Get-Item -LiteralPath $Directory
    if (-not $item.PSIsContainer -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Installer directory must be a regular directory, not a reparse point.'
    }
    $files = @(Get-ChildItem -LiteralPath $Directory -Force)
    if ($files.Count -ne $expected.Count) {
        throw "Expected exactly six installer files in: $Directory"
    }
    foreach ($file in $files) {
        if ($file.PSIsContainer -or
            ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not $expected.Contains($file.Name)) {
            throw "Unexpected installer entry: $($file.Name)"
        }
    }
    foreach ($name in $expected.Keys) {
        $path = Join-Path $Directory $name
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $expected[$name]) { throw "Installer hash mismatch: $path" }
        [pscustomobject]@{Name=$name;Length=(Get-Item -LiteralPath $path).Length;Sha256=$hash}
    }
}

$source = (Get-Item -LiteralPath $SourceDirectory).FullName
$output = [IO.Path]::GetFullPath($OutputIso)
if ($output -notmatch '^[A-Za-z]:\\' -or [IO.Path]::GetExtension($output) -ne '.iso') {
    throw 'OutputIso must be an absolute local Windows drive path ending in .iso.'
}
if (-not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($output))) {
    throw 'The output parent directory must already exist.'
}
$partial = $output + '.creating.iso'
$manifestPath = $output + '.manifest.json'
foreach ($path in @($output, $partial, $manifestPath)) {
    if (Test-Path -LiteralPath $path) { throw "Refusing to overwrite: $path" }
}
$inputs = @(Confirm-InstallerFiles $source)

if (-not ('SpitfireXpIsoStreamWriter' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class SpitfireXpIsoStreamWriter {
    public static long Write(object source, string output, long expectedBytes) {
        if (expectedBytes <= 0 || expectedBytes > 800L * 1024 * 1024)
            throw new InvalidDataException("Unexpected ISO image size.");
        IStream stream = (IStream)source;
        System.Runtime.InteropServices.ComTypes.STATSTG info;
        stream.Stat(out info, 1); // STATFLAG_NONAME
        if (info.cbSize != expectedBytes)
            throw new InvalidDataException("IStream size differs from IMAPI block count.");
        stream.Seek(0, 0, IntPtr.Zero); // STREAM_SEEK_SET
        IntPtr countPtr = Marshal.AllocCoTaskMem(sizeof(int));
        try {
            long total = 0;
            byte[] buffer = new byte[65536];
            using (FileStream file = new FileStream(output, FileMode.CreateNew,
                       FileAccess.Write, FileShare.None)) {
                while (total < expectedBytes) {
                    int request = (int)Math.Min(buffer.Length, expectedBytes - total);
                    Marshal.WriteInt32(countPtr, 0);
                    stream.Read(buffer, request, countPtr);
                    int count = Marshal.ReadInt32(countPtr);
                    if (count <= 0 || count > request)
                        throw new InvalidDataException("Truncated or invalid ISO stream read.");
                    file.Write(buffer, 0, count);
                    total += count;
                }
                Marshal.WriteInt32(countPtr, 0);
                stream.Read(buffer, 1, countPtr);
                if (Marshal.ReadInt32(countPtr) != 0)
                    throw new InvalidDataException("ISO stream exceeds expected image size.");
                file.Flush(true);
            }
            return total;
        } finally { Marshal.FreeCoTaskMem(countPtr); }
    }
}
'@
}

$image = $null
$result = $null
$stream = $null
try {
    $image = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
    $image.ChooseImageDefaultsForMediaType(2) # IMAPI_MEDIA_TYPE_CDR
    $image.FileSystemsToCreate = 3           # ISO9660 | Joliet
    $image.SessionStartBlock = 0
    $image.VolumeName = 'SPITFIRE160'
    $image.Root.AddTree($source, $false)
    $result = $image.CreateResultImage()
    $bytesExpected = [long]$result.TotalBlocks * [long]$result.BlockSize
    $stream = $result.ImageStream
    $bytesWritten = [SpitfireXpIsoStreamWriter]::Write($stream, $partial, $bytesExpected)
} finally {
    foreach ($com in @($stream, $result, $image)) {
        if ($null -ne $com -and [Runtime.InteropServices.Marshal]::IsComObject($com)) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($com)
        }
    }
}

# Confirm the source did not change, then hash the actual ISO filesystem view.
$null = @(Confirm-InstallerFiles $source)
$mounted = $false
try {
    $disk = Mount-DiskImage -ImagePath $partial -StorageType ISO -Access ReadOnly -PassThru
    $mounted = $true
    $volumes = @($disk | Get-Volume | Where-Object { $_.DriveLetter })
    for ($attempt = 0; $volumes.Count -eq 0 -and $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        $volumes = @(Get-DiskImage -ImagePath $partial | Get-Volume |
                     Where-Object { $_.DriveLetter })
    }
    if ($volumes.Count -ne 1) { throw 'Could not resolve exactly one mounted ISO volume.' }
    $mountedRoot = [string]$volumes[0].DriveLetter + ':\'
    $verified = @(Confirm-InstallerFiles $mountedRoot)
} finally {
    if ($mounted) { Dismount-DiskImage -ImagePath $partial | Out-Null }
}

# Only a fully read-back-verified image receives the final requested name.
[IO.File]::Move($partial, $output)
$manifest = [ordered]@{
    CreatedUtc = [DateTime]::UtcNow.ToString('o')
    Status = 'PASS'
    Scope = 'Data-only ISO creation and mounted filesystem read-back SHA256 verification'
    SourceDirectory = $source
    ImagePath = $output
    ImageBytes = $bytesWritten
    ImageSha256 = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
    FileSystems = @('ISO9660', 'Joliet')
    InputFiles = $inputs
    VerifiedFiles = $verified
    InstallerExecuted = $false
    VirtualMachineChanged = $false
}
$json = $manifest | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText($manifestPath, $json, (New-Object Text.UTF8Encoding $false))
$json
