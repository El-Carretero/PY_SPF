# Spitfire Twin Verifier 0.3.1

Local Windows workbench for comparing Spitfire XP GUI wire evidence and multiple Python Control versions. See START_HERE_KO.txt first.

0.3.1 serializes configuration reads/writes within one process to avoid Windows
handle contention during concurrent saves. Atomic replacement and permission-error
propagation are preserved. This is not a cross-process transaction lock; see
docs/RELEASE_CHANGES_0.3.1.txt for scope and P07 validation.

This release separates four kinds of evidence: synthetic model assertions, real selected Python transport/state/policy tests, captured XP/Python packets, and manual GUI observations. None is a physical safety certificate. No outgoing hardware-control destination is provided by the automated matrix or passive replay.

## Start

- Windows: double-click Start-SpitfireTwinVerifier.bat. It prefers the included dist EXE when available.
- Source: Python3.10+ with Tk, then python run_verifier.py.
- Actual imported Python source tests still require a separate Python interpreter, including when the verifier itself is an EXE.

## Features

- Version declarations for XP1.6.0 / Python1.1.3 / Python1.3.0, with static ZIP/folder inspection and whole-ZIP/source hashes.
- Unknown Python versions can use the shared API adapter; compatibility is established per tested case, never inferred from the version string. Incompatible APIs are UNSUPPORTED/ERROR.
- 19 actual-client fixtures using that artifact's formatter, UDP transport, decoder, state and optional external-pump enable-policy functions.
- 12 JSON event scenarios: trigger loss/duplicate/jitter/rate/phase, seed/pump loss, readiness, interlock, thermal/flow/HV and communication recovery.
- Per-client isolated state and first-request realtime epoch; manual virtual checkpoints for repeatable comparisons.
- Raw datagram capture, exact/semantic/framing comparisons, phase mismatch detection, response and request loss distinguished.
- Strict offline capture import, bounded require/forbid reaction assertions, passive loopback exact-byte response replay.
- JSON and HTML reports, GUI observation records, evidence labels and explicit missing-coverage states.

## Command line

Run from this folder; use the same switches on dist/SpitfireTwinVerifierCLI.exe.

    python run_verifier.py --self-test
    python run_verifier.py --list-profiles
    python run_verifier.py --list-scenarios
    python run_verifier.py --run-scenario seed_loss_recovery
    python run_verifier.py --scenario-suite
    python run_verifier.py --inspect-client path/to/Spitfire_Python_Control.zip
    python run_verifier.py --matrix old.zip new.zip --trust-client-code
    python run_verifier.py --matrix new.zip --trust-client-code --python-executable C:/Python313/python.exe
    python run_verifier.py --compare-capture capture.jsonl --original-label "XP Original 1.6.0" --python-label "Python 1.3.0"
    python run_verifier.py --compare-capture capture.jsonl --reaction-rules reference/reaction_rules.example.json
    python run_verifier.py --replay-capture capture.jsonl --replay-label "Python 1.3.0" --bind 127.0.0.1 --port 19024 --duration 60

--matrix explicitly executes selected trusted Python source. The subprocess and socket audit guard are not a security sandbox for hostile code. Inspection itself never imports the artifact. The controller's complete scheduling loop and GUI are not executed by matrix cases.

For XP, start the headless or GUI listener only on the isolated Host-only adapter. The bundled network scripts are opt-in and must never target the lab's physical adapter. An XP host-only example is bind10.19.70.13:1024, XP10.19.70.2, Python host10.19.70.1. Existing IP conflicts must be resolved first.

## What the model does not establish

The event policy is synthetic. It is not a firmware model or electrical edge generator. Its armed/inhibited values are scenario policy state, not measured HV or optical output. They do not automatically force unknown firmware writes/readbacks. Only explicit wire fixtures affect UDP replies; fault-to-register causation is not invented. The same response is not proof that both clients recognized or safely reacted to it.

The original installer has146 recovered numeric slots, including empty2034:145 nonempty slots,132 exact unique strings including empty,131 nonempty unique strings. This is not a complete firmware/service protocol. Original TCP1001 and physical RS-232/HIL are not implemented by this UDP twin.

## Test and build

    python run_tests.py
    python tools/validate_release.py --output validation_output
    python tools/windows_gui_smoke.py --output validation_output/gui_smoke.json
    powershell -ExecutionPolicy Bypass -File build_windows.ps1

The build script creates a local venv and downloads build dependencies only when explicitly run. It is not needed to run the supplied EXEs. Package data is included in wheels/frozen builds. See docs/VALIDATION_RESULTS_0.3.0.txt for the actual environment and omissions.

Historical v0.1/v0.2 documents remain as history only; v0.3 files are authoritative for this release.
