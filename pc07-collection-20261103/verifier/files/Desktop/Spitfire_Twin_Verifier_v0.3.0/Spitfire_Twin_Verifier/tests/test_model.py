import unittest

from spitfire_twin_verifier.catalog import COMMANDS
from spitfire_twin_verifier.model import VirtualSpitfire
from spitfire_twin_verifier.protocol import decode_commands, encode_commands


def command(line):
    return decode_commands(encode_commands([line]))[0]


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.model = VirtualSpitfire(isolated_clients=True)

    def test_default_qswitch_wire_unit(self):
        answer = self.model.answer("left", command("[1010]EMP:QSW:PRF?"))
        self.assertEqual(answer.value, "100")

    def test_write_and_readback(self):
        self.assertEqual(self.model.answer("left", command("[2004]EMP:QSW:PRF 125.00")).value, "OK")
        self.assertEqual(self.model.answer("left", command("[1010]EMP:QSW:PRF?")).value, "125")

    def test_client_states_are_isolated(self):
        self.model.answer("left", command("[2003]EMP:DIODE:CURR 22"))
        self.assertEqual(self.model.answer("left", command("[1009]EMP:DIODE:CURR?")).value, "22")
        self.assertEqual(self.model.answer("right", command("[1009]EMP:DIODE:CURR?")).value, "18")

    def test_shared_state_option(self):
        model = VirtualSpitfire(isolated_clients=False)
        model.answer("left", command("[2003]EMP:DIODE:CURR 22"))
        self.assertEqual(model.answer("right", command("[1009]EMP:DIODE:CURR?")).value, "22")

    def test_delay_compound_record(self):
        self.model.answer("left", command("[2019]TDG:DEL 1 12.5"))
        result = self.model.answer("left", command("[1045]TDG:DEL1?"))
        self.assertTrue(result.value.endswith("= 12.5"))

    def test_profile_override_drop_and_error(self):
        self.model.profile.overrides[1031] = "88.8"
        self.assertEqual(self.model.answer("x", command("[1031]ECU:HUM?")).value, "88.8")
        self.model.profile.overrides.clear()
        self.model.profile.error_ids.add(1031)
        self.assertEqual(self.model.answer("x", command("[1031]ECU:HUM?")).value, "ERROR:INJECTED")
        self.model.profile.drop_ids.add(1031)
        self.assertTrue(self.model.answer("x", command("[1031]ECU:HUM?")).dropped)

    def test_all_recovered_ids_receive_answer(self):
        for command_id, spec in COMMANDS.items():
            line = f"[{command_id}]{spec.text}"
            answer = self.model.answer("coverage", command(line))
            self.assertIsNotNone(answer.value, command_id)


if __name__ == "__main__":
    unittest.main()

