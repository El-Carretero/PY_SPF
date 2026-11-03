param(
 [ValidateSet('capture','click','keys')][string]$Action='capture',
 [int]$X=0,[int]$Y=0,[string]$Keys='',
 [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Name='live'
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class VmLiveUi {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint data,UIntPtr extra);
}
'@
[VmLiveUi]::SetProcessDPIAware() | Out-Null
$vms=@(Get-Process vmware | Where-Object {$_.MainWindowTitle -eq 'Windows XP Professional - VMware Workstation'})
if($vms.Count -ne 1){throw 'Expected exactly one observed XP VMware window'}
$handle=$vms[0].MainWindowHandle
[VmLiveUi]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Milliseconds 300
$front=0
[VmLiveUi]::GetWindowThreadProcessId([VmLiveUi]::GetForegroundWindow(),[ref]$front) | Out-Null
if($front -ne $vms[0].Id){throw 'VMware is not foreground; input refused'}
$rect=New-Object VmLiveUi+RECT
if(-not [VmLiveUi]::GetWindowRect($handle,[ref]$rect)){throw 'No window geometry'}
$bounds=[Windows.Forms.Screen]::PrimaryScreen.Bounds
$left=[Math]::Max($rect.Left,$bounds.Left)
$top=[Math]::Max($rect.Top,$bounds.Top)
$width=[Math]::Min($rect.Right,$bounds.Right)-$left
$height=[Math]::Min($rect.Bottom,$bounds.Bottom)-$top
if($Action -eq 'click'){
 if($X -lt 0 -or $Y -lt 0 -or $X -ge $width -or $Y -ge $height){throw 'Click out of visible VM window'}
 if(-not [VmLiveUi]::SetCursorPos($left+$X,$top+$Y)){throw 'Cursor placement failed'}
 Start-Sleep -Milliseconds 600
 [VmLiveUi]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
 Start-Sleep -Milliseconds 100
 [VmLiveUi]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
}
if($Action -eq 'keys'){[Windows.Forms.SendKeys]::SendWait($Keys)}
Start-Sleep -Milliseconds $(if($Action -eq 'capture'){500}else{5000})
$out=Join-Path $PSScriptRoot ('internal\'+$Name+'.png')
$bitmap=New-Object Drawing.Bitmap($width,$height)
$graphics=[Drawing.Graphics]::FromImage($bitmap)
try{
 $graphics.CopyFromScreen($left,$top,0,0,(New-Object Drawing.Size($width,$height)))
 $bitmap.Save($out,[Drawing.Imaging.ImageFormat]::Png)
}finally{$graphics.Dispose();$bitmap.Dispose()}
[pscustomobject]@{Action=$Action;Screenshot=$out;ScreenLeft=$left;ScreenTop=$top;Width=$width;Height=$height;ObservedUtc=[DateTime]::UtcNow.ToString('o');Method='CopyFromScreen-live-not-PrintWindow'} | ConvertTo-Json
