"""1.3.0 command/transport-choice boundaries; memory-only hardware stand-in."""
import contextlib
import io
import unittest
from unittest.mock import patch

from spitfire_control.app import main
from spitfire_control.commands import format_command
from spitfire_control.controller import LaserController
from spitfire_control.profiles import is_stop_command
from spitfire_control.protocol import Reply
from spitfire_control.transport import SimulatorTransport


class HardwareNamedSimulator(SimulatorTransport):
    name = "offline hardware stand-in"


class CommandArgumentBoundaryTests(unittest.TestCase):
    def test_control_characters_are_rejected_before_whitespace_normalization(self):
        for cid, valid in ((1026, "1"), (2019, "1 OFF")):
            for control in ("\n", "\r", "\t", "\x00", "\x1f", "\x7f"):
                for argument in (control + valid, valid + control, valid + control + "EXTRA"):
                    with self.subTest(cid=cid, argument=argument), self.assertRaises(ValueError):
                        format_command(cid, argument)

    def test_query_arguments_are_limited_to_documented_channel_query(self):
        for cid in (1000, 1014, 1021, 1050, 1051, 1065, 1089):
            with self.subTest(cid=cid), self.assertRaises(ValueError):
                format_command(cid, "1")
        for argument in ("0", "6", "1 2", "1.0", "1 ON", "1\n2017"):
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                format_command(1026, argument)
        for channel in range(1, 6):
            self.assertEqual(format_command(1026, channel), f"[1026]TDG:DEL {channel}")
        self.assertEqual(format_command(1000), "[1000]*idn?")

    def test_semicolon_query_injection_never_enters_either_queue(self):
        for mode in ("empower", "external"):
            with self.subTest(mode=mode), patch("spitfire_control.controller.AuditLog"):
                transport = HardwareNamedSimulator()
                controller = LaserController(transport, pump_mode=mode, auto_poll=False)
                for cid, argument in ((1000, ";TDG:HV ON"), (1026, "1;TDG:HV ON"),
                                      (1000, "x\n[2017]TDG:HV:ON")):
                    with self.subTest(cid=cid, argument=argument), self.assertRaises(ValueError):
                        controller.submit(cid, argument, origin="Programmer")
                self.assertFalse(controller._commands)
                self.assertFalse(controller._urgent)
                self.assertEqual(transport.command_history, [])

    def test_write_separator_is_rejected_even_when_command_is_otherwise_safe_off(self):
        for argument in ("1 OFF;TDG:HV ON", "1 OFF\n[2017]TDG:HV:ON"):
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                format_command(2019, argument)


class TransportChoiceBoundaryTests(unittest.TestCase):
    def test_conflicting_flags_fail_before_config_or_gui_or_device_setup(self):
        for flags in (("--simulator", "--udp"), ("--udp", "--simulator")):
            with self.subTest(flags=flags), patch("spitfire_control.app.AppConfig.load") as load, patch("spitfire_control.app.tk.Tk") as tk, patch("spitfire_control.app.SpitfireApp") as app, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(list(flags))
                self.assertEqual(raised.exception.code, 2)
                load.assert_not_called()
                tk.assert_not_called()
                app.assert_not_called()


class ChannelOffBoundaryTests(unittest.TestCase):
    def make_controller(self, mode):
        transport = HardwareNamedSimulator()
        transport.connect()  # In-memory state only; this class has no sockets.
        self.addCleanup(transport.close)
        return LaserController(transport, pump_mode=mode, auto_poll=False), transport

    def test_every_channel_off_is_urgent_without_current_readbacks(self):
        with patch("spitfire_control.controller.AuditLog"):
            for mode in ("empower", "external"):
                for channel in range(1, 6):
                    with self.subTest(mode=mode, channel=channel):
                        controller, transport = self.make_controller(mode)
                        argument = f"{channel}   OFF"
                        controller.submit(2019, argument)
                        self.assertFalse(controller._commands)
                        self.assertEqual(len(controller._urgent), 1)
                        controller._execute(controller._urgent.popleft())
                        self.assertEqual(transport.command_history, [(2019, f"TDG:DEL {argument}")])

    def test_channel_off_invalidates_dequeued_and_queued_writes_in_both_modes(self):
        with patch("spitfire_control.controller.AuditLog"):
            for mode in ("empower", "external"):
                with self.subTest(mode=mode):
                    controller, transport = self.make_controller(mode)
                    controller._state.connected = controller._state.transport_open = True
                    controller._state.apply(Reply(1000, "Spitfire", "<1000>Spitfire"))
                    controller.submit(2019, "1 20")
                    dequeued = controller._commands.popleft()
                    controller.submit(2019, "2 40")
                    controller.submit(1000)
                    old_generation = controller._generation
                    controller.submit(2019, "1 OFF")
                    self.assertGreater(controller._generation, old_generation)
                    self.assertEqual([request.command_id for request in controller._commands], [1000])
                    controller._execute(dequeued)
                    self.assertEqual(transport.command_history, [])
                    controller._execute(controller._urgent.popleft())
                    self.assertEqual(transport.command_history, [(2019, "TDG:DEL 1 OFF")])

    def test_off_extra_or_other_settings_do_not_receive_safe_off_privileges(self):
        arguments = ("1 OFF EXTRA", "1 OFFF", "OFF", "6 OFF", "01 OFF", "1 ON", "1 0")
        with patch("spitfire_control.controller.AuditLog"):
            for mode in ("empower", "external"):
                for argument in arguments:
                    with self.subTest(mode=mode, argument=argument):
                        controller, transport = self.make_controller(mode)
                        self.assertFalse(is_stop_command(2019, argument))
                        with self.assertRaises((PermissionError, ValueError)):
                            controller.submit(2019, argument)
                        self.assertFalse(controller._urgent)
                        self.assertFalse(controller._commands)
                        self.assertEqual(transport.command_history, [])


if __name__ == "__main__":
    unittest.main()
