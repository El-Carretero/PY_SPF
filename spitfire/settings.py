"""Original file locations, INI service-level gate and keyboard sequences.

The binary names user_settings.txt but only reads c:\\config.sp in this build.
It appends two numeric readings to datalog.csv when its logging timer is enabled.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import configparser
import re

USER_SETTINGS_NAME = "user_settings.txt"
ORIGINAL_CONFIG_PATH = r"c:\config.sp"
DATALOG_NAME = "datalog.csv"
ACCESS_WORDS = ("user", "regensvc", "factory", "programmer")
ACCESS_LABELS = ("USER MODE", "SERVICE MODE, CLICK TO LOWER LEVEL",
                 "FACTORY MODE, CLICK TO LOWER LEVEL",
                 "PROGRAMMER MODE, CLICK TO LOWER LEVEL")


def c_atoi(value: str) -> int:
    match = re.match(r"\s*([+-]?\d+)", value)
    return int(match.group(1)) if match else 0


def read_max_level(path: str | Path | None = None) -> int:
    """Read [Spitfire] maxLevel, default 0, with the native 8-character limit."""
    config_path = Path(path) if path is not None else Path(ORIGINAL_CONFIG_PATH)
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(config_path, encoding="cp1252")
    except (OSError, configparser.Error):
        return 0
    section = next((x for x in parser.sections() if x.casefold() == "spitfire"), None)
    if section is None:
        return 0
    raw = parser.get(section, "maxLevel", fallback="0").strip().strip('"\'')[:8]
    return c_atoi(raw)


def access_allowed(level: int, max_level_code: int) -> bool:
    if level in (0, 1):
        return True
    if level == 2:
        return max_level_code in (6251, 3146)
    return level == 3 and max_level_code == 3146


@dataclass
class AccessKeySequence:
    """Four independent case-sensitive key matchers from _MainCallBack.

    A mismatched key clears that sequence's progress. The mismatched key is
    not reconsidered as the first character, matching the original callback.
    """
    indices: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    def feed(self, key: str | int, max_level_code: int = 0) -> int | None:
        char = chr(key & 0xff) if isinstance(key, int) else key[:1]
        requested = None
        for level, word in enumerate(ACCESS_WORDS):
            index = self.indices[level]
            if char == word[index]:
                index += 1
                if index == len(word):
                    if access_allowed(level, max_level_code):
                        requested = level
                        index = 0
                    # Original leaves a rejected complete sequence at strlen.
                    # Avoid an out-of-bounds comparison on the next key.
                    else:
                        index = 0
            else:
                index = 0
            self.indices[level] = index
        return requested


def append_datalog(first: float, second: float,
                   path: str | Path = DATALOG_NAME) -> None:
    """0x412e60: append no-header readings using '%.2f, %.2f\\n'."""
    with Path(path).open("a", encoding="ascii") as stream:
        stream.write(f"{first:.2f}, {second:.2f}\n")
