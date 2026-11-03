param([string]$Destination=(Join-Path $PSScriptRoot 'official-downloads'))
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force $Destination|Out-Null
$items=@(
 @{name='Wireshark-win32-1.10.14.exe';url='https://www.wireshark.org/download/win32/all-versions/Wireshark-win32-1.10.14.exe';sha1='37f74c6f3e73550904e621ae2f5ad342be5762f6'},
 @{name='WinPcap_4_1_3.exe';url='https://www.winpcap.org/install/bin/WinPcap_4_1_3.exe';sha1='e2516fcd1573e70334c8f50bee5241cdfdf48a00'}
)
$result=@(foreach($i in $items){
 $file=Join-Path $Destination $i.name
 if(!(Test-Path $file)){Invoke-WebRequest -UseBasicParsing -Uri $i.url -OutFile $file}
 $actual=(Get-FileHash $file -Algorithm SHA1).Hash.ToLowerInvariant()
 $signature=Get-AuthenticodeSignature $file
 $record=[pscustomobject]@{file=$i.name;source=$i.url;bytes=(Get-Item $file).Length;official_sha1=$i.sha1;actual_sha1=$actual;sha1_matches=($actual -eq $i.sha1);sha256=(Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant();authenticode_status=[string]$signature.Status;signer=if($signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null};download_utc=[DateTime]::UtcNow.ToString('o');installed=$false}
 $record
})
$result|ConvertTo-Json -Depth 4|Set-Content -Encoding UTF8 (Join-Path $Destination 'integrity.json')
if(@($result|Where-Object {-not $_.sha1_matches}).Count){throw 'Official digest mismatch; do not install'}
Invoke-WebRequest -UseBasicParsing -Uri 'https://www.wireshark.org/download/src/all-versions/SIGNATURES-1.10.14.txt' -OutFile (Join-Path $Destination 'SIGNATURES-1.10.14.txt')
$result|ConvertTo-Json -Depth 4
# This run uses the Windows host's built-in Pktmon; these XP installers are NOT run.
# Wireshark alternative in XP: Wireshark-win32-1.10.14.exe /S /desktopicon=no /quicklaunchicon=no
# /S DOES NOT install WinPcap. Its official installer is interactive; do not assume /S support.
