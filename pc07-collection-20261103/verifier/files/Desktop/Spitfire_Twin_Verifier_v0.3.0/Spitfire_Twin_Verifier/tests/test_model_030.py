import unittest
from spitfire_twin_verifier.model import VirtualSpitfire
from spitfire_twin_verifier.protocol import decode_commands, encode_commands


class Model030Tests(unittest.TestCase):
    def setUp(self):
        self.model = VirtualSpitfire()

    def answer(self, text):
        return self.model.answer('client', decode_commands(encode_commands([text]))[0])

    def test_modes_are_original_text_tokens(self):
        self.assertEqual(self.answer('[1050]TDG:OSC:MODE?').value, 'INT')
        self.answer('[2030]TDG:OSC:MODE EXT')
        self.assertEqual(self.answer('[1067]TDG:OSC:MODE?').value, 'EXT')
        self.answer('[2031]TDG:TRIG:MODE EXT')
        self.assertEqual(self.answer('[1051]TDG:TRIG:MODE?').value, 'EXT')

    def test_osc_reference_does_not_mutate_ambiguous_rate(self):
        before = self.answer('[1024]TDG:OSC:FREQ?').value
        self.answer('[2046]TDG:OSC:SETTOFRQ 79.5')
        self.assertEqual(self.answer('[1065]TDG:READ:OSCQUEST?').value, '79.5')
        self.assertEqual(self.answer('[1024]TDG:OSC:FREQ?').value, before)

    def test_reset_is_module_scoped_fixture(self):
        state = self.model.state_for('client')
        state.values.update({1014:'1 2 3 4',1029:16,1066:'4000'})
        self.answer('[2044]EMP:RESETFAULTS')
        self.assertEqual(state.values[1014], '0 0 0 0')
        self.assertEqual(state.values[1029], 16)
        self.assertEqual(state.values[1066], '4000')
        self.answer('[2049]ECU:RESETFAULTS')
        self.assertEqual(state.values[1066], '4000')

    def test_generic_query_argument_is_accepted_but_not_certified(self):
        answer = self.answer('[1026]TDG:DEL 1')
        self.assertEqual(answer.validation, 'VALID')
        self.assertFalse(answer.modelled)
        self.assertEqual(answer.effect, 'unmodelled_query')
        self.assertEqual(self.answer('[1026]TDG:DEL 9').validation, 'INVALID_ARGUMENT')

if __name__ == '__main__':
    unittest.main()
