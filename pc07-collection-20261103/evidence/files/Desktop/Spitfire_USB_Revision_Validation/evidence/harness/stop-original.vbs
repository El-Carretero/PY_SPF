Option Explicit
Dim fs,w,log,p,n,rc
Set fs=CreateObject("Scripting.FileSystemObject")
Set w=GetObject("winmgmts:\\.\root\cimv2")
Set log=fs.CreateTextFile("C:\SPF_USB_REVISION\stop-original.txt",True)
For Each p In w.ExecQuery("Select * From Win32_Process Where Name='passive_capture.exe' Or Name='readonly_ui.exe' Or Name='readonly_menu_probe.exe'")
 log.WriteLine "Blocked: helper active " & p.Name & " " & p.ProcessId
 log.Close
 WScript.Quit 20
Next
For Each p In w.ExecQuery("Select * From Win32_Process Where Name='Spitfire.exe'")
 If LCase(p.ExecutablePath)<>"c:\program files\spectra-physics\spitfire\spitfire.exe" Then
  log.WriteLine "Blocked: unexpected original path":log.Close:WScript.Quit 21
 End If
 rc=p.Terminate()
 log.WriteLine "Fixture-only terminated original PID=" & p.ProcessId & " rc=" & rc
Next
WScript.Sleep 1500
n=0
For Each p In w.ExecQuery("Select * From Win32_Process Where Name='Spitfire.exe'")
 n=n+1
Next
log.WriteLine "remaining_originals=" & n
log.Close
If n<>0 Then WScript.Quit 22
WScript.Quit 0
