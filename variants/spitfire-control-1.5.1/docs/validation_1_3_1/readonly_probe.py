"""One-client, query-only TDG diagnostics. Never imports the application controller."""
from __future__ import annotations
import argparse,json,sys,time,socket,statistics
from pathlib import Path
from datetime import datetime,timezone
SOURCE=Path(r"C:\Users\physi\Downloads\Spitfire_Python_Control_1.3.0\Spitfire_Python_Control\src")
sys.path.insert(0,str(SOURCE))
from spitfire_control.commands import COMMANDS,format_command
from spitfire_control.protocol import decode_command_datagram
from spitfire_control.transport import UdpTransport,UdpSettings,TransportError
from spitfire_control.state import DeviceState
ROOT=Path(__file__).resolve().parent
CORE=(1000,1021,1019,1039,1066,1050,1051,1065,1045,1046,1068,1087,1028,1088,1089)
CAPABILITY=(1000,1021,1015,1017,1018,1019,1020,1022,1023,1024,1025,1027,1028,1029,1030,1031,1032,1033,1034,1036,1037,1039,1040,1041,1042,1043,1044,1045,1046,1047,1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,1058,1059,1060,1061,1063,1064,1065,1066,1067,1068,1069,1079,1080,1083,1084,1085,1086,1087,1088,1089)
ALLOWED=frozenset(CAPABILITY)
for cid in ALLOWED:
    spec=COMMANDS[cid]
    if not (1000 <= cid < 2000 and not spec.writable and spec.text.endswith('?')): raise PermissionError('Non-query allowlist entry')
    if spec.text.startswith(('EMP:','MIL:')): raise PermissionError('Pump command forbidden')
class ReadOnlySocket:
    def __init__(self,sock,events):self.sock=sock;self.events=events
    def __getattr__(self,name):return getattr(self.sock,name)
    def sendto(self,data,destination):
        if destination!=('10.19.70.13',1024): raise PermissionError('Unexpected destination')
        commands=decode_command_datagram(data)
        if len(commands)!=1: raise PermissionError('Only one query per packet is permitted')
        c=commands[0]
        if not (c.command_id in ALLOWED and c.command==COMMANDS[c.command_id].text): raise PermissionError('Non-allowlisted query')
        self.events.append({'kind':'TX_DATAGRAM','monotonic':time.monotonic(),'utc':datetime.now(timezone.utc).isoformat(),'data_hex':data.hex(),'destination':destination})
        return self.sock.sendto(data,destination)
    def recvfrom(self,n):
        data,sender=self.sock.recvfrom(n)
        self.events.append({'kind':'RX_DATAGRAM','monotonic':time.monotonic(),'utc':datetime.now(timezone.utc).isoformat(),'data_hex':data.hex(),'sender':sender})
        return data,sender

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--interval',type=float,choices=[1.0,0.5,0.2,0.1],required=True);ap.add_argument('--cycles',type=int,default=2);ap.add_argument('--capability',action='store_true');args=ap.parse_args()
    if not (args.name.replace('_','').isalnum() and 1<=args.cycles<=12): raise ValueError('Invalid stage bounds')
    folder=ROOT/args.name;folder.mkdir(exist_ok=False)
    transport=UdpTransport(UdpSettings(remote_host='10.19.70.13',remote_port=1024,local_host='10.19.70.1',local_port=1024))
    events=[];results=[];last_send=None;status='starting';state=DeviceState()
    log=(folder/'events.jsonl').open('w',encoding='utf-8')
    def emit(record):log.write(json.dumps(record,ensure_ascii=False)+'\n');log.flush()
    def query(cid,interval,phase):
        nonlocal last_send
        if cid not in ALLOWED: raise PermissionError('Non-allowlisted query')
        if last_send is not None:time.sleep(max(0.0,interval-(time.monotonic()-last_send)))
        line=format_command(cid)
        if line!=f'[{cid}]'+COMMANDS[cid].text: raise PermissionError('Unexpected query text')
        last_send=time.monotonic();record={'kind':'EXCHANGE','phase':phase,'command_id':cid,'tx_monotonic':last_send,'utc':datetime.now(timezone.utc).isoformat(),'line':line}
        before=len(events)
        try:
            replies=transport.exchange(line,3.0)
            record['transport_ok']=True;record['replies']=[{'value':r.value,'raw':r.raw_line,'parser_130_accepts':state.apply(r)} for r in replies]
        except TransportError as exc:record['transport_ok']=False;record['error']=str(exc)
        record['elapsed_seconds']=time.monotonic()-last_send
        for e in events[before:]:emit(e)
        emit(record);results.append(record)
        print(json.dumps({'phase':phase,'id':cid,'ok':record['transport_ok'],'seconds':round(record['elapsed_seconds'],4),'values':[r['value'] for r in record.get('replies',[])]}),flush=True)
        return record
    def check_hv(record):
        values=[r['value'].strip() for r in record.get('replies',[])]
        if not record['transport_ok'] or values!=['0']:raise RuntimeError('Fresh HV OFF was not confirmed; query-only diagnostic stopped without changing output')
    try:
        transport.connect();transport._socket=ReadOnlySocket(transport._socket,events)
        ident=query(1000,1.0,'preflight')
        if not ident['transport_ok'] or not any('SASC' in r['value'] and 'Spectra' in r['value'] for r in ident.get('replies',[])):raise RuntimeError('Unexpected or missing identity')
        check_hv(query(1021,1.0,'preflight'))
        ids=CAPABILITY if args.capability else CORE
        status='passed'
        for cycle in range(args.cycles):
            for cid in ids:
                r=query(cid,args.interval,'measurement')
                if not r['transport_ok']:
                    status='transport_failure';time.sleep(2.0)
                    query(1000,1.0,'recovery_check')
                    raise RuntimeError('One transport failure: stage stopped; no faster stage automatically scheduled')
                if cid in (1021,1061):check_hv(r)
            check_hv(query(1021,args.interval,'boundary'))
        check_hv(query(1021,1.0,'postflight'))
    except Exception as exc:
        if status!='transport_failure':status='stopped'
        emit({'kind':'STOP','reason':str(exc)});print('STOP',str(exc),flush=True)
    finally:
        transport.close();log.close()
        measurement=[r for r in results if r['phase']=='measurement'];tx=[r['tx_monotonic'] for r in measurement]
        summary={'status':status,'name':args.name,'interval_seconds':args.interval,'cycles_requested':args.cycles,'measurement_requests':len(measurement),'transport_successes':sum(r['transport_ok'] for r in measurement),'transport_failures':sum(not r['transport_ok'] for r in measurement),'writes_sent':sum(c.command_id >= 2000 for e in events if e['kind']=='TX_DATAGRAM' for c in decode_command_datagram(bytes.fromhex(e['data_hex']))),'total_datagrams_sent':sum(e['kind']=='TX_DATAGRAM' for e in events),'response_ms_median':statistics.median([r['elapsed_seconds']*1000 for r in measurement if r['transport_ok']]) if any(r['transport_ok'] for r in measurement) else None,'min_measurement_tx_gap':min((b-a for a,b in zip(tx,tx[1:])),default=None),'source':'unmodified installed 1.3.0 transport/codec; strict read-only socket wrapper','finished_utc':datetime.now(timezone.utc).isoformat()}
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
    return 0 if status=='passed' else 2
if __name__=='__main__':raise SystemExit(main())
