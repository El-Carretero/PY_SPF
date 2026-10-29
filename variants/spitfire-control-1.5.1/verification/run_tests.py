"""Reproducible offline regression runner. Rejects non-loopback socket sends."""
from pathlib import Path
import argparse
import contextlib
import ipaddress
import json
import os
import platform
import socket
import sys
import tempfile
import time
import unittest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--suite',choices=('control','verifier'),default='control')
    parser.add_argument('--pattern',default='test*.py')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    source=root if args.suite=='control' else root/'verification'/'verifier'
    sys.path[:0]=[str(source/'src'),str(source/'tests')]
    real_socket=socket.socket
    class LoopbackOnlySocket(real_socket):
        def _check(self,address):
            if self.family in (socket.AF_INET,socket.AF_INET6):
                if not ipaddress.ip_address(socket.gethostbyname(address[0])).is_loopback:
                    raise PermissionError('Offline validation forbids non-loopback destinations')
        def sendto(self,data,*args):
            self._check(args[-1]);return super().sendto(data,*args)
        def connect(self,address):
            self._check(address);return super().connect(address)
        def connect_ex(self,address):
            self._check(address);return super().connect_ex(address)
    socket.socket=LoopbackOnlySocket
    os.environ['SPITFIRE_EVIDENCE_DIR']=str(out/'captures')
    with tempfile.TemporaryDirectory(prefix='spitfire-test-config-') as config_dir:
        os.environ['APPDATA']=config_dir
        os.environ['XDG_CONFIG_HOME']=config_dir
        suite=unittest.defaultTestLoader.discover(str(source/'tests'),pattern=args.pattern)
        started=time.monotonic()
        with (out/'tests.txt').open('w',encoding='utf-8') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        report={'suite':args.suite,'python':sys.version,'platform':platform.platform(),
                'tests':result.testsRun,'failures':[(t.id(),msg) for t,msg in result.failures],
                'errors':[(t.id(),msg) for t,msg in result.errors],
                'skipped':[(t.id(),reason) for t,reason in result.skipped],
                'duration_seconds':round(time.monotonic()-started,3),
                'success':result.wasSuccessful(),'network_scope':'loopback sends only',
                'physical_validation':False,'xp_gui_executed_by_this_runner':False}
        (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('failures','errors','skipped')},ensure_ascii=False))
        print('failures',len(result.failures),'errors',len(result.errors),'skips',len(result.skipped))
        return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
