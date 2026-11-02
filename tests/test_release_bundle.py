"""Public package selection and private evidence exclusion contracts."""
import importlib.util
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

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
        for path in ('docs/source-development.md', 'requirements-build.txt',
                     'packaging/windows/build.ps1', 'packaging/windows/test_install.ps1',
                     'packaging/windows/PY_SPF.spec', 'packaging/windows/installer.iss',
                     'packaging/windows/native.manifest', 'packaging/windows/native_app.py'):
            self.assertTrue(build.public_source_path(path), path)

    def test_runtime_captures_and_old_release_evidence_are_excluded(self):
        for path in ('logs/native/events.jsonl', '.venv-native/pyvenv.cfg',
                     'analysis/device-capture.pcapng', 'analysis/device-capture.json',
                     'analysis/post2_windows_native_gui.json', 'output/old-release.zip',
                     'ANALYSIS.ko.md', 'POST2.ko.md', 'Legacy/notes/ANALYSIS.ko.md',
                     'Legacy/source-distributions/PY_SPF_1.0/PY_SPF_1.0.zip',
                     'Legacy/source-distributions/PY_SPF_1.0/README.md',
                     'dist/source/PY_SPF_1.0/README.md',
                     'packaging/windows/dist/PY_SPF/private.py',
                     'packaging/windows/build/private.py'):
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
                'docs/source-development.md': b'Current developer instructions',
                'docs/private-notes.md': b'Not selected',
                'packaging/windows/build.ps1': b'Write-Host build',
                'packaging/windows/dist/PY_SPF/private.py': b'generated payload',
                'Legacy/source-distributions/PY_SPF_1.0/README.md': b'historical instructions',
            }.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            selected=dict(build.source_entries(root))
            self.assertEqual(set(selected), {'README.md', 'spitfire/__init__.py',
                                            'docs/source-development.md', 'packaging/windows/build.ps1'})

    def test_source_rebuild_targets_dist_and_preserves_historical_and_native_outputs(self):
        """Exercise main's destinations without pip or an actual archive build."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = {
                'Legacy/source-distributions/PY_SPF_1.0/PY_SPF_1.0.zip': b'original ZIP bytes',
                'Legacy/source-distributions/PY_SPF_1.0/spitfire_gui_reconstruction-1.0.0-py3-none-any.whl': b'original wheel bytes',
                'Legacy/source-distributions/PY_SPF_1.0/README.md': b'historical instructions',
                'Legacy/source-distributions/PY_SPF_1.0/SHA256.json': b'original manifest',
                'Legacy/MANIFEST.json': b'original provenance',
                'output/README.md': b'primary output index',
                'output/native-installer/setup.exe': b'current installer bytes',
            }
            fixtures = {
                **historical, 'pyproject.toml': b'version = "1.0.0"\n',
                'spitfire/resources/SPITFIRE.UIR': b'fixture native resource',
                'docs/source-development.md': b'# Current source development\nUse the source tools.\n',
            }
            for name, data in fixtures.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            wheel_name = 'spitfire_gui_reconstruction-1.0.0-py3-none-any.whl'
            source_archive = mock.MagicMock()
            installed_wheel = mock.MagicMock()
            installed_wheel.read.side_effect = lambda name: {
                'spitfire/resources/SPITFIRE.UIR': b'fixture native resource',
                'spitfire_gui_reconstruction-1.0.0.dist-info/METADATA': b'Version: 1.0.0\n',
            }[name]
            installed_wheel.namelist.return_value = ['licenses/THIRD_PARTY_NOTICES.md']

            def fake_wheel(command, *, check):
                self.assertTrue(check)
                destination = Path(command[command.index('--wheel-dir') + 1])
                self.assertEqual(destination, root / 'dist/source/PY_SPF_1.0')
                (destination / wheel_name).write_bytes(b'mocked new wheel')

            def fake_archive(path, mode='r', **kwargs):
                context = mock.MagicMock()
                if mode == 'w':
                    Path(path).write_bytes(b'mocked new source ZIP')
                    context.__enter__.return_value = source_archive
                else:
                    context.__enter__.return_value = installed_wheel
                return context

            with mock.patch.object(build, 'ROOT', root), \
                 mock.patch.object(build.subprocess, 'run', side_effect=fake_wheel) as subprocess_run, \
                 mock.patch.object(build.zipfile, 'ZipFile', side_effect=fake_archive), \
                 contextlib.redirect_stdout(io.StringIO()):
                build.main()
            self.assertEqual(subprocess_run.call_count, 1)
            for name, data in historical.items():
                self.assertEqual((root / name).read_bytes(), data, name)
            output = root / 'dist/source/PY_SPF_1.0'
            self.assertTrue((output / 'SHA256.json').is_file())
            readme = (output / 'README.md').read_bytes()
            self.assertIn(fixtures['docs/source-development.md'], readme)
            self.assertNotIn(b'historical instructions', readme)
            source_archive.write.assert_called_once_with(
                output / wheel_name, 'PY_SPF_1.0/dist/source/PY_SPF_1.0/' + wheel_name)
            written = dict((call.args[0], call.args[1]) for call in source_archive.writestr.call_args_list)
            self.assertEqual(written['PY_SPF_1.0/dist/source/PY_SPF_1.0/README.md'], readme)
            self.assertIn('PY_SPF_1.0/docs/source-development.md', written)
            self.assertFalse(any('/Legacy/' in name or '/output/' in name for name in written))


if __name__ == '__main__':
    unittest.main()
