param([string]$Action='capture',[int]$X=0,[int]$Y=0,[string]$Keys='',[string]$Name='logaudit_state')
$ErrorActionPreference='Stop'
Add-Type @'
using System; using System.Runtime.InteropServices;
public class AuditActivate {
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a,uint b,bool attach);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int s);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
}
'@
$target=@(Get-Process vmware|Where-Object {$_.MainWindowTitle -eq 'Windows XP Professional - VMware Workstation'})
if($target.Count -ne 1){throw 'Expected single XP VMware window'}
$target=$target[0];$frontpid=0
$thread=[AuditActivate]::GetWindowThreadProcessId([AuditActivate]::GetForegroundWindow(),[ref]$frontpid)
$mine=[AuditActivate]::GetCurrentThreadId()
$attached=[AuditActivate]::AttachThreadInput($mine,$thread,$true)
try {[AuditActivate]::ShowWindow($target.MainWindowHandle,3)|Out-Null;[AuditActivate]::BringWindowToTop($target.MainWindowHandle)|Out-Null;[AuditActivate]::SetForegroundWindow($target.MainWindowHandle)|Out-Null}
finally {if($attached){[AuditActivate]::AttachThreadInput($mine,$thread,$false)|Out-Null}}
& (Join-Path $PSScriptRoot 'VM-LiveConsole.ps1') -Action $Action -X $X -Y $Y -Keys ('^g'+$Keys) -Name $Name
