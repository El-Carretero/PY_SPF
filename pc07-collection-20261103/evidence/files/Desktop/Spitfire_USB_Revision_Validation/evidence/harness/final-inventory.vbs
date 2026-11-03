Option Explicit
Dim f,s,w,l,p,n,a,x,h
Set f=CreateObject("Scripting.FileSystemObject")
Set s=CreateObject("WScript.Shell")
Set w=GetObject("winmgmts:\\.\root\cimv2")
Set l=f.CreateTextFile("C:\SPF_USB_REVISION\final-inventory.txt",True)
n=0
For Each p In w.ExecQuery("Select * From Win32_Process Where Name='Spitfire.exe'")
n=n+1
Next
l.WriteLine "original_process_count=" & n
For Each p In w.ExecQuery("Select * From Win32_NetworkAdapterConfiguration Where IPEnabled=True")
l.WriteLine "nic=" & p.Description
l.WriteLine "mac=" & p.MACAddress
If Not IsNull(p.IPAddress) Then
For Each x In p.IPAddress
l.WriteLine "ip=" & x
Next
End If
If Not IsNull(p.DefaultIPGateway) Then
For Each x In p.DefaultIPGateway
l.WriteLine "gateway=" & x
Next
End If
Next
a=s.RegRead("HKCU\Control Panel\Desktop\WindowMetrics\MenuFont")
h=""
For Each x In a
h=h & Right("0" & Hex(x),2)
Next
l.WriteLine "MenuFont_REG_BINARY_hex=" & h
l.Close
s.Run "cmd.exe /c ipconfig /all > C:\SPF_USB_REVISION\final-ipconfig.txt",0,True
s.Run "cmd.exe /c route print > C:\SPF_USB_REVISION\final-route.txt",0,True
WScript.Quit 0
