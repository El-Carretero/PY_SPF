param(
    [ValidateSet('capture','click','keys')][string]$Action='capture',
    [int]$X=0, [int]$Y=0, [string]$Keys='',
    [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Name='state'
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class VmConsoleUi {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int s);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint data,UIntPtr extra);
}
'@
[VmConsoleUi]::SetProcessDPIAware() | Out-Null
$processes=@(Get-Process vmware | Where-Object {$_.MainWindowTitle -eq 'Windows XP Professional - VMware Workstation'})
if($processes.Count -ne 1){throw 'Expected exactly one observed XP VMware window'}
$h=$processes[0].MainWindowHandle
$foregroundPid=0
[VmConsoleUi]::GetWindowThreadProcessId([VmConsoleUi]::GetForegroundWindow(),[ref]$foregroundPid) | Out-Null
if([VmConsoleUi]::IsIconic($h)){[VmConsoleUi]::ShowWindow($h,9) | Out-Null}
if($foregroundPid -ne $processes[0].Id){[VmConsoleUi]::SetForegroundWindow($h) | Out-Null}
Start-Sleep -Milliseconds 250
$foregroundPid=0
[VmConsoleUi]::GetWindowThreadProcessId([VmConsoleUi]::GetForegroundWindow(),[ref]$foregroundPid) | Out-Null
if($foregroundPid -ne $processes[0].Id){throw 'VMware window is not foreground; no input sent'}
$rect=New-Object VmConsoleUi+RECT
if(![VmConsoleUi]::GetWindowRect($h,[ref]$rect)){throw 'Window geometry unavailable'}
if($Action -eq 'click'){
 if($X -lt 0 -or $Y -lt 0 -or $X -ge ($rect.Right-$rect.Left) -or $Y -ge ($rect.Bottom-$rect.Top)){throw 'Click outside VMware window'}
 if(![VmConsoleUi]::SetCursorPos(($rect.Left+$X),($rect.Top+$Y))){throw 'Mouse positioning rejected; no click sent'}
 [VmConsoleUi]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
 [VmConsoleUi]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
}
if($Action -eq 'keys'){[Windows.Forms.SendKeys]::SendWait($Keys)}
Start-Sleep -Milliseconds 700
$out=Join-Path $PSScriptRoot ('internal\'+$Name+'.png')
$bitmap=New-Object Drawing.Bitmap ($rect.Right-$rect.Left),($rect.Bottom-$rect.Top)
$graphics=[Drawing.Graphics]::FromImage($bitmap)
try {
 $dc=$graphics.GetHdc()
 try {
  if(![VmConsoleUi]::PrintWindow($h,$dc,2)){throw 'VMware PrintWindow capture failed'}
 } finally {$graphics.ReleaseHdc($dc)}
 $bitmap.Save($out,[Drawing.Imaging.ImageFormat]::Png)
} finally {$graphics.Dispose();$bitmap.Dispose()}
[pscustomobject]@{Action=$Action;Screenshot=$out;Rect=$rect;Window=$processes[0].MainWindowTitle} | ConvertTo-Json -Depth 3
