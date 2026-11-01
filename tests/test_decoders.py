"""Assembly-derived fixtures for the port; no instrument access required."""
import unittest
import ctypes
import json
from pathlib import Path
import sys
from spitfire.decoders import ResponseDecoder,decode_number,f32
from spitfire.protocol import parse_datagram

class OriginalDecoderFixtures(unittest.TestCase):
    def values(self, updates):
        return {(u.panel_id,u.control_id):u.value for u in updates if u.attribute is None}

    def test_literal_space_delay_parser(self):
        self.assertEqual(decode_number('1 ENA BWD ON 0 0 12.75'),12.75)
        self.assertEqual(decode_number('1  2  3  4'),4)
        self.assertEqual(decode_number('1\tENA BWD ON 0 0 12.75'),-999)
        self.assertEqual(decode_number('0 1 2 8.5',3),8.5)

    def test_numeric_and_checksum_bindings(self):
        d=ResponseDecoder()
        self.assertEqual(self.values(d.decode(1007,'123.5')),{(3,31):0,(9,2):12.35})
        self.assertEqual(self.values(d.decode(1030,'12.34'))[(2,4)],f32(12.34))
        self.assertEqual(self.values(d.decode(1040,'2150'))[(5,35)],2150)

    def test_delay_flags_and_six_space_offset(self):
        d=ResponseDecoder()
        v=self.values(d.decode(1045,'1 NENA NBWD OFF 0 0 7.5'))
        self.assertEqual(v[(5,6)],0)
        self.assertEqual(v[(5,8)],0)
        self.assertEqual(v[(6,43)],7.5)
        self.assertEqual(v[(6,23)],0)

    def test_initialization_and_rate_division(self):
        d=ResponseDecoder()
        d.decode(1025,'4')
        d.decode(1024,'1000')
        v=self.values(d.decode(1010,'200'))
        self.assertEqual(v[(9,9)],2000)
        self.assertEqual(v[(6,6)],250)
        self.assertEqual(v[(6,7)],500)
        d.decode(1012,'1')
        v=self.values(d.decode(1010,'300'))
        self.assertNotIn((9,9),v)
        self.assertNotIn((6,7),v)
        self.assertEqual(v[(6,9)],3000)

    def test_status_word_bit_directions(self):
        d=ResponseDecoder()
        v=self.values(d.decode(1039,'30001'))
        self.assertEqual(v[(5,47)],1)
        self.assertEqual(v[(6,27)],0)
        self.assertEqual(v[(6,26)],0)
        v=self.values(d.decode(1066,'7000'))
        self.assertEqual(v[(3,19)],1)
        self.assertEqual(v[(3,23)],1)
        self.assertEqual(v[(3,14)],1)
        self.assertEqual(v[(6,15)],1)

    def test_captured_prefixed_status_preserves_bwd_and_photodiode_flags(self):
        fixture=Path(__file__).resolve().parents[1]/'analysis'/'optout_post2_capture.json'
        capture=json.loads(fixture.read_text(encoding='utf-8'))
        sample=next(s for s in capture['samples'] if s['kind']=='response' and s['tag']==1039)
        reply=parse_datagram(bytes.fromhex(sample['payload_hex']))[0]
        payload=reply.body.split('>',1)[1]
        self.assertEqual(payload,' 0X00330409')
        # This is the original API's conversion, independent of the decoder
        # and the emulator interception code. It must retain the prefix bits.
        word=ctypes.c_uint()
        crt=ctypes.CDLL('msvcrt' if sys.platform=='win32' else None)
        self.assertEqual(crt.sscanf(ctypes.c_char_p(payload.encode('ascii')),
                                   ctypes.c_char_p(b'%x'),ctypes.byref(word)),1)
        self.assertEqual(word.value,0x00330409)
        d=ResponseDecoder()
        updates=d.decode_line(reply.decorated)
        values=self.values(updates)
        self.assertEqual(values[(5,47)],1)
        self.assertEqual(values[(6,27)],0)
        self.assertEqual(values[(6,26)],0)
        attributes={(u.panel_id,u.control_id,u.attribute):u.value
                    for u in updates if u.attribute is not None}
        self.assertEqual(attributes[(6,5,500)],0)
        self.assertEqual(attributes[(6,5,0x281)],'RESET BWD')

    def test_prefixed_fault_readback_keeps_each_fault_indicator(self):
        for payload in ('F800',' 0x0000f800','0X0000F800','+0xF800 trailing'):
            values=self.values(ResponseDecoder().decode(1066,payload))
            for control in (19,23,14,21,22):
                self.assertEqual(values[(3,control)],1,payload)
            self.assertEqual(values[(6,15)],1,payload)

    def test_ecu_blink_and_color(self):
        d=ResponseDecoder()
        a=d.decode(1029,'256')
        self.assertEqual(self.values(a)[(2,15)],0)
        self.assertEqual(self.values(d.decode(1029,'256'))[(2,15)],1)
        a=d.decode(1029,'512')
        self.assertIn((2,15,0xffff00,0x399),[(x.panel_id,x.control_id,x.value,x.attribute)for x in a])
        self.assertEqual(self.values(a)[(2,15)],0)

    def test_fault_word_magnitudes_preserved(self):
        d=ResponseDecoder()
        v=self.values(d.decode(1014,'64 128 16 1'))
        self.assertEqual(v[(3,18)],64)
        self.assertEqual(v[(3,6)],128)
        self.assertEqual(v[(3,15)],16)
        self.assertEqual(d.state['LBO_STABILITY_STATE'],1)

    def test_original_ignored_query_still_clears_checksum(self):
        self.assertEqual(self.values(ResponseDecoder().decode(1044,'garbage')),{(3,31):0})

    def test_reply_decoration_and_reset_response(self):
        d=ResponseDecoder()
        v=self.values(d.decode_line('(10,2)<2050>Reset accepted'))
        self.assertEqual(v[(6,58)],'Reset accepted')
        self.assertEqual(d.decode_line('incomplete'),[])

    def test_identity_disconnected_substring_uses_a_space(self):
        d=ResponseDecoder()
        self.assertEqual(self.values(d.decode(1038,'NOT CONNECTED'))[(4,6)],'NOT CONNECTED')
        self.assertEqual(self.values(d.decode(1038,'Maker,Model,Rev,Firmware'))[(4,6)],'Rev')

    def test_oscillator_query_preserves_original_two_command_sequence(self):
        d=ResponseDecoder()
        d.decode(1067,'EXT')
        self.assertEqual(d.next_queries,[(2030,'  INT'),(2030,'  EXT')])
        d.decode(1067,'INT')
        self.assertEqual(d.next_queries,[])

if __name__=='__main__':unittest.main()
