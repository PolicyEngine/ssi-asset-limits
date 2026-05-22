import pandas as pd

from ssi_asset_limits.benchmarks import (
    calculate_external_benchmark_comparison,
)


def test_external_benchmark_comparison_matches_participation_then_cost():
    summary = pd.DataFrame(
        [
            {"metric": "annual_ssi_cost", "value": 10_000},
            {"metric": "new_recipients", "value": 1_000},
        ]
    )

    comparison = calculate_external_benchmark_comparison(
        summary,
        cbpp_new_beneficiaries=200,
        oact_annual_cost=500,
    ).set_index("scenario")

    assert comparison.loc["policyengine_raw", "annual_ssi_cost"] == 10_000
    assert (
        comparison.loc["cbpp_participation_matched", "annual_ssi_cost"]
        == 2_000
    )
    assert (
        comparison.loc[
            "cbpp_participation_and_oact_cost_matched", "annual_ssi_cost"
        ]
        == 500
    )
    assert (
        comparison.loc[
            "cbpp_participation_and_oact_cost_matched",
            "average_cost_per_new_recipient",
        ]
        == 2.5
    )
    assert (
        comparison.loc[
            "cbpp_participation_and_oact_cost_matched",
            "benefit_amount_scale",
        ]
        == 0.25
    )
