"""The controller names no vendor, no microscope and no vendor software.

The controller is the vocabulary every microscope shares, so nothing in this
repository may lean on one of them. This test reads every text file and
fails on a name, so none comes back.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: The names that must not appear, as whole words, in any letter case.
VENDOR_NAMES = re.compile(
    r"\b(leica|stellaris|las ?x|nikon|nis-elements|zeiss|zen|mesospim|olympus)\b",
    re.IGNORECASE,
)

#: The kinds of file that hold text a person reads.
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yml", ".yaml", ".cff", ".txt", ".cfg"}

#: Folders that are made by tools, not written by hand.
MADE_BY_TOOLS = {".git", "build", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}


def text_files():
    """Every text file of the repository, except those tools make and this test itself."""
    for path in REPOSITORY.rglob("*"):
        parts = set(path.relative_to(REPOSITORY).parts)
        if parts & MADE_BY_TOOLS or any(part.endswith(".egg-info") for part in parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES and path != Path(__file__).resolve():
            yield path


def test_no_file_names_a_vendor():
    found = [
        f"{path.relative_to(REPOSITORY)}:{number}: {line.strip()}"
        for path in text_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if VENDOR_NAMES.search(line)
    ]
    assert found == [], "\n".join(found)
