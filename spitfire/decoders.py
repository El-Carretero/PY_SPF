"""Response semantics recovered from native Spitfire GUI 1.6.0.

Panel and control numbers are original UIR identifiers, not new widget indices.
The decoder has no network or GUI side effects. `next_queries` and `effects`
expose actions requested by the original callbacks for the application host.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import struct

_NUMBER = re.compile(r'^[\t\n\r\v\f ]*([+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|inf(?:inity)?|nan))', re.I)
_INTEGER = re.compile(r'^\s*([+-]?\d+)')
_HEX_INTEGER = re.compile(r'^\s*([+-]?(?:0[xX])?[0-9a-fA-F]+)')


def c_atof(text: str) -> float:
    match = _NUMBER.match(text)
    return float(match[1]) if match else 0.0


def c_atoi(text: str) -> int:
    match = _INTEGER.match(text)
    return int(match[1]) if match else 0


def c_scan_hex(text: str) -> int:
    """Read the original sscanf("%x") unsigned 32-bit status field.

    Actual controller captures include an uppercase 0X prefix. A bare-hex
    regular expression would consume only its leading zero and clear faults.
    """
    match = _HEX_INTEGER.match(text)
    return int(match[1], 16) & 0xffffffff if match else 0


def f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


def decode_number(text: str, spaces: int = 6) -> float:
    """_decodenum / _decodenum_del count literal ASCII spaces, including repeats."""
    offset = 0
    for _ in range(spaces):
        offset = text.find(' ', offset)
        if offset < 0:
            return -999.0
        offset += 1
    return c_atof(text[offset:])


@dataclass(frozen=True)
class ControlUpdate:
    panel_id: int
    control_id: int
    value: object
    attribute: int | None = None


class ResponseDecoder:
    """Stateful transcription of _gextHandleReceivedMsg and its decoders."""
    SIMPLE_FLOAT = {
        1007:(9,2,0.1), 1008:(9,5,1), 1018:(6,3,1),
        1030:(2,4,1), 1031:(2,2,1), 1032:(2,7,1),
        1040:(5,35,1), 1041:(5,33,1), 1042:(5,32,1),
        1043:(5,31,1), 1055:(5,30,1), 1056:(5,29,1),
        1060:(6,3,1), 1065:(5,7,1), 1077:(8,15,1), 1084:(2,3,1),
    }
    SIMPLE_INT = {1021:(5,34),1061:(5,34),1078:(8,18),1086:(6,47)}
    # NBWD, NENA, numeric delay, channel-on controls, respectively.
    DELAYS = {
        1045:((5,6),(5,8),(6,43),(6,23)),
        1046:((5,9),(5,10),(6,42),(6,21)),
        1047:((5,13),(5,14),(5,42),(5,25)),
        1048:((5,15),(5,16),(5,41),(5,23)),
        1049:((5,11),(5,12),(6,41),(6,20)),
        1058:((5,6),(5,8),(6,43),(6,23)),
        1059:((5,9),(5,10),(6,42),(6,21)),
    }

    def __init__(self, read=None) -> None:
        self.read = read
        self.values: dict[tuple[int,int], object] = {}
        self.state = {
            'initial_secrets_fill':1, 'initial_secrets_read':1,
            'ecu_optout':0, 'hed_optout':0, 'emp_optout':0,
            'LBO_STABILITY_STATE':0, 'verify':0,
            'hum_blinkval':0, 'tem_blinkval':0, 'old_on_ready':0,
            'delay_monitor_status':1, 'needs_initialization':1,
            'comm_status_emp':0,'comm_status_mil':0,'comm_status_tdg':0,'comm_status_ecu':0,
            'used_comm_status_emp':0,'used_comm_status_mil':0,'used_comm_status_tdg':0,'used_comm_status_ecu':0,
        }
        self.next_queries: list[tuple[int,str]] = []
        self.effects: list[tuple[str,object]] = []
        self._updates: list[ControlUpdate] = []

    def _set(self, panel: int, control: int, value: object, attribute: int | None = None) -> None:
        self._updates.append(ControlUpdate(panel,control,value,attribute))
        if attribute is None:
            self.values[panel,control] = value

    def _bit(self, panel: int, control: int, value: int, mask: int) -> None:
        self._set(panel,control,int(bool(value & mask)))

    def decode_line(self, line: str) -> list[ControlUpdate]:
        """Accept the original decorated '(packet,line)<query_id>payload' line."""
        left = line.find('<')
        right = line.find('>',left+1)
        if left < 0 or right < 0:
            return []
        payload=line[right+1:]
        return self.decode(c_atoi(line[left+1:right]),payload if payload else self.state.get('last_payload',''))

    def decode(self, query_id: int, payload: str) -> list[ControlUpdate]:
        self._updates=[]
        self.next_queries=[]
        self.effects=[]
        payload=payload.split('\0',1)[0]
        if not payload:payload=self.state.get('last_payload','')
        self.state['last_query_id']=query_id
        self.state['last_payload']=payload
        self.effects.append(('connected', True))
        self._set(3,31,0)  # _clear_cksum_err
        number=c_atof(payload)
        integer=c_atoi(payload)
        if query_id in self.SIMPLE_FLOAT:
            panel,control,scale=self.SIMPLE_FLOAT[query_id]
            self._set(panel,control,number/10 if query_id==1007 else (f32(number) if query_id in (1030,1031,1084) else number)*scale)
        elif query_id in self.SIMPLE_INT:
            self._set(*self.SIMPLE_INT[query_id],integer)
        elif query_id in self.DELAYS:
            bwd,enabled,delay,on=self.DELAYS[query_id]
            self._set(*bwd,int('NBWD' not in payload))
            self._set(*enabled,int('NENA' not in payload))
            self._set(*delay,decode_number(payload))
            self._set(*on,int('OFF' not in payload))
        elif query_id in (1063,1064):
            self._set(6,23 if query_id==1063 else 21,int('OFF' not in payload))
        elif query_id==1052:
            self._set(5,4,decode_number(payload,3))
        elif query_id==1054:
            self._set(5,39,int('SING' not in payload))
            self._set(5,37,int('NEG' not in payload))
        elif query_id in (1050,1067):
            self._set(5,2,int('INT' not in payload))
            if query_id==1067:
                if 'INT' not in payload:
                    self.next_queries.extend(((2030,'  INT'),(2030,'  EXT')))
        elif query_id==1051:
            internal='INT' in payload
            self._set(5,3,int(not internal))
            for control,visible in ((6,internal),(7,not internal),(8,internal),(9,not internal)):
                self._set(6,control,int(visible),0x212)
        elif query_id==1080:
            self._set(5,48,int('CONT' not in payload))
        elif query_id==1082:
            self.state['verify']+=1
        elif query_id==1087:
            self._set(2,12,int(integer>0))
        elif query_id in (1033,1068,1069):
            name,control={1033:('ecu_optout',11),1068:('emp_optout',9),1069:('hed_optout',10)}[query_id]
            self.state[name]=integer
            self._set(2,control,integer)
            if query_id in (1033,1068):
                self.effects.append(('hide_ecu' if query_id==1033 else 'hide_emp',integer==1))
        elif query_id==1009:
            if self.state['initial_secrets_fill']:
                self._set(9,8,number/10)
            self._set(9,3,number/10)
        elif query_id==1011:
            if self.state['initial_secrets_fill']:
                self._set(9,10,number)
            self._set(9,6,number)
        elif query_id==1012:
            if self.state['initial_secrets_fill']:
                self._set(9,11,number)
                self.state['initial_secrets_fill']=0
            self._set(9,7,number)
        elif query_id==1010:
            if self.state['initial_secrets_fill']:
                frequency=number*10 if number>=0 else number
                self._set(9,9,frequency)
                self._set(9,4,frequency)
                self._set(6,9,frequency)
                self._refresh_rates()
            else:
                self._set(9,4,number*10)
                self._set(6,9,number*10)
        elif query_id in (1024,1025,1053,1062):
            if query_id==1024:self._set(5,28,number)
            if query_id==1025:self._set(5,43,number)
            if query_id==1053:
                self._set(5,28,number)
                self._set(6,8,self._read(5,28))
            self._refresh_rates()
        elif query_id in (1071,1072,1073,1074,1075,1076):
            edit,read={1071:(13,16),1072:(10,11),1073:(8,9),1074:(6,7),1075:(2,3),1076:(4,5)}[query_id]
            if self.state['initial_secrets_read']:self._set(8,edit,number)
            self._set(8,read,number)
            if query_id==1071:
                self._set(9,2,number,0x2da)
                self._set(9,8,number,0x2da)
            if query_id==1076:self.state['initial_secrets_read']=0
        elif query_id in (1013,1015,1019,1028):
            self._decode_status(query_id,int(f32(number))&0xffffffff)
        elif query_id==1014:
            self._decode_faults(payload)
        elif query_id==1057:
            bits=int(f32(number))&0xffffffff
            self._bit(2,8,bits,2)
            self._bit(2,13,bits,0x20)
        elif query_id==1088:
            bits=int(f32(number))&0xffffffff
            self._bit(3,8,bits,4)
            self._bit(3,10,bits,0x10)
        elif query_id==1029:
            self._decode_ecu_status(int(f32(number))&0xffffffff)
        elif query_id==1039:
            self._decode_tdg_status(c_scan_hex(payload))
        elif query_id==1066:
            bits=c_scan_hex(payload)
            for mask,control in ((0x2000,19),(0x4000,23),(0x1000,14),(0x800,21),(0x8000,22)):
                self._bit(3,control,bits,mask)
            self._set(6,15,int(bool(bits & 0x7000)))
        elif query_id==1089:
            for mask,control in ((1,20),(2,5),(4,9),(8,4)):
                self._bit(3,control,integer,mask)
        elif query_id==1085:
            self.state['pardon_first_time_user']=0
            self.state['delay_monitor_status']=int(bool(integer&1))
            if integer&2:
                self._set(6,23,0);self._set(6,21,0)
                self.state['call_for_reset_c1n2']=1
            if self.state.get('curtain_not_open',1):
                self.effects.append(('open_curtain',True))
                self.state['curtain_not_open']=0
        elif query_id in (1034,1035,1036,1037,1038):
            field={1034:4,1035:7,1036:5,1037:3,1038:6}[query_id]
            if ('NOT CON' in payload if query_id==1038 else 'CONNECTED' in payload):
                value=payload
            else:
                fields=payload.split(',')
                value=fields[2] if len(fields)>2 else ''
                if query_id==1034 and len(fields)>3:value=fields[3].split(' ',1)[0]
                if query_id==1036 and len(fields)>3:value=fields[3].split(' ',1)[0]
            self._set(4,field,value)
        elif query_id==1000:
            self.state['chars_read']=1
        elif query_id==2050:
            self._set(6,58,payload)
        return self._updates.copy()

    def _read(self,panel:int,control:int) -> float:
        for update in reversed(self._updates):
            if update.attribute is None and (update.panel_id,update.control_id)==(panel,control):
                return f32(float(update.value))
        if self.read is not None:
            return f32(float(self.read(panel,control)))
        return f32(float(self.values.get((panel,control),0.0)))

    def _refresh_rates(self) -> None:
        divisor=self._read(5,43)
        pump=self._read(9,9)
        trigger=self._read(5,28)
        if divisor==0:divisor=1.0
        for rate,target in ((trigger,6),(pump,7)):
            self._set(6,target,rate if rate<0 else rate/divisor)

    def _decode_status(self, query_id: int, value: int) -> None:
        high=value>>8
        low=value&255
        if query_id in (1015,1019,1028):
            self.state['initial_secrets_fill_'+{1015:'mil',1019:'tdg',1028:'ecu'}[query_id]]=0
        name,control={1013:('emp',19),1015:('mil',17),1019:('tdg',13),1028:('ecu',16)}[query_id]
        opted=self.state.get({'emp':'emp_optout','mil':'hed_optout','ecu':'ecu_optout'}.get(name,''),0)
        if opted:
            self.state['comm_status_'+name]=0
            self._set(6,control,0)
            return
        comm=high&8
        if self.state['used_comm_status_'+name]!=comm:
            self.effects.append(('initial_updates',name))
            self.state['used_comm_status_'+name]=comm
        self.state['comm_status_'+name]=comm
        self._set(6,control,int(comm==0))
        if query_id==1013:
            on=low&1
            fault=int(bool(high&4) or self.state.get('LBO_STABILITY_STATE')==1)
            ready=int(not(on or high&2 or fault or self.state.get('LBO_STABILITY_STATE')==1))
            for ctrl,val in ((22,on),(31,ready),(29,fault),(24,high&2),(25,high&1)):
                self._set(6,ctrl,val)
            self._set(6,32,int(bool(on or high&2)),0x212)

    def _decode_faults(self, payload: str) -> None:
        fields=[c_atoi(v) for v in payload.split(' ')]
        fields=(fields+[0]*4)[:4]
        b1,b2,b3,lbo=fields
        self.state['LBO_STAB_FAULT']=lbo
        self.state['LBO_STABILITY_STATE']=lbo
        bindings=[(b1,0x40,18),(b1,0x20,11),(b1,0x10,16),(b1,8,24),(b1,2,25),(b1,1,32),
                  (b2,0x80,6),(b2,0x40,7),(b2,0x20,13),(b2,0x10,34),(b2,8,30),(b2,4,12),(b2,2,17),
                  (b3,0x10,15),(b3,2,3),(b3,1,35)]
        for val,mask,control in bindings:self._set(3,control,val&mask)
        self._set(3,2,lbo)

    def _decode_ecu_status(self,value: int) -> None:
        high=value>>8
        low=value&255
        self._set(2,14,int(bool(low&2)))
        for control,blink_mask,yellow_mask,key in ((15,1,2,'hum_blinkval'),(16,4,8,'tem_blinkval')):
            blink=bool(high&blink_mask)
            yellow=bool(high&yellow_mask)
            green=not(blink or yellow)
            self._set(2,control,self.state[key] if blink else 0)
            if blink:self.state[key]=1-int(bool(self.state[key]))
            if yellow:self._set(2,control,0xffff00,0x399)
            if green:self._set(2,control,0x00ff00,0x399)

    def _decode_tdg_status(self,value: int) -> None:
        self._set(5,47,value&1)
        self._set(6,27,int(not(value&0x10000)))
        self._set(6,26,int(not(value&0x20000)))
        mode=value&0x300000
        labels={0:'BWD OK',0x100000:'RESET BWD',0x200000:'RESET BWD',0x300000:'RESET BWD'}
        self._set(6,5,int(mode==0),0x1f4)
        self._set(6,5,0xc0c0c0 if mode==0 else 0xffff00,0x370)
        self._set(6,5,labels[mode],0x281)

    def check_health(self, access_level: int = 0) -> list[ControlUpdate]:
        """_check_if_system_healthy, called by the original auto-poll builder.

        Menu changes are returned in effects as ('menu_disabled',(item_id,bool)).
        A ('fault_update',True) effect requests the original fault query sequence.
        """
        self._updates=[]
        self.next_queries=[]
        self.effects=[]
        healthy=int(self.state['delay_monitor_status']==0)
        if healthy!=self.state['old_on_ready'] or self.state['needs_initialization']:
            self.effects.append(('fault_update',True))
            for control in (10,23,21):self._set(6,control,1-healthy,500)
            self._set(6,50,healthy,500)
            self._set(6,50,'ALL SYS OK' if healthy else 'FAULT (CLICK HERE)',0x281)
            self._set(6,50,0xc0c0c0 if healthy else 0xffff00,0x370)
            self.state['old_on_ready']=healthy
            self.state['needs_initialization']=0
        for name,optout in (('ecu','ecu_optout'),('tdg',None),('mil','hed_optout'),('emp','emp_optout')):
            comm=self.state['comm_status_'+name]
            opted=self.state.get(optout,0)
            signature=(comm,access_level,opted)
            if self.state.get('health_signature_'+name)==signature:continue
            disabled=bool(comm or opted)
            if name=='mil':
                for control in (3,52,51):self._set(6,control,int(disabled and access_level==0),500)
            else:
                menu={'ecu':8,'tdg':7,'emp':5}[name]
                self.effects.append(('menu_disabled',(menu,disabled and access_level==0)))
            if name=='emp':self._set(6,65,int(disabled),0x212)
            self.state['health_signature_'+name]=signature
        return self._updates.copy()
