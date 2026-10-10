"""The page's prose must take its figures from results.json.

Result figures typed into components go stale on the next republish, and no
other test would notice. Only the legal limits, years, ages, citations and
definitions may appear as literals.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPY_FILES = sorted((ROOT / "src/components").glob("*.tsx")) + [
    ROOT / "src/lib/facts.ts"
]
# Python modules whose string literals reach the page.
PYTHON_COPY_FILES = [ROOT / "src/ssi_asset_limits/publish.py"]
# The legal limits, and the rounding unit of the published tables.
ALLOWED_THOUSANDS = {"1,000", "2,000", "3,000", "10,000", "20,000"}
FORBIDDEN = [
    # A number with a thousands separator: a count or dollar figure.
    re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?!\d|,\d)"),
    # A literal amount in billions or millions.
    re.compile(r"\d(?:\.\d+)?\s*(?:billion|million)\b"),
    # A literal share or ratio (the range level, the weight-concentration
    # threshold and the "under 1 percent" floor are definitions, not results).
    re.compile(
        r"\b(?!99 percent|90 percent|1 percent)\d+(?:\.\d+)? percent\b"
    ),
    re.compile(r"\b\d+(?:\.\d+)? times\b"),
    re.compile(
        r"\bone in (?:two|three|four|five|six|seven|eight|nine|ten|twelve|"
        r"forty)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:about|roughly) (?:half|twice|a third|two-thirds)\b"),
    # Abbreviated amounts and ratios.
    re.compile(r"\$\d+(?:\.\d+)?[BMK]\b"),
    re.compile(r"\d(?:\.\d+)?\s*\u00d7"),
]


def _hits(text: str) -> list[str]:
    return [
        match.group(0)
        for pattern in FORBIDDEN
        for match in pattern.finditer(text)
        if match.group(0) not in ALLOWED_THOUSANDS
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


@pytest.mark.parametrize("path", PYTHON_COPY_FILES, ids=lambda path: path.name)
def test_no_result_figures_are_typed_into_published_strings(path):
    strings = [
        node.value
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    found = [hit for text in strings for hit in _hits(text)]
    assert not found, found


def test_the_guard_catches_abbreviated_figures():
    assert sorted(_hits("$3.6B and 3.6\u00d7 and $2,000")) == [
        "$3.6B",
        "3.6\u00d7",
    ]
