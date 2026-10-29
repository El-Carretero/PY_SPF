"""Assembly-derived fixtures for the port; no instrument access required."""
import unittest
from spitfire.decoders import ResponseDecoder,decode_number,f32

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
