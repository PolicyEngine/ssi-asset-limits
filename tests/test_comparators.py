import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from ssi_asset_limits.comparators import (
    CBPP_NEW_BENEFICIARIES,
    OACT_LETTERS,
    SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024,
    SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL,
)

SOURCES = Path(__file__).resolve().parents[1] / "sources"


def test_cbpp_constants_match_the_transcribed_table():
    table = pd.read_csv(SOURCES / "cbpp_2023_table1.csv")
    for scenario, rows in CBPP_NEW_BENEFICIARIES.items():
        for group, value in rows.items():
            hit = table[
                (table.scenario == scenario) & (table.age_group == group)
            ]["new_beneficiaries"]
            assert len(hit) == 1
            if value is None:
                assert pd.isna(hit.iloc[0])
            else:
                assert hit.iloc[0] == value


def test_ssa_counts_match_the_transcribed_table():
    text = (SOURCES / "ssa_ssi_monthly_2024-12_table01.txt").read_text()
    line = next(
        row for row in text.splitlines() if "Total with federal payment" in row
    )
    numbers = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{5,}", line)]
    assert numbers == [
        SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL,
        SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024["children_under_18"],
        SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024["adults_18_64"],
        SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024["elderly_65_plus"],
    ]
    assert sum(SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024.values()) == (
        SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL
    )


def test_oact_letters_are_archived_with_their_hashes():
    sums = dict(
        reversed(line.split())
        for line in (SOURCES / "SHA256SUMS").read_text().splitlines()
    )
    for letter in OACT_LETTERS:
        name = letter["url"].rsplit("/", 1)[-1]
        data = (SOURCES / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sums[name]


def oact_table(letter):
    """Years and amounts from the cost table in a letter's text extract."""

    name = letter["url"].rsplit("/", 1)[-1].replace(".pdf", ".txt")
    lines = (SOURCES / name).read_text().splitlines()
    header = next(
        i
        for i, line in enumerate(lines)
        if re.fullmatch(r"\s*(\d{4}\s+)+\d{4}-\d{2}\s*", line)
    )
    columns = lines[header].split()
    row = next(line for line in lines[header + 1 :] if "$" in line)
    amounts = re.findall(r"--|\$[\d.]+", row)
    return dict(zip(columns, amounts, strict=True))


def test_oact_figures_match_the_letters():
    for letter in OACT_LETTERS:
        table = oact_table(letter)
        total_column = letter["total_label"].replace("–", "-")
        expected = {
            str(year): "--" if value is None else f"${value:.1f}"
            for year, value in letter["annual"].items()
        }
        expected[total_column] = f"${letter['total_billions']:.1f}"
        assert table == expected


def test_oact_letters_assume_january_eligibility():
    for letter in OACT_LETTERS:
        name = letter["url"].rsplit("/", 1)[-1].replace(".pdf", ".txt")
        text = " ".join((SOURCES / name).read_text().split())
        year = letter["effective"].split()[-1]
        # The date must be the one the estimate assumes, not any mention.
        pattern = (
            rf"effective for eligibility starting (?:on )?January 1, {year}"
        )
        assert re.search(pattern, text), letter["date"]


@pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="pdftotext not installed"
)
def test_oact_text_extracts_come_from_the_archived_letters(tmp_path):
    for letter in OACT_LETTERS:
        name = letter["url"].rsplit("/", 1)[-1]
        out = tmp_path / name.replace(".pdf", ".txt")
        subprocess.run(
            ["pdftotext", "-layout", str(SOURCES / name), str(out)],
            check=True,
        )
        assert out.read_text() == (SOURCES / out.name).read_text()
