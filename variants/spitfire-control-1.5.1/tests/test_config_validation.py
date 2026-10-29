"""Configuration boundary and atomic persistence regressions; no device I/O."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spitfire_control.config import AppConfig


class ConfigurationValidationTests(unittest.TestCase):
    def test_malformed_saved_values_fall_back_without_startup_crash(self):
        invalid = (
            ("mode", "serial"), ("mode", []), ("pump_mode", "other"),
            ("remote_host", " "), ("remote_host", 123), ("local_host", None),
            ("remote_host", "127.0.0.1\n"), ("remote_port", "1024"),
            ("remote_port", True), ("remote_port", 0), ("local_port", 65536),
            ("timeout_seconds", "bad"), ("timeout_seconds", None),
            ("timeout_seconds", float("nan")), ("timeout_seconds", float("inf")),
            ("timeout_seconds", 0), ("timeout_seconds", False),
            ("timeout_seconds", 10 ** 1000),
            ("poll_interval_seconds", 0.19), ("poll_interval_seconds", "1"),
            ("auto_poll", "false"), ("monitor_hv", 1), ("log_directory", []),
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for key, value in invalid:
                with self.subTest(key=key, value=value):
                    raw = asdict(AppConfig(mode="udp", pump_mode="external"))
                    raw[key] = value
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    self.assertEqual(AppConfig.load(path), AppConfig())

    def test_old_valid_config_migrates_and_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"mode": "udp", "remote_host": "10.19.70.13",
                                        "local_port": 0, "future_option": 123}), encoding="utf-8")
            result = AppConfig.load(path)
            self.assertEqual(result.mode, "udp")
            self.assertEqual(result.pump_mode, "empower")
            self.assertEqual(result.local_port, 0)

    def test_atomic_save_failure_preserves_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            original = AppConfig()
            original.save(path)
            before = path.read_bytes()
            with patch.object(Path, "replace", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    AppConfig(pump_mode="external").save(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_mutated_invalid_config_cannot_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            cfg = AppConfig()
            cfg.save(path)
            before = path.read_bytes()
            cfg.timeout_seconds = "broken"
            with self.assertRaises(ValueError):
                cfg.save(path)
            self.assertEqual(path.read_bytes(), before)

    def test_save_round_trip_uses_own_unique_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            unrelated = path.with_suffix(".tmp")
            unrelated.write_text("another writer", encoding="utf-8")
            config = AppConfig(mode="udp", pump_mode="external", local_port=0,
                               timeout_seconds=0.1, poll_interval_seconds=0.2,
                               auto_poll=False, monitor_hv=True)
            config.save(path)
            self.assertEqual(AppConfig.load(path), config)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "another writer")
            self.assertEqual(list(Path(folder).glob("config.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
