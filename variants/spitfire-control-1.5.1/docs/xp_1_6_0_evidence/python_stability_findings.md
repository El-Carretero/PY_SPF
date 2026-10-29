# Python stability audit, 1.3.0 working tree

Read-only source review followed by scoped fixes authorized by root. No hardware, socket, COM, or GUI activation.

## Fixed in this agent's files

1. `config.py`: persisted configuration only validated pump mode. A string timeout such as `"bad"` survived load and would reach `math.isfinite` in the controller, raising TypeError during startup. Strict validation now covers mode enums, nonempty string hosts, integer ports, finite positive timeout, poll >=0.2, boolean polling options, and string log path. Invalid persisted configuration falls back to default simulator configuration.
2. `config.py`: all writers shared the same `.tmp` file, allowing concurrent saves to interfere. Save now revalidates mutable fields and uses a unique temporary file in the destination directory, flush/fsync, atomic replacement, and cleanup after failure. Failed replacement preserves original file contents.
3. `serial_service.py`: a handle successfully created by the serial backend was leaked when subsequent DTR/RTS configuration failed before assigning `self._serial`. Failed configuration/open now closes the local handle.
4. `serial_service.py`: requested control lines were applied after opening the device. Native pySerial creation now uses `serial_for_url(..., do_not_open=True)`, configures requested DTR/RTS, then opens. This removes the application's use of default states before applying requested settings; it cannot promise that every USB/serial driver is electrically glitch-free.

## Regressions run

- `tests/test_config_validation.py`: 5 pass, 0.205s. Includes malformed settings, valid old settings migration, atomic failure preservation, invalid post-construction mutation, and unique temporary path behavior.
- `tests/test_serial_integrity.py` plus `tests/test_serial_service.py`: 9 pass, 0.007s, with offline I/O fence and memory-only fake handles. Includes control-line ordering before open and cleanup after DTR, RTS, open, and invalid factory states.
- Existing `FakeSerial` was changed to begin unopened and expose `open()` to follow the stricter injection contract.

## Findings passed to root (root owns implementation/status)

- Alias readback error invalidation: a malformed/error 1061 HV alias previously left canonical 1021 fresh. Root fixed alias propagation; a later reproduction returned `high_voltage=None`, canonical fresh=False, invalid IDs {1061,1021}.
- Active-output timing-source change: pre-enable synchronization gates alone do not prevent 2030/2031 source changes while HV is already ON. Requested fresh HV OFF guards at submission and transmission for timing source changes; oscillator reference update 2046 also warrants this guard.
- CLI transport flags: parser accepted both `--simulator --udp`, and later main logic selected UDP. Recommended mutually exclusive argument group with startup regression.
- Programmer query arguments: Empower profile accepted a query argument such as `;TDG:HV ON` without write classification. Actual firmware semicolon interpretation is not established here; recommended universally rejecting command separators/control characters and query arguments except the proven channel query 1026.

## Remaining limits observed

- UDP has command IDs but no per-request sequence token. Sender and command ID checks reject foreign peers and unrelated replies, but cannot conclusively distinguish an unusually late same-ID reply from a current request. This is a protocol limitation; no new replay guarantee is claimed.
- Main AuditLog intentionally swallows file OSError so logging failure cannot block OFF. An operator-visible warning for unavailable audit logs would improve diagnosability without changing the OFF path.
- Original firmware compatibility, physical timing, and channel readback semantics are owned by the binary/manual reviewers and require hardware confirmation where not proven.
