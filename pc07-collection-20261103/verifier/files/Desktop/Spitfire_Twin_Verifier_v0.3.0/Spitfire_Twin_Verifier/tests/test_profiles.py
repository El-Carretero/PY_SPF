import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from spitfire_twin_verifier.catalog import COMMANDS
from spitfire_twin_verifier.profiles import (InspectionError, catalog_digest, get_profile,
                                            inspect_client, list_profiles, materialized_client)


def make_client(root, version="9.9.0"):
    package = Path(root) / "src" / "spitfire_control"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = ' + repr(version), encoding="utf-8")
    commands = "_QUERIES = " + repr({cid: spec.text for cid, spec in COMMANDS.items() if cid < 2000})
    commands += "\n_WRITES = " + repr({cid: (spec.text, "risk") for cid, spec in COMMANDS.items() if cid >= 2000})
    (package / "commands.py").write_text(commands, encoding="utf-8")
    (package / "transport.py").write_text("class UdpTransport: pass\nclass UdpSettings: pass\n", encoding="utf-8")
    (package / "state.py").write_text("class DeviceState: pass\n", encoding="utf-8")
    return package


class ProfileTests(unittest.TestCase):
    def test_builtin_profiles_are_declarations_not_test_claims(self):
        profiles = list_profiles()
        self.assertEqual({p["version"] for p in profiles}, {"1.6.0", "1.1.3", "1.3.0"})
        self.assertEqual(get_profile("xp_gui_1.6.0")["evidence_status"], "STATIC_RECOVERY_ONLY")
        profiles[0]["label"] = "changed"
        self.assertNotEqual(list_profiles()[0]["label"], "changed")
        with self.assertRaises(ValueError):
            get_profile("invented")

    def test_static_inspection_does_not_execute_init(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(directory)
            with (package / "__init__.py").open("a") as stream:
                stream.write("\nraise RuntimeError('must not execute')\n")
            result = inspect_client(directory)
            self.assertEqual(result["catalog_entries"], 146)
            self.assertEqual(result["unique_commands"], 132)
            self.assertTrue(result["catalog_matches_recovered"])
            self.assertIsNone(result["profile_id"])
            self.assertEqual(result["evidence_status"], "NOT_EXECUTED")
            with materialized_client(directory) as root:
                self.assertEqual(inspect_client(root)["source_sha256"], result["source_sha256"])

    def test_source_hash_covers_behavior_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(directory, "1.3.0")
            first = inspect_client(directory)
            with (package / "state.py").open("a") as stream:
                stream.write("# behavioral source update\n")
            second = inspect_client(directory)
            self.assertNotEqual(first["source_sha256"], second["source_sha256"])
            self.assertEqual(first["catalog_sha256"], second["catalog_sha256"])

    def test_zip_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(Path(directory) / "client")
            archive = Path(directory) / "client.zip"
            with zipfile.ZipFile(archive, "w") as target:
                for item in package.iterdir():
                    target.write(item, "release/src/spitfire_control/" + item.name)
            result = inspect_client(archive)
            self.assertEqual(result["artifact_hash_scope"], "whole_zip")
            with materialized_client(archive) as root:
                self.assertEqual(inspect_client(root)["source_sha256"], result["source_sha256"])

    def test_rejects_zip_traversal_absolute_and_backslash(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("../evil.py", "/evil.py", "C:/evil.py", "a\\evil.py"):
                archive = Path(directory) / "bad.zip"
                with zipfile.ZipFile(archive, "w") as target:
                    target.writestr(name, "pass")
                with self.assertRaises(InspectionError):
                    inspect_client(archive)

    def test_rejects_zip_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bad.zip"
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr(info, "destination")
            with self.assertRaises(InspectionError):
                inspect_client(archive)

    def test_rejects_ambiguous_zip_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("a/spitfire_control/__init__.py", "__version__='1'")
                target.writestr("b/spitfire_control/__init__.py", "__version__='2'")
            with self.assertRaises(InspectionError):
                inspect_client(archive)

    def test_rejects_dynamic_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(directory)
            (package / "commands.py").write_text("_QUERIES = dict()", encoding="utf-8")
            with self.assertRaises(InspectionError):
                inspect_client(directory)

    def test_features_are_detected_from_api_not_version_string(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(directory, "1.3.0")
            self.assertEqual(inspect_client(directory)["adapter_features"], [])
            (package / "state.py").write_text(
                "class DeviceState:\n def external_enable_reason(self): pass\n def external_timing_reason(self): pass\n",
                encoding="utf-8")
            (package / "timing.py").write_text("def validate_timing_expectations(a,b,c): pass\n", encoding="utf-8")
            self.assertEqual(inspect_client(directory)["adapter_features"], ["external_state_policy"])


if __name__ == "__main__":
    unittest.main()
