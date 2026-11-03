Option Explicit
Dim wmi,fs,sh,log,p,n,rc,oldcwd,base,z,known,newname
Set wmi=GetObject("winmgmts:\\.\root\cimv2")
Set fs=CreateObject("Scripting.FileSystemObject")
Set sh=CreateObject("WScript.Shell")
Set log=fs.CreateTextFile("C:\SPF_USB_REVISION\start-log.txt",True)
n=0
For Each p In wmi.ExecQuery("Select * From Win32_Process Where Name='Spitfire.exe'")
 n=n+1
Next
If n<>0 Then log.WriteLine "Blocked: original already running":log.Close:WScript.Quit 10
Set known=CreateObject("Scripting.Dictionary")
base="C:\SpitfireLogs"
If fs.FolderExists(base) Then
 For Each z In fs.GetFolder(base).SubFolders
  known.Add z.Name,True
 Next
End If
oldcwd=sh.CurrentDirectory
sh.CurrentDirectory="C:\Program Files\Spectra-Physics\Spitfire"
rc=sh.Run(Chr(34) & "C:\Program Files\Spectra-Physics\Spitfire\Spitfire.exe" & Chr(34),1,False)
sh.CurrentDirectory=oldcwd
log.WriteLine "Isolated original launch requested; startup writes rejected by fixed-response fixture."
WScript.Sleep 15000
n=0
For Each p In wmi.ExecQuery("Select * From Win32_Process Where Name='Spitfire.exe'")
 n=n+1
 log.WriteLine "Original pid=" & p.ProcessId & " path=" & p.ExecutablePath
 If LCase(p.ExecutablePath)<>"c:\program files\spectra-physics\spitfire\spitfire.exe" Then log.Close:WScript.Quit 11
Next
If n<>1 Then log.WriteLine "Blocked: original process count is not one":log.Close:WScript.Quit 12
rc=sh.Run("C:\SPF_USB_PACKAGE_V1_1\START.cmd",1,True)
log.WriteLine "Actual START.cmd exit=" & rc
WScript.Sleep 12000
newname=""
For Each z In fs.GetFolder(base).SubFolders
 If Not known.Exists(z.Name) Then
  If newname<>"" Then log.WriteLine "More than one new run":log.Close:WScript.Quit 13
  newname=z.Name
 End If
Next
log.WriteLine "New session=" & newname
log.Close
Set log=fs.CreateTextFile("C:\SPF_USB_REVISION\current-session.txt",True)
log.Write newname
log.Close
WScript.Quit rc
