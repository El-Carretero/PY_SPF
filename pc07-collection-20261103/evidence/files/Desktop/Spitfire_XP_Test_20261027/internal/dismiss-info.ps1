Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices;
public class DialogProbe {
 public delegate bool E(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(E e,IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p,E e,IntPtr l);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
 public static string T(IntPtr h){var b=new StringBuilder(2048);GetWindowText(h,b,b.Capacity);return b.ToString();}
 public static void Run(uint pid){EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p==pid){Console.WriteLine(h+" "+T(h));EnumChildWindows(h,(c,z)=>{string t=T(c);if(t.Length>0)Console.WriteLine(" CHILD "+c+" "+t); if(T(h)=="Removable Devices" && t=="OK"){SendMessage(c,0xf5,IntPtr.Zero,IntPtr.Zero);Console.WriteLine("ACKNOWLEDGED INFORMATION DIALOG");}return true;},IntPtr.Zero);}return true;},IntPtr.Zero);}
}
'@
[DialogProbe]::Run(8484)
