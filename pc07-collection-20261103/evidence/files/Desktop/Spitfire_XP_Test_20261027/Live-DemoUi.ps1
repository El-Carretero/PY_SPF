param(
 [ValidateSet('Spitfire Twin Verifier 0.3.1','Windows XP Professional - VMware Workstation')][string]$Title='Spitfire Twin Verifier 0.3.1',
 [string]$Actions='[]',
 [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Name='demo'
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class DemoUi {
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint data,UIntPtr extra);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int s);
 [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int ht,bool repaint);
}
'@
[DemoUi]::SetProcessDPIAware()|Out-Null
$p=@(Get-Process|Where-Object {$_.MainWindowTitle -eq $Title})
if($p.Count -ne 1){throw "Expected exactly one target window: $Title"}
[DemoUi]::SetForegroundWindow($p[0].MainWindowHandle)|Out-Null
Start-Sleep -Milliseconds 400
$b=[Windows.Forms.Screen]::PrimaryScreen.Bounds
foreach($a in ($Actions|ConvertFrom-Json)){
 $front=0; [DemoUi]::GetWindowThreadProcessId([DemoUi]::GetForegroundWindow(),[ref]$front)|Out-Null
 if($front -ne $p[0].Id){throw 'Unexpected foreground process; input refused'}
 switch($a.action){
  'click' {if($a.x -lt 0 -or $a.y -lt 0 -or $a.x -ge $b.Width -or $a.y -ge $b.Height){throw 'Outside screen'};[DemoUi]::SetCursorPos($a.x,$a.y)|Out-Null;Start-Sleep -Milliseconds 300;[DemoUi]::mouse_event(2,0,0,0,[UIntPtr]::Zero);Start-Sleep -Milliseconds 100;[DemoUi]::mouse_event(4,0,0,0,[UIntPtr]::Zero)}
  'keys' {[Windows.Forms.SendKeys]::SendWait([string]$a.keys)}
  'drag' {if($a.x -lt 0 -or $a.y -lt 0 -or $a.tx -lt 0 -or $a.ty -lt 0 -or $a.x -ge $b.Width -or $a.tx -ge $b.Width -or $a.y -ge $b.Height -or $a.ty -ge $b.Height){throw 'Drag outside screen'};[DemoUi]::SetCursorPos($a.x,$a.y)|Out-Null;Start-Sleep -Milliseconds 400;[DemoUi]::mouse_event(2,0,0,0,[UIntPtr]::Zero);Start-Sleep -Milliseconds 200;for($i=1;$i -le 20;$i++){[DemoUi]::SetCursorPos([int]($a.x+($a.tx-$a.x)*$i/20),[int]($a.y+($a.ty-$a.y)*$i/20))|Out-Null;Start-Sleep -Milliseconds 30};[DemoUi]::mouse_event(4,0,0,0,[UIntPtr]::Zero)}
  'layout' {[DemoUi]::ShowWindow($p[0].MainWindowHandle,9)|Out-Null;[DemoUi]::MoveWindow($p[0].MainWindowHandle,$a.x,$a.y,$a.w,$a.h,$true)|Out-Null}
  default {throw 'Unknown action'}
 }
 $wait=700;if($a.wait_ms){$wait=[Math]::Min(5000,[Math]::Max(200,[int]$a.wait_ms))};Start-Sleep -Milliseconds $wait
}
Start-Sleep -Milliseconds 500
$out=Join-Path $PSScriptRoot ('internal\'+$Name+'.png')
$bitmap=New-Object Drawing.Bitmap($b.Width,$b.Height)
$graphics=[Drawing.Graphics]::FromImage($bitmap)
try{$graphics.CopyFromScreen($b.Left,$b.Top,0,0,$b.Size);$bitmap.Save($out,[Drawing.Imaging.ImageFormat]::Png)}finally{$graphics.Dispose();$bitmap.Dispose()}
[pscustomobject]@{Screenshot=$out;Utc=[DateTime]::UtcNow.ToString('o');Title=$Title;Method='CopyFromScreen'}|ConvertTo-Json
