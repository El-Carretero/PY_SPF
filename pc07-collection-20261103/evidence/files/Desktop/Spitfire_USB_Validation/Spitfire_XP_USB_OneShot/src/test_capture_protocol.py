#!/usr/bin/env python3
"""Portable tests run the exact C parser linked into the XP binary.
Fixture is a previous real XP-program/simulator capture, never physical hardware.
Mutations below are offline parser cases only and are never sent on a network.
"""
import collections,ctypes as C,hashlib,json,struct,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
src=root/'src'; build=root/'build/capture';build.mkdir(parents=True,exist_ok=True)
subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',str(src/'capture_protocol.c'),'-o',str(build/'protocol-test.so')],check=True)
lib=C.CDLL(str(build/'protocol-test.so'))
u32=C.c_uint32;u16=C.c_uint16;u=C.c_uint
class Packet(C.Structure):
 _fields_=[('src_ip',u32),('dst_ip',u32),('src_port',u16),('dst_port',u16),('payload',C.POINTER(C.c_ubyte)),('payload_len',u32),('kind',u),('tag',u),('write_commands',u),('first_write_tag',u),('malformed_command',u)]
class Pair(C.Structure):
 _fields_=[('client_ip',u32),('controller_ip',u32),('client_port',u16),('controller_port',u16),('interface_id',u),('commands',u),('responses',u),('last_command_ms',u32),('last_response_ms',u32)]
class Observation(C.Structure):
 _fields_=[('pairs',Pair*64),('pair_count',u),('pair_overflow',u),('command_packets',u),('response_packets',u),('any_write_commands',u),('first_write_tag',u),('malformed_commands',u)]
lib.cap_decode_ethernet.argtypes=[C.POINTER(C.c_ubyte),C.c_size_t,C.POINTER(Packet)]
lib.cap_observe.argtypes=[C.POINTER(Observation),C.POINTER(Packet),u,C.c_int,C.c_int,u32]
lib.cap_pair_ready.argtypes=[C.POINTER(Observation),u32]
def decode(frame):
 buf=(C.c_ubyte*len(frame)).from_buffer_copy(frame);p=Packet()
 valid=lib.cap_decode_ethernet(buf,len(frame),C.byref(p))
 p._buffer=buf
 return valid,p
def observe(obs,p,iface=1,tick=1000,local=0x0a134602):
 lib.cap_observe(C.byref(obs),C.byref(p),iface,p.src_ip==local,p.dst_ip==local,tick)
def ready(obs,tick=1000):return bool(lib.cap_pair_ready(C.byref(obs),tick))
fixture=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/workspace/spitfire-evidence/original.pcap')
audit=fixture.with_name('original.audit.json')
expected=json.loads(audit.read_text())
raw=fixture.read_bytes();assert raw[:4]==b'\xd4\xc3\xb2\xa1'
assert struct.unpack_from('<I',raw,20)[0]==1
pos=24;frames=0;counts=collections.Counter();tags={1:collections.Counter(),2:collections.Counter()};obs=Observation();samples={}
while pos<len(raw):
 sec,usec,caplen,wirelen=struct.unpack_from('<IIII',raw,pos);pos+=16
 frame=raw[pos:pos+caplen];pos+=caplen;assert len(frame)==caplen
 frames+=1;valid,p=decode(frame)
 if valid and p.kind:
  counts[p.kind]+=1;tags[p.kind][str(p.tag)]+=1;samples.setdefault(p.kind,frame)
  observe(obs,p,tick=(sec*1000+usec//1000)&0xffffffff)
assert pos==len(raw)
assert frames==expected['frame_count']==46666
assert counts=={1:20148,2:20148},counts
assert dict(tags[1])==expected['request_tag_counts']
assert dict(tags[2])==expected['response_tag_counts']
assert obs.pair_count==1 and obs.command_packets==obs.response_packets==20148
assert obs.any_write_commands==14 and obs.first_write_tag==2047
assert not obs.malformed_commands
assert not ready(obs,obs.pairs[0].last_response_ms)
# Actual frame retains exact prefix and payload; synthetic response is explicitly labeled.
req=samples[1];rep=samples[2];_,qp=decode(req);_,rp=decode(rep)
assert qp.tag==rp.tag==1000
# Recent bidirectionality is required; a same-direction packet cannot substitute.
fresh=Observation()
for _ in range(3):observe(fresh,qp)
assert not ready(fresh)
for _ in range(3):observe(fresh,rp)
assert ready(fresh)
assert ready(fresh,6000) and not ready(fresh,6001)
# Millisecond tick wrap works through unsigned subtraction.
wrap=Observation()
for _ in range(3):observe(wrap,qp,tick=0xfffffff0);observe(wrap,rp,tick=0xfffffff0)
assert ready(wrap,20)
# Duplicate same pair on another adapter is deliberately ambiguous.
observe(fresh,qp,iface=2)
assert fresh.pair_count==2 and not ready(fresh)
# Nonlocal/prefix-only traffic cannot establish original-program endpoint pair.
wrong=Observation()
for _ in range(3):observe(wrong,qp,local=0x01020304);observe(wrong,rp,local=0x01020304)
assert wrong.pair_count==0 and not ready(wrong)
# Every truncation of a complete query before its declared UDP end is rejected.
for n in range(len(req)):assert not decode(req[:n])[0],n
# VLAN single and double tagging decode the same captured IP datagram.
for tags_bytes in (b'\x81\x00\x00\x01',b'\x88\xa8\x00\x01\x81\x00\x00\x02'):
 valid,p=decode(req[:12]+tags_bytes+req[12:]);assert valid and p.kind==1 and p.tag==1000
# IPv4 fragments remain raw-PCAP evidence, but are excluded from endpoint proof.
fragment=bytearray(req);fragment[20:22]=b'\x20\x00';assert not decode(fragment)[0]
# Controlled offline payload substitutions test unknown and combined commands.
def with_payload(payload):
 b=bytearray(req[:42]+payload);struct.pack_into('!H',b,16,len(b)-14);struct.pack_into('!H',b,38,len(payload)+8);return bytes(b)
prefix=b'Spectra-Physics:CMD_ECLIPSE,'
for body in (b'[999]UNKNOWN?\n',b'[abc]UNKNOWN\n',b'[1000]\n',b'[999999999]X\n',b'broken\n'):
 valid,p=decode(with_payload(prefix+body));assert valid and p.malformed_command
 blocked=Observation()
 for _ in range(3):observe(blocked,qp);observe(blocked,rp)
 assert ready(blocked);observe(blocked,p);assert not ready(blocked)
for body,nwrites in ((b'[2000]X\n',1),(b'[1999]SAFE?\n[2036]OTHER\n[2047]LBOBREAK 0\n',2)):
 valid,p=decode(with_payload(prefix+body));assert valid and p.write_commands==nwrites
 blocked=Observation()
 for _ in range(3):observe(blocked,qp);observe(blocked,rp)
 assert ready(blocked);observe(blocked,p)
 assert not ready(blocked) and blocked.any_write_commands==nwrites
 for _ in range(3):observe(blocked,qp);observe(blocked,rp)
 assert not ready(blocked),'write latch must not clear after later good queries'
report={'test':'exact native-C parser replay + offline boundary/fail-closed cases','passed':True,
'fixture':str(fixture),'fixture_sha256':hashlib.sha256(raw).hexdigest(),
'fixture_provenance':'previous XP original-program requests / simulator-generated replies; not physical controller',
'frames':frames,'command_packets':counts[1],'response_packets':counts[2],
'request_and_response_tag_counts_match_independent_audit':True,
'write_commands_detected':obs.any_write_commands,'first_write_tag':obs.first_write_tag,
'checks':['all actual frames, counts and per-tag counts','unique bidirectional pair','no replies fails closed','freshness and tick wrap','duplicate adapter ambiguity','nonlocal traffic exclusion','all request truncations','VLAN single/double','fragment exclusion','malformed/unknown tag rejection','multiple write tags per packet and permanent UI-stop latch'],
'limitation':'Does not validate a live WinPcap driver or physical controller.'}
(build/'parser-replay-test.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
