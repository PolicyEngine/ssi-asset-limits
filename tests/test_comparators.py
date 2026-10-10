import hashlib
import re
from pathlib import Path

import pandas as pd

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
