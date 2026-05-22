"""External benchmark comparisons for SSI asset-limit estimates."""

from __future__ import annotations

import pandas as pd

from .constants import (
    CBPP_TEN_TWENTY_NEW_BENEFICIARIES,
    OACT_TEN_TWENTY_2026_FEDERAL_SSI_COST,
)


def _metric_value(summary: pd.DataFrame, metric: str) -> float:
    value = summary.loc[summary["metric"] == metric, "value"].iloc[0]
    return float(value)


def calculate_external_benchmark_comparison(
    summary: pd.DataFrame,
    cbpp_new_beneficiaries: float = CBPP_TEN_TWENTY_NEW_BENEFICIARIES,
    oact_annual_cost: float = OACT_TEN_TWENTY_2026_FEDERAL_SSI_COST,
) -> pd.DataFrame:
    """Compare PolicyEngine output with CBPP recipients and OACT cost.

    This is intended for the $10,000 individual / $20,000 couple resource-limit
    scenario. PolicyEngine output already includes its seeded SSI take-up
    assignment and calibration to SSI amount and recipient targets. CBPP
    reports new beneficiaries; OACT reports federal SSI payment cost. The
    combined row asks what benefit-amount scale is needed after matching
    PolicyEngine's post-take-up new-recipient count to CBPP.
    """

    pe_cost = _metric_value(summary, "annual_ssi_cost")
    pe_new_recipients = _metric_value(summary, "new_recipients")
    pe_average_cost = pe_cost / pe_new_recipients

    new_beneficiary_scale = cbpp_new_beneficiaries / pe_new_recipients
    cbpp_matched_cost = pe_cost * new_beneficiary_scale
    benefit_amount_scale = oact_annual_cost / cbpp_matched_cost

    rows = [
        {
            "scenario": "policyengine_raw",
            "new_recipients": pe_new_recipients,
            "annual_ssi_cost": pe_cost,
            "average_cost_per_new_recipient": pe_average_cost,
            "new_beneficiary_scale": 1.0,
            "benefit_amount_scale": 1.0,
        },
        {
            "scenario": "cbpp_new_beneficiary_matched",
            "new_recipients": cbpp_new_beneficiaries,
            "annual_ssi_cost": cbpp_matched_cost,
            "average_cost_per_new_recipient": pe_average_cost,
            "new_beneficiary_scale": new_beneficiary_scale,
            "benefit_amount_scale": 1.0,
        },
        {
            "scenario": "cbpp_new_beneficiary_and_oact_cost_matched",
            "new_recipients": cbpp_new_beneficiaries,
            "annual_ssi_cost": oact_annual_cost,
            "average_cost_per_new_recipient": (
                oact_annual_cost / cbpp_new_beneficiaries
            ),
            "new_beneficiary_scale": new_beneficiary_scale,
            "benefit_amount_scale": benefit_amount_scale,
        },
    ]
    return pd.DataFrame(rows)
