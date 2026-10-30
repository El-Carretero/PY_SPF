"""Data logger integration checks without starting a device or TCP connection."""
import os
import tempfile
import unittest
from pathlib import Path

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller


class DataLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data_dir = Path(self.temporary.name) / "measurements" / "session"
        self.log_path = self.data_dir / "datalog.csv"
        self.now = 0.0
        self.view = MemoryView()
        self.controller = Controller(
            self.view, data_dir=self.data_dir, tcp_port=None,
            clock=lambda: self.now,
        )
        self.view.values[9, 2] = 12.345
        self.view.values[8, 15] = 36.789

    def tick_at(self, instant):
        self.now = instant
        self.controller.tick()

    def timer_event(self, event=15):
        self.controller.handle_callback(
            "tmr_Data_Logger", event=event, panel=6, control=64,
        )

    def test_default_off_does_not_create_directory_or_file(self):
        self.assertEqual(self.view.read(1, 3), 0)
        self.tick_at(1.0)
        self.tick_at(2.0)
        self.timer_event()
        self.assertFalse(self.data_dir.exists())

    def test_enabled_timer_waits_one_second_and_appends_once_per_interval(self):
        self.view.values[1, 3] = 1
        self.tick_at(0.999)
        self.assertFalse(self.log_path.exists())
        self.tick_at(1.0)
        self.assertEqual(self.log_path.read_text(), "12.35, 36.79\n")

        self.view.values[9, 2] = 2.5
        self.view.values[8, 15] = 42.0
        self.tick_at(1.0)
        self.tick_at(1.999)
        self.assertEqual(self.log_path.read_text(), "12.35, 36.79\n")
        self.tick_at(2.0)
        self.assertEqual(
            self.log_path.read_text(), "12.35, 36.79\n2.50, 42.00\n",
        )

    def test_turning_off_stops_appending(self):
        self.view.values[1, 3] = 1
        self.tick_at(1.0)
        before = self.log_path.read_bytes()
        self.view.values[1, 3] = 0
        self.tick_at(2.0)
        self.tick_at(3.0)
        self.timer_event()
        self.assertEqual(self.log_path.read_bytes(), before)

    def test_only_timer_event_writes_when_enabled(self):
        self.view.values[1, 3] = 1
        for event in (1, 2, 3, 7, 11, 14, 16):
            with self.subTest(event=event):
                self.timer_event(event)
                self.assertFalse(self.log_path.exists())
        self.timer_event(15)
        self.assertEqual(self.log_path.read_text(), "12.35, 36.79\n")

    def test_configured_directory_and_float32_csv_format(self):
        self.view.values[1, 3] = 1
        # Native controls supply float32 values: these round differently from
        # formatting the original Python float64 inputs directly.
        self.view.values[9, 2] = 16.055
        self.view.values[8, 15] = 8.045
        self.timer_event()
        self.assertTrue(self.data_dir.is_dir())
        self.assertEqual(self.log_path.read_text(), "16.06, 8.05\n")
        self.assertEqual(list(self.data_dir.iterdir()), [self.log_path])

    def test_existing_contents_are_preserved(self):
        self.data_dir.mkdir(parents=True)
        previous = b"1.00, 20.00\n"
        self.log_path.write_bytes(previous)
        self.view.values[1, 3] = 1
        self.timer_event()
        self.assertEqual(
            self.log_path.read_bytes(), previous + b"12.35, 36.79" + os.linesep.encode("ascii"),
        )

    def test_native_timer_does_not_also_run_synthetic_timer(self):
        self.view.values[1, 3] = 1
        self.view.native_timers = True
        self.tick_at(1.0)
        self.tick_at(2.0)
        self.assertFalse(self.log_path.exists())
        self.timer_event()
        self.assertEqual(self.log_path.read_text(), "12.35, 36.79\n")


if __name__ == "__main__":
    unittest.main()
