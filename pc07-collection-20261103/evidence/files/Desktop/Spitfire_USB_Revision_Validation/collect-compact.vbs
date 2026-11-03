Option Explicit
Dim fs,root,src,dst,f,name,sh
Set fs=CreateObject("Scripting.FileSystemObject")
Set f=fs.OpenTextFile("C:\SPF_USB_REVISION\current-session.txt",1)
name=Trim(Replace(Replace(f.ReadAll,vbCr,""),vbLf,"")):f.Close
If name="" Or InStr(name,"\")>0 Then WScript.Quit 2
root="C:\SpitfireLogs\" & name
dst="C:\SPF_USB_REVISION\compact"
If fs.FolderExists(dst) Then fs.DeleteFolder dst,True
fs.CreateFolder dst
CopyTree fs.GetFolder(root),dst
For Each name In Array("readonly_ui.exe","passive_capture.exe","proof_publish.exe","provision_winpcap.exe")
 If Not fs.FolderExists(dst & "\runtime") Then fs.CreateFolder dst & "\runtime"
 fs.CopyFile root & "\app\bin\" & name,dst & "\runtime\" & name,True
Next
For Each name In Array("runner.js","report.js","RUN.hta")
 fs.CopyFile root & "\app\" & name,dst & "\runtime\" & name,True
Next
fs.CopyFile "C:\SPF_USB_PACKAGE_V1_1\START.cmd",dst & "\runtime\START.cmd",True
fs.CopyFile "C:\SPF_USB_PACKAGE_V1_1\START.hta",dst & "\runtime\START.hta",True
fs.CopyFile "C:\SPF_USB_REVISION\current-session.txt",dst & "\session-name.txt",True
fs.CopyFile "C:\SPF_USB_REVISION\start-log.txt",dst & "\start-log.txt",True
WScript.Quit 0
Sub CopyTree(folder,destination)
 Dim z,s,ext
 For Each z In folder.Files
  ext=LCase(fs.GetExtensionName(z.Name))
  If ext<>"bmp" And ext<>"exe" Then
   On Error Resume Next
   fs.CopyFile z.Path,destination & "\" & z.Name,True
   On Error GoTo 0
  End If
 Next
 For Each s In folder.SubFolders
  If LCase(s.Name)<>"app" Then
   fs.CreateFolder destination & "\" & s.Name
   CopyTree s,destination & "\" & s.Name
  End If
 Next
End Sub
