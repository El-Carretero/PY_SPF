from pathlib import Path
import zipfile,base64,json,hashlib
r=Path(r"C:\Users\Fluke\Desktop\Spitfire_USB_Validation")
data=base64.b64decode((r/'final-runtime-transfer.b64').read_text(),validate=True)
assert hashlib.sha256(data).hexdigest()=='f5468652ae68817064d6ade765cb056214b29ff4b0daf125a7a5af95127a0641'
(r/'final-runtime-transfer.zip').write_bytes(data)
g=r'C:\SPF_USB_VALIDATION';p=r'C:\SPF_USB_PACKAGE'
ops=[]
with zipfile.ZipFile(r/'final-runtime-transfer.zip') as z:
 for i,n in enumerate(z.namelist()):
  name='final-runtime-file-'+str(i)
  (r/name).write_bytes(z.read(n))
  ops.append({'op':'download','name':name,'path':p+'\\'+n.replace('/','\\')})
v='''Option Explicit\r\nDim s,p,n,f,log,sh,rc\r\nSet s=GetObject("winmgmts:\\\\.\\root\\cimv2")\r\nSet f=CreateObject("Scripting.FileSystemObject")\r\nSet sh=CreateObject("WScript.Shell")\r\nSet log=f.CreateTextFile("C:\\SPF_USB_VALIDATION\\final-launch.txt",True)\r\nn=0\r\nFor Each p In s.ExecQuery("SELECT * FROM Win32_Process WHERE Name='Spitfire.exe'")\r\nn=n+1\r\nNext\r\nIf n<>0 Then log.WriteLine "Blocked existing original": log.Close: WScript.Quit 10\r\nlog.WriteLine "Isolated simulator only; launch original before USB capture; startup2047 rejected by fixture."\r\nrc=sh.Run("C:\\SPF_USB_VALIDATION\\launch-original.cmd",0,True)\r\nlog.WriteLine "Original launch command exit=" & rc\r\nWScript.Sleep 15000\r\nn=0\r\nFor Each p In s.ExecQuery("SELECT * FROM Win32_Process WHERE Name='Spitfire.exe'")\r\nn=n+1\r\nlog.WriteLine "Original pid=" & p.ProcessId & " path=" & p.ExecutablePath\r\nIf LCase(p.ExecutablePath)<>"c:\\program files\\spectra-physics\\spitfire\\spitfire.exe" Then log.Close: WScript.Quit 11\r\nNext\r\nIf n<>1 Then log.WriteLine "Blocked original count": log.Close: WScript.Quit 12\r\nrc=sh.Run("C:\\SPF_USB_PACKAGE\\START.cmd",1,True)\r\nlog.WriteLine "Actual USB START.cmd exit=" & rc\r\nlog.Close\r\nWScript.Quit rc\r\n'''
ops += [{'op':'write','path':g+'\\final-launch.vbs','text':v},{'op':'run','command':'cscript //nologo "'+g+'\\final-launch.vbs"','wait':True},{'op':'upload','path':g+'\\final-launch.txt','name':'final-launch.txt'}]
(r/'control-final.json').write_text(json.dumps({'id':'041-final-full-start','ops':ops}),encoding='utf-8')
print(json.dumps({'runtime_files':len(ops)-3,'queue':'041-final-full-start'}))
