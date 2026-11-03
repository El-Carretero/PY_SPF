from pathlib import Path
import base64,zipfile,io,hashlib
r=Path(r"C:\Users\Fluke\Desktop\Spitfire_USB_Validation");b=base64.b64decode((r/'final-fix-transfer.b64').read_text(),validate=True)
assert hashlib.sha256(b).hexdigest()=='d815f58d214857da557b08d1c2dde73557ceeb43b7ff42aa4c43886c9417f3e2'
with zipfile.ZipFile(io.BytesIO(b)) as z:
 for n,t in [('bin/readonly_ui.exe','readonly_ui-final.exe'),('runner.js','runner-final.js')]:
  p=r/t;p.write_bytes(z.read(n));print(t,hashlib.sha256(p.read_bytes()).hexdigest())
