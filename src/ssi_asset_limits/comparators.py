"""Published figures the app compares PolicyEngine's estimates with.

Every value here is transcribed from the source named next to it. Copies of
the public-domain sources (SSA tables and OACT letters) are kept in
``sources/`` with their SHA-256 hashes; CBPP's table is transcribed as numbers
only.
"""

from __future__ import annotations

SSA_SSI_MONTHLY_DEC_2024_URL = (
    "https://www.ssa.gov/policy/docs/statcomps/ssi_monthly/2024-12/"
    "table01.html"
)
SSA_SSI_MONTHLY_DEC_2024_LABEL = (
    "SSI Monthly Statistics, December 2024, Table 1"
)

# People with a federal SSI payment in December 2024, by age (Table 1,
# "Total with— Federal payment"). Microcosm calibrates to these counts.
SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024 = {
    "children_under_18": 1_001_922,
    "adults_18_64": 3_905_779,
    "elderly_65_plus": 2_382_142,
}
SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL = 7_289_843

CBPP_CITATION = (
    "Romig, Nuñez and Sherman, “The Case for Updating SSI Asset Limits,” "
    "Center on Budget and Policy Priorities, September 2023, Table 1"
)
CBPP_URL = (
    "https://www.cbpp.org/research/social-security/"
    "the-case-for-updating-ssi-asset-limits"
)
CBPP_DATA_YEAR = 2014

# CBPP Table 1, "Estimated Number of New Beneficiaries at Higher SSI Asset
# Thresholds", rounded to the nearest 1,000. None = "n/a" in the table
# (sample too small). Couple limits are twice the individual limit.
CBPP_NEW_BENEFICIARIES = {
    "ten_twenty": {
        "total_all_ages": 224_000,
        "children_under_18": 23_000,
        "adults_18_64": 154_000,
        "elderly_65_plus": None,
    },
    "no_limit": {
        "total_all_ages": 462_000,
        "children_under_18": 49_000,
        "adults_18_64": 298_000,
        "elderly_65_plus": 115_000,
    },
}

OACT_LETTERS = [
    {
        "date": "August 7, 2026",
        "title": (
            "OACT letter to Sen. Cassidy on a proposal similar to S. 1234, "
            "the SSI Savings Penalty Elimination Act"
        ),
        "url": "https://www.ssa.gov/oact/solvency/BCassidy_20260807.pdf",
        "effective": "January 2027",
        "indexing": (
            "Limits of $10,000 and $20,000 from 2027, indexed to CPI-U from "
            "2028; 2025 SSI Annual Report assumptions; CPS ASEC data."
        ),
        "annual": {
            2025: None,
            2026: None,
            2027: 0.5,
            2028: 1.0,
            2029: 1.1,
            2030: 1.2,
            2031: 1.2,
            2032: 1.3,
            2033: 1.3,
            2034: 1.4,
        },
        "total_label": "2025–34",
        "total_billions": 8.9,
    },
    {
        "date": "January 29, 2024",
        "title": (
            "OACT letter to Sens. Brown and Cassidy on S. 2767, the SSI "
            "Savings Penalty Elimination Act"
        ),
        "url": "https://www.ssa.gov/OACT/solvency/BrownCassidy_20240129.pdf",
        "effective": "January 2024",
        "indexing": (
            "Limits of $10,000 and $20,000 from 2024, indexed to CPI-U from "
            "2025; 2023 SSI Annual Report assumptions."
        ),
        "annual": {
            2023: None,
            2024: 0.5,
            2025: 1.0,
            2026: 1.0,
            2027: 1.1,
            2028: 1.1,
            2029: 1.1,
            2030: 1.2,
            2031: 1.3,
            2032: 1.4,
        },
        "total_label": "2023–32",
        "total_billions": 9.8,
    },
]
