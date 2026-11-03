$ErrorActionPreference='Stop'
$r=$PSScriptRoot
Add-Type -AssemblyName System.Drawing
$out=Join-Path $r 'screenshots'
New-Item -ItemType Directory -Force -Path $out|Out-Null
$rows=@()
foreach($f in Get-ChildItem (Join-Path $r 'received') -Filter '*-desktop*.bmp'){
 $stem=$f.BaseName -replace '-desktop','-windows'
 $wf=Join-Path $f.DirectoryName ($stem+'.jsonl')
 $wins=@()
 if(Test-Path $wf){
  foreach($line in [IO.File]::ReadAllLines($wf,[Text.Encoding]::UTF8)){
   try{$w=$line|ConvertFrom-Json;if($w.visible -and $w.class -eq 'CVIRTLVDChild4194304' -and $w.rect[0] -ge 0 -and $w.rect[1] -ge 0 -and $w.rect[2] -le 1280 -and $w.rect[3] -le 800){$wins += $w}}catch{}
  }
 }
 $b=New-Object Drawing.Bitmap $f.FullName
 if($wins.Count){
  $left=($wins|ForEach-Object {$_.rect[0]}|Measure-Object -Minimum).Minimum
  $top=($wins|ForEach-Object {$_.rect[1]}|Measure-Object -Minimum).Minimum
  $right=($wins|ForEach-Object {$_.rect[2]}|Measure-Object -Maximum).Maximum
  $bottom=($wins|ForEach-Object {$_.rect[3]}|Measure-Object -Maximum).Maximum
  $rect=[Drawing.Rectangle]::new($left,$top,($right-$left),($bottom-$top))
 }else{$rect=[Drawing.Rectangle]::new(0,0,$b.Width,$b.Height)}
 $crop=$b.Clone($rect,$b.PixelFormat)
 $temp=Join-Path $out 'temporary.png'
 $crop.Save($temp,[Drawing.Imaging.ImageFormat]::Png)
 $crop.Dispose();$b.Dispose()
 $hash=(Get-FileHash $temp).Hash.ToLower()
 $target=Join-Path $out ($hash+'.png')
 if(Test-Path $target){Remove-Item $temp}else{Move-Item $temp $target}
 $rows += [pscustomobject]@{raw_bmp=$f.Name;raw_bmp_sha256=(Get-FileHash $f.FullName).Hash.ToLower();png=('screenshots/'+$hash+'.png');crop_x=$rect.X;crop_y=$rect.Y;crop_width=$rect.Width;crop_height=$rect.Height;pixels_rescaled=$false;raw_bmp_preserved_on_p07=$f.FullName}
}
$rows|Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $r 'screenshot-index.csv')
[pscustomobject]@{source_screenshots=$rows.Count;unique_pngs=@(Get-ChildItem $out -Filter '*.png').Count;png_bytes=(Get-ChildItem $out -Filter '*.png'|Measure-Object Length -Sum).Sum}|ConvertTo-Json

