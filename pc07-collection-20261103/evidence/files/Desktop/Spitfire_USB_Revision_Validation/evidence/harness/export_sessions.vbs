Option Explicit
Dim f,root,folder,ddf,manifest,out,n,sh,rc
Set f=CreateObject("Scripting.FileSystemObject")
Set sh=CreateObject("WScript.Shell")
root="C:\SpitfireLogs"
out="C:\SPF_USB_REVISION\export"
If Not f.FolderExists(out) Then f.CreateFolder out
Set ddf=f.CreateTextFile(out & "\export.ddf",True)
Set manifest=f.CreateTextFile(out & "\manifest.tsv",True)
ddf.WriteLine ".OPTION EXPLICIT"
ddf.WriteLine ".Set CabinetNameTemplate=evidence.cab"
ddf.WriteLine ".Set DiskDirectoryTemplate=" & out
ddf.WriteLine ".Set Cabinet=on"
ddf.WriteLine ".Set Compress=on"
ddf.WriteLine ".Set CompressionType=MSZIP"
ddf.WriteLine ".Set MaxDiskSize=0"
ddf.WriteLine ".Set MaxCabinetSize=0"
n=0
For Each folder In f.GetFolder(root).SubFolders
 If InStr(1,"," & WScript.Arguments(0) & ",","," & folder.Name & ",",vbBinaryCompare)>0 Then Call AddFolder(folder,folder.Name & "--")
Next
ddf.Close
manifest.Close
rc=sh.Run("cmd.exe /c makecab.exe /F """ & out & "\export.ddf"" > """ & out & "\makecab.log"" 2>&1",0,True)
Set manifest=f.CreateTextFile(out & "\export-result.txt",True)
manifest.WriteLine "files=" & n
manifest.WriteLine "makecab_exit=" & rc
manifest.Close
WScript.Quit rc
Sub AddFolder(folder,prefix)
 Dim z,s,dest
 For Each z In folder.Files
  dest=prefix & z.Name
  ddf.WriteLine """" & z.Path & """ """ & dest & """"
  manifest.WriteLine dest & vbTab & z.Size & vbTab & z.Path
  n=n+1
 Next
 For Each s In folder.SubFolders
  If s.Name<>"app" And s.Name<>"official-installer" Then Call AddFolder(s,prefix & s.Name & "--")
 Next
End Sub
