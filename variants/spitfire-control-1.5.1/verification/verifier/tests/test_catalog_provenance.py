"""Regression fingerprint independently recovered from the supplied XP EXE.

The vendor binary is deliberately not bundled. Set SPITFIRE_XP_EXE to the
extracted original EXE for the optional direct binary comparison. A catalog
match is not evidence that the XP program was executed or behaved correctly.
"""
import hashlib
import os
from pathlib import Path
import unittest

from spitfire_twin_verifier.catalog import COMMANDS, QUERIES, WRITES


CATALOG_SHA256 = "ea17f85b5b3213a3ee52141072c2da5349994cd18478c589fc36965bc3ddc8c4"
EXE_SHA256 = "8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b"
SLOT_SHA256 = "e9a3064e9c50429eb8118d7c9a913422a71361e2888384e721151694c9182308"


class CatalogProvenanceTests(unittest.TestCase):
    def test_recovered_table_fingerprint(self):
        canonical = "".join(f"{cid}\t{spec.text}\n" for cid, spec in sorted(COMMANDS.items())).encode("ascii")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), CATALOG_SHA256)

    def test_count_means_slots_not_unique_named_commands(self):
        self.assertEqual(set(QUERIES), set(range(1000, 1090)))
        self.assertEqual(set(WRITES), set(range(2000, 2056)))
        names = [s.text for s in COMMANDS.values()]
        self.assertEqual(len(names), 146)
        self.assertEqual(sum(bool(s) for s in names), 145)
        self.assertEqual(len(set(names)), 132)
        self.assertEqual(len({s for s in names if s}), 131)
        self.assertEqual(len({s.upper() for s in names}), 130)
        self.assertEqual(COMMANDS[2034].text, "")

    def test_status_sources_are_distinct_commands(self):
        expected = {1014: "EMP:FAULT?", 1039: "TDG:STBH?",
                    1066: "TDG:STBHFLT?", 1088: "ECU:STBH?",
                    1089: "COMSTATUS?", 1065: "TDG:READ:OSCQUEST?"}
        for cid, name in expected.items():
            self.assertEqual(COMMANDS[cid].text, name)

    @unittest.skipUnless(os.environ.get("SPITFIRE_XP_EXE"), "optional vendor EXE not bundled; set SPITFIRE_XP_EXE")
    def test_user_supplied_original_binary(self):
        data = Path(os.environ["SPITFIRE_XP_EXE"]).read_bytes()
        self.assertEqual(len(data), 271360)
        self.assertEqual(hashlib.sha256(data).hexdigest(), EXE_SHA256)
        slots = data[0x30b70:0x30b70 + 90 * 30] + data[0x315fc:0x315fc + 56 * 30]
        self.assertEqual(hashlib.sha256(slots).hexdigest(), SLOT_SHA256)
        for offset, first_id, count in ((0x30b70, 1000, 90), (0x315fc, 2000, 56)):
            for index in range(count):
                text = data[offset + index * 30:offset + (index + 1) * 30].split(b"\0", 1)[0].decode("ascii")
                self.assertEqual(text, COMMANDS[first_id + index].text)


if __name__ == "__main__":
    unittest.main()
