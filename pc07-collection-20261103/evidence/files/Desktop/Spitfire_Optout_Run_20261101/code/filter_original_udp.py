"""Make a byte-preserving UDP-only view of the complete classic Ethernet PCAP."""
import argparse,hashlib,json,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
b=a.input.read_bytes();assert b[:4]==b'\xd4\xc3\xb2\xa1' and struct.unpack_from('<I',b,20)[0]==1
out=bytearray(b[:24]);offset=24;kept=[];frames=0
while offset<len(b):
 start=offset;sec,usec,n,orig=struct.unpack_from('<IIII',b,offset);offset+=16;f=b[offset:offset+n];assert len(f)==n;offset+=n;frames+=1
 if len(f)<42 or f[12:14]!=b'\x08\x00' or f[23]!=17:continue
 ihl=(f[14]&15)*4
 if ihl<20 or len(f)<14+ihl+8:continue
 ports=struct.unpack_from('!HH',f,14+ihl)
 pair={f[26:30],f[30:34]}
 if ports==(1024,1024) and pair=={bytes([10,19,70,2]),bytes([10,19,70,13])}:
  out.extend(b[start:offset]);kept.append(frames)
assert offset==len(b) and not a.output.exists();a.output.write_bytes(out)
r={'source_sha256':hashlib.sha256(b).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'source_frames':frames,'kept_frames':len(kept),'all_kept_record_headers_and_frame_bytes_unchanged':True,'source_frame_numbers':kept}
a.output.with_suffix('.filter.json').write_text(json.dumps(r,indent=2));print({k:v for k,v in r.items() if k!='source_frame_numbers'})
