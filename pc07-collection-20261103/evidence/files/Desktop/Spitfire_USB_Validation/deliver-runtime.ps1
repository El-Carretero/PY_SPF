$ErrorActionPreference='Stop'
$r='C:\Users\Fluke\Desktop\Spitfire_USB_Validation';$desktop='C:\Users\Fluke\Desktop'
$parts=@(Get-ChildItem -LiteralPath $r -Filter 'release-part-*.b64' | Sort-Object Name)
if($parts.Count -ne 23){throw 'Release part count mismatch'}
$b64=($parts | ForEach-Object {[IO.File]::ReadAllText($_.FullName)}) -join ''
if($b64.Length -ne 1790280){throw 'Release base64 length mismatch'}
$data=[Convert]::FromBase64String($b64)
$hash=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($data))).Replace('-','').ToLower()
if($hash -ne '1931bc9a4319b37e27e443422162fca2a20cec2f97102a6dc88440f9bedab268'){throw 'Final ZIP SHA mismatch'}
$zip=$desktop+'\Spitfire_XP_USB_OneShot.zip';$folder=$desktop+'\Spitfire_XP_USB_OneShot'
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
if(Test-Path -LiteralPath $zip){Move-Item -LiteralPath $zip -Destination ($zip+'.previous-'+$stamp)}
if(Test-Path -LiteralPath $folder){Move-Item -LiteralPath $folder -Destination ($folder+'.previous-'+$stamp)}
[IO.File]::WriteAllBytes($zip,$data)
Expand-Archive -LiteralPath $zip -DestinationPath $desktop
@{utc=[DateTime]::UtcNow.ToString('o');zip=$zip;folder=$folder;bytes=$data.Length;sha256=(Get-FileHash -LiteralPath $zip).Hash.ToLower();start_exists=(Test-Path -LiteralPath ($folder+'\START.cmd'))} | ConvertTo-Json | Set-Content -LiteralPath ($r+'\delivery.json') -Encoding UTF8
Get-Content -LiteralPath ($r+'\delivery.json')
