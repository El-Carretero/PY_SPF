"""Public package selection and private evidence exclusion contracts."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_builder', ROOT/'tools/build_release.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ReleaseBundleTests(unittest.TestCase):
    def test_exact_public_name_and_all_native_resources_selected(self):
        self.assertEqual(build.RELEASE_NAME, 'PY_SPF_1.0')
        self.assertEqual(build.PACKAGE_VERSION, '1.0.0')
        for path in (ROOT/'spitfire/resources').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                self.assertTrue(build.public_source_path(path.relative_to(ROOT).as_posix()), path)
        self.assertTrue(build.public_source_path('run_readonly.bat'))

    def test_runtime_captures_and_old_release_evidence_are_excluded(self):
        for path in ('logs/native/events.jsonl', '.venv-native/pyvenv.cfg',
                     'analysis/device-capture.pcapng', 'analysis/device-capture.json',
                     'analysis/post2_windows_native_gui.json', 'output/old-release.zip'):
            self.assertFalse(build.public_source_path(path), path)
        with self.assertRaises(RuntimeError):
            build.check_public_content('tests/fixtures/example.json', b'{"fixture_kind":"device_capture"}')

    def test_validation_report_cannot_publish_personal_capture_paths(self):
        separator = chr(92)
        private = ('C:'+separator+'Users'+separator+'Example'+separator+'capture').encode()
        with self.assertRaises(RuntimeError):
            build.check_public_content('analysis/release_1_0_validation.json', private)
        build.check_public_content('analysis/release_1_0_validation.json', b'{"passed":true,"source":"synthetic"}')

    def test_extracted_source_can_select_build_entries_without_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name,data in {
                'README.md': b'Public source', 'spitfire/__init__.py': b'',
                'logs/native/events.jsonl': b'private runtime record',
                'analysis/device-capture.json': b'private capture',
                'output/old-release.zip': b'old binary',
            }.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            selected=dict(build.source_entries(root))
            self.assertEqual(set(selected), {'README.md','spitfire/__init__.py'})


if __name__ == '__main__':
    unittest.main()
