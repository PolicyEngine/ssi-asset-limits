"""The page's prose must take its figures from results.json.

Result figures typed into components go stale on the next republish, and no
other test would notice. Only the legal limits, years, ages, citations and
definitions may appear as literals.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPY_FILES = sorted((ROOT / "src/components").glob("*.tsx")) + [
    ROOT / "src/lib/facts.ts"
]
ALLOWED_THOUSANDS = {"2,000", "3,000", "10,000", "20,000"}
FORBIDDEN = [
    # A number with a thousands separator: a count or dollar figure.
    re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?!\d|,\d)"),
    # A literal amount in billions or millions.
    re.compile(r"\d(?:\.\d+)?\s*(?:billion|million)\b"),
    # A literal share or ratio (the range level and the weight-concentration
    # threshold are definitions, not results).
    re.compile(r"\b(?!99 percent|90 percent)\d+(?:\.\d+)? percent\b"),
    re.compile(r"\b\d+(?:\.\d+)? times\b"),
    re.compile(
        r"\bone in (?:two|three|four|five|six|seven|eight|nine|ten|twelve|"
        r"forty)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:about|roughly) (?:half|twice|a third|two-thirds)\b"),
]


@pytest.mark.parametrize("path", COPY_FILES, ids=lambda path: path.name)
def test_no_result_figures_are_typed_into_page_copy(path):
    text = path.read_text()
    found = []
    for pattern in FORBIDDEN:
        for match in pattern.finditer(text):
            if match.group(0) in ALLOWED_THOUSANDS:
                continue
            line = text.count("\n", 0, match.start()) + 1
            found.append(f"{path.name}:{line}: {match.group(0)!r}")
    assert not found, "\n".join(found)


def test_the_guard_catches_a_typed_figure():
    sample = "the model has 153,000 against 154,000, about twice, 21 percent"
    hits = [
        match.group(0)
        for pattern in FORBIDDEN
        for match in pattern.finditer(sample)
        if match.group(0) not in ALLOWED_THOUSANDS
    ]
    assert sorted(hits) == ["153,000", "154,000", "21 percent", "about twice"]
