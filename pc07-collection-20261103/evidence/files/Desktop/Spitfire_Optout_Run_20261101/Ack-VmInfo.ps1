Add-Type @'
using System;using System.Text;using System.Runtime.InteropServices;
public class VmInfoAck {
public delegate bool E(IntPtr h,IntPtr x);
[DllImport("user32.dll")]public static extern bool EnumWindows(E e,IntPtr x);
[DllImport("user32.dll")]public static extern bool EnumChildWindows(IntPtr h,E e,IntPtr x);
[DllImport("user32.dll",CharSet=CharSet.Unicode)]public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
[DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
[DllImport("user32.dll")]public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
static string T(IntPtr h){var b=new StringBuilder(3000);GetWindowText(h,b,b.Capacity);return b.ToString();}
public static void Run(uint pid){EnumWindows((h,x)=>{uint p;GetWindowThreadProcessId(h,out p);if(p!=pid)return true;bool info=T(h)=="Removable Devices";IntPtr ok=IntPtr.Zero;EnumChildWindows(h,(c,y)=>{var t=T(c);if(t.Contains("side channel mitigations"))info=true;if(t=="OK")ok=c;return true;},IntPtr.Zero);if(info&&ok!=IntPtr.Zero){SendMessage(ok,0xf5,IntPtr.Zero,IntPtr.Zero);Console.WriteLine("Acknowledged VMware information dialog");}return true;},IntPtr.Zero);}
}
'@
[VmInfoAck]::Run((Get-Process vmware).Id)
