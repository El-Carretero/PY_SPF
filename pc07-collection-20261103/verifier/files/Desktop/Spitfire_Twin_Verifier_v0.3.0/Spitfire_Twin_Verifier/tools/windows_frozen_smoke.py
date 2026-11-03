"""Test only this release's frozen executables with isolated user settings."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--client', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    gui, cli = root/'dist/SpitfireTwinVerifier.exe', root/'dist/SpitfireTwinVerifierCLI.exe'
    report = {'scope':'Frozen EXE launch and loopback software tests; no vendor/physical hardware',
              'status':'ERROR','xp_execution':'NOT_PERFORMED','hardware_validation':'NOT_PERFORMED',
              'executables':{}, 'cli':[]}
    for binary in (gui, cli):
        report['executables'][binary.name] = {'size':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='spitfire-frozen-settings-') as settings:
        env = dict(os.environ, LOCALAPPDATA=settings)
        for name, flags in [('selftest',['--self-test']),('scenarios',['--scenario-suite']),
                            ('matrix',['--matrix',str(Path(args.client).resolve()),'--trust-client-code'])]:
            run = subprocess.run([str(cli),*flags,'--output',str(out/name)],cwd=root,env=env,
                                 capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            (out/(name+'.txt')).write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
            report['cli'].append({'name':name,'returncode':run.returncode})
        windows = []
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        def callback(hwnd,_):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(length+1)
                user32.GetWindowTextW(hwnd,title,length+1)
                if title.value.startswith('Spitfire Twin Verifier'):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                    windows.append((int(hwnd),pid.value,title.value))
            return True
        # A PyInstaller onefile bootloader starts one child. Only close windows
        # whose process image is exactly our executable, never a user instance.
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        user32.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user32.EnumWindows(callback_type(callback),0)
        existing_windows={hwnd for hwnd,_,_ in windows}
        process = subprocess.Popen([str(gui)],cwd=root,env=env)
        owned = []
        try:
            deadline = time.monotonic()+15
            while time.monotonic()<deadline and not owned:
                windows.clear()
                user32.EnumWindows(callback_type(callback),0)
                for hwnd,pid,title in windows:
                    if hwnd in existing_windows:
                        continue
                    handle=kernel32.OpenProcess(0x1000,False,pid)
                    if handle:
                        buf=ctypes.create_unicode_buffer(32768); size=wintypes.DWORD(len(buf))
                        ok=kernel32.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size))
                        kernel32.CloseHandle(handle)
                        if ok and Path(buf.value).resolve()==gui.resolve():
                            owned.append((hwnd,pid,title))
                if process.poll() is not None and not owned:
                    break
                time.sleep(.1)
            report['gui_window_found']=bool(owned)
            report['gui_title']=owned[0][2] if owned else None
            for hwnd,_,_ in owned:
                user32.PostMessageW(hwnd,0x0010,0,0)
            process.wait(timeout=10)
            report['gui_exitcode']=process.returncode
        except Exception as exc:
            report['gui_error']=type(exc).__name__+': '+str(exc)
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)
        report['status']='PASS' if all(x['returncode']==0 for x in report['cli']) and report.get('gui_window_found') and report.get('gui_exitcode')==0 else 'FAIL'
    (out/'frozen_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
