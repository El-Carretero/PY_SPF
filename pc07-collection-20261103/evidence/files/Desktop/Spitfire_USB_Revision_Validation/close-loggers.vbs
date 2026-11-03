Option Explicit
Dim w,f,l,p,q,n,k,cmd,paths,counts,rc
Set w=GetObject("winmgmts:\\.\root\cimv2")
Set f=CreateObject("Scripting.FileSystemObject")
Set l=f.CreateTextFile("C:\SPF_USB_REVISION\guest-final-processes.txt",True)
paths=Array("c:\spitfirelogs\run-2026-10-31-19-49-45-14743\app\run.hta","c:\spitfirelogs\run-2026-10-31-20-0-27-62380\app\run.hta","c:\spitfirelogs\run-2026-10-31-20-6-20-13944\app\run.hta","c:\spitfirelogs\run-2026-10-31-20-12-53-12423\app\run.hta","c:\spitfirelogs\run-2026-10-31-20-18-5-68232\app\run.hta")
For Each p In w.ExecQuery("Select * From Win32_Process Where Name='mshta.exe'")
 cmd=LCase(p.CommandLine)
 For Each q In paths
  If InStr(1,cmd,q,vbBinaryCompare)>0 Then
   rc=p.Terminate()
   l.WriteLine "terminated_completed_test_logger=" & p.ProcessId & " rc=" & rc
  End If
 Next
Next
WScript.Sleep 1000
Set counts=CreateObject("Scripting.Dictionary")
For Each k In Array("spitfire.exe","passive_capture.exe","readonly_ui.exe","proof_publish.exe","provision_winpcap.exe","readonly_menu_probe.exe","readonly_font_probe.exe","readonly_font_probe2.exe")
 counts.Add k,0
Next
For Each p In w.ExecQuery("Select * From Win32_Process")
 k=LCase(p.Name)
 If counts.Exists(k) Then counts(k)=counts(k)+1
 If k="mshta.exe" Then l.WriteLine "remaining_mshta=" & p.ProcessId & " " & p.CommandLine
Next
n=0
For Each k In counts.Keys
 l.WriteLine k & "=" & counts(k)
 n=n+counts(k)
Next
l.Close
If n<>0 Then WScript.Quit 20
WScript.Quit 0
