# Validation bundle for Spitfire Python Control 1.5.0

The independent Twin Verifier fixture is based on source version 0.3.1.
Local changes: SASC delay grammar with the significant leading space; current wire units;
HV wire defaults; nonzero TDG health values formatted as hexadecimal. Tests updated to these contracts.
It remains a protocol model, not a firmware or physical laser model. The delayed MAIN transition
is explicitly injected by CapturedResetTwin based on the earlier capture; it is not a derived reset mechanism.

Run the product and verifier suites using run_tests.py as documented in the root README.
The optional vendor-binary test requires the user's original SPITFIRE_XP_EXE; the binary is not redistributed.
Detailed results, skips, source hashes and captures are in results/. Earlier primary evidence is in reference/.

1.5.0 current runs are under results/v1_5_0; all other result folders are historical 1.4.0 data.
Product PC-output fixtures in tests/test_release_150.py inject loss, NACK, mismatch, and a key/reset/HV
transition explicitly. This is scenario coverage, not firmware or electrical validation.
The original vendor binary is not bundled or executed in this release.
