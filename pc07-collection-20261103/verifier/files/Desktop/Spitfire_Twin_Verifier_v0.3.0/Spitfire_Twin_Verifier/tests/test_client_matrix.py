import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from spitfire_twin_verifier.client_matrix import _evaluate, _WORKER, _FixtureDevice, _interpreter, _run_case, matrix_cases, run_matrix
from spitfire_twin_verifier.model import ResponseProfile
from spitfire_twin_verifier.protocol import decode_commands, encode_commands
from test_profiles import make_client


class ClientMatrixTests(unittest.TestCase):
    def test_execution_requires_trust_consent(self):
        with self.assertRaisesRegex(ValueError, "trust"):
            run_matrix(["anything"])

    def test_empty_matrix_cannot_pass(self):
        with self.assertRaises(ValueError):
            run_matrix([], trusted=True)

    def test_evaluator_flags_value_and_fault_differences(self):
        case = {"operations": [{"id": 1066, "expected_value": 16384, "expected_fault_active": True}]}
        status, rows = _evaluate(case, {"operations": [{"id": 1066, "value": 4000, "accepted": True,
                                                       "fault_active": False}]})
        self.assertEqual(status, "FAIL")
        self.assertEqual(rows[0]["differences"], ["value differs", "fault_active differs"])

    def test_arbitrary_exception_is_not_timeout_success(self):
        case = {"operations": [{"id": 1024, "expected_timeout": True}]}
        status, _ = _evaluate(case, {"operations": [{"id": 1024, "transport_error": True, "error": "bad argument"}]})
        self.assertEqual(status, "FAIL")

    def test_missing_and_extra_results_fail(self):
        case = {"operations": [{"id": 1024, "expected_value": 80}]}
        self.assertEqual(_evaluate(case, {"operations": []})[0], "FAIL")
        self.assertEqual(_evaluate(case, {"operations": [
            {"id": 1024, "value": 80, "accepted": True}, {"id": 1024} ]})[0], "FAIL")

    def test_invalid_artifact_is_error_not_pass(self):
        result = run_matrix(["/does/not/exist"], trusted=True)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["xp_execution"], "NOT_PERFORMED")

    def test_network_guard_blocks_remote_at_import(self):
        with tempfile.TemporaryDirectory() as directory:
            package = make_client(directory)
            (package / "__init__.py").write_text(
                "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\ns.sendto(b'x', ('10.19.70.13', 1024))\n",
                encoding="utf-8")
            payload = {"source_root": str(package.parent), "port": 9999, "operations": []}
            result = subprocess.run([sys.executable, "-I", "-c", _WORKER, json.dumps(payload)],
                                    text=True, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only 127.0.0.1", result.stderr)

    def test_cases_never_issue_emission_hv_or_motion_command(self):
        writes = {op["id"] for case in matrix_cases() for op in case["operations"] if op["id"] >= 2000}
        self.assertEqual(writes, {2020})

    def test_frozen_app_does_not_spawn_itself(self):
        with patch.object(sys, "frozen", True, create=True), patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Python 3.10"):
                _interpreter()

    def test_unknown_external_policy_is_unsupported_not_success(self):
        case = next(c for c in matrix_cases() if c["id"] == "external_ready")
        result = _run_case(Path("unused"), {"adapter_features": []}, case, 5, [sys.executable])
        self.assertEqual(result["status"], "UNSUPPORTED")

    def test_ordered_wire_override_recovery(self):
        device = _FixtureDevice([{"id": 1065, "wire_overrides": {1065: "0"}},
                                 {"id": 1065, "wire_overrides": {1065: "80"}}])
        command = decode_commands(encode_commands(["[1065]TDG:READ:OSCQUEST?"]))[0]
        self.assertEqual(device.answer("test", command).value, "0")
        self.assertEqual(device.answer("test", command).value, "80")

    def test_policy_rejection_must_be_observed_not_just_numeric_reply(self):
        case = {"operations": [{"id": 1065, "expected_value": 0, "expected_enable_allowed": False}]}
        actual = {"operations": [{"id": 1065, "accepted": True, "value": 0, "enable_allowed": True}]}
        self.assertEqual(_evaluate(case, actual)[0], "FAIL")


if __name__ == "__main__":
    unittest.main()
