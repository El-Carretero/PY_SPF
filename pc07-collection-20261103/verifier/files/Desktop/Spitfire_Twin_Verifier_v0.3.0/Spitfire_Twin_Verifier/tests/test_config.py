from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spitfire_twin_verifier.config import AppConfig, MAX_CONFIG_BYTES


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'config.json'
        self.path_patch = patch.object(AppConfig, 'path', return_value=self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding='utf-8')

    def test_dataclass_positional_layout_and_defaults_unchanged(self):
        self.assertEqual([field.name for field in fields(AppConfig)], [
            'bind_ip', 'bind_port', 'original_ip', 'python_ip',
            'original_label', 'python_label', 'isolated_clients', 'output_directory'])
        self.assertEqual(AppConfig().bind_ip, '127.0.0.1')
        self.assertEqual(AppConfig().python_label, 'Python 1.3.0')

    def test_missing_file_and_nonobject_json_use_defaults(self):
        self.assertEqual(AppConfig.load(), AppConfig())
        for data in (None, [], [1], True, 42, 'value'):
            with self.subTest(data=data):
                self.write(data)
                self.assertEqual(AppConfig.load(), AppConfig())

    def test_bad_json_duplicate_keys_and_nonfinite_use_defaults(self):
        for raw in ('{', '{"bind_port":2000,"bind_port":3000}',
                    '{"bind_port":NaN}', '{"bind_port":Infinity}'):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding='utf-8')
                self.assertEqual(AppConfig.load(), AppConfig())
        self.path.write_bytes(b'\xff\xfe\x00')
        self.assertEqual(AppConfig.load(), AppConfig())

    def test_oversized_json_does_not_load(self):
        self.path.write_bytes(b' ' * (MAX_CONFIG_BYTES + 1))
        self.assertEqual(AppConfig.load(), AppConfig())

    def test_bad_fields_fallback_without_erasing_valid_user_settings(self):
        self.write({'bind_ip': {'ip': '192.168.20.4'}, 'bind_port': '1024',
                    'original_ip': '192.168.20.2', 'python_ip': '192.168.20.3',
                    'original_label': 'XP custom', 'python_label': [],
                    'isolated_clients': 'false', 'output_directory': 'C:/Verifier Reports',
                    'future_field': {'ignored': True}})
        loaded = AppConfig.load()
        self.assertEqual(loaded.bind_ip, '127.0.0.1')
        self.assertEqual(loaded.bind_port, 1024)
        self.assertEqual(loaded.original_ip, '192.168.20.2')
        self.assertEqual(loaded.python_ip, '192.168.20.3')
        self.assertEqual(loaded.original_label, 'XP custom')
        self.assertEqual(loaded.python_label, 'Python 1.3.0')
        self.assertIs(loaded.isolated_clients, True)
        self.assertEqual(loaded.output_directory, 'C:/Verifier Reports')

    def test_ipv4_policy_preserves_valid_addresses_and_rejects_wildcard(self):
        for bad in ('0.0.0.0', '224.0.0.1', '::1', '999.1.2.3', 1234, None):
            with self.subTest(bad=bad):
                self.write({'bind_ip': bad})
                self.assertEqual(AppConfig.load().bind_ip, '127.0.0.1')
        self.write({'bind_ip': ' 192.168.100.13 '})
        self.assertEqual(AppConfig.load().bind_ip, '192.168.100.13')

    def test_ports_booleans_and_control_characters_fail_closed(self):
        for bad in (True, False, 0, -1, 65536, 1024.0, '1024', []):
            with self.subTest(bad=bad):
                self.write({'bind_port': bad})
                self.assertEqual(AppConfig.load().bind_port, 1024)
        for bad in ('', ' ', 'line\nbreak', '\x00file', '\ud800', 'x' * 129):
            self.write({'original_label': bad})
            self.assertEqual(AppConfig.load().original_label, AppConfig().original_label)
        self.write({'isolated_clients': False})
        self.assertIs(AppConfig.load().isolated_clients, False)

    def test_colliding_addresses_or_labels_restore_only_related_group(self):
        self.write({'bind_ip': '10.19.70.2', 'original_label': 'same',
                    'python_label': 'same', 'output_directory': 'kept'})
        loaded = AppConfig.load()
        self.assertEqual((loaded.bind_ip, loaded.original_ip, loaded.python_ip),
                         ('127.0.0.1', '10.19.70.2', '10.19.70.1'))
        self.assertEqual(loaded.original_label, AppConfig().original_label)
        self.assertEqual(loaded.python_label, AppConfig().python_label)
        self.assertEqual(loaded.output_directory, 'kept')

    def test_valid_roundtrip_and_no_shared_temp_file(self):
        config = AppConfig(bind_ip='192.168.20.13', bind_port=2024,
                           original_label='원본 XP', python_label='Python custom',
                           isolated_clients=False, output_directory='reports/custom')
        config.save()
        self.assertEqual(AppConfig.load(), config)
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')), [])

    def test_invalid_save_does_not_replace_previous_file(self):
        AppConfig().save()
        original = self.path.read_bytes()
        for config in (AppConfig(bind_port=True), AppConfig(bind_ip='0.0.0.0'),
                       AppConfig(isolated_clients='false'),
                       AppConfig(original_label='same', python_label='same')):
            with self.subTest(config=config), self.assertRaises(ValueError):
                config.save()
            self.assertEqual(self.path.read_bytes(), original)

    def test_replace_failure_preserves_existing_and_cleans_temp(self):
        AppConfig().save()
        original = self.path.read_bytes()
        with patch('spitfire_twin_verifier.config.os.replace', side_effect=OSError('blocked')):
            with self.assertRaises(OSError):
                AppConfig(bind_port=2000).save()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')), [])

    def test_concurrent_saves_produce_complete_valid_json(self):
        configs = [AppConfig(bind_port=2000 + index) for index in range(16)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda config: config.save(), configs))
        self.assertIn(AppConfig.load(), configs)
        self.assertIn(json.loads(self.path.read_text())['bind_port'], range(2000, 2016))
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
