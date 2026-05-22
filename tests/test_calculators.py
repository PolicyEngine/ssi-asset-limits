import pandas as pd

from ssi_asset_limits.calculators import (
    calculate_national_summary,
    calculate_resource_bins,
)


class FakeSimulation:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def calc(self, variable, **kwargs):
        self.calls.append((variable, kwargs))
        return self.values[variable]


def test_national_summary_scores_ssi_asset_limit_removal():
    baseline = FakeSimulation(
        {
            "ssi": pd.Series([1_000, 0, 0, 500]),
            "person_in_poverty": pd.Series([True, True, False, True]),
            "in_deep_poverty": pd.Series([False, True, False, True]),
        }
    )
    reformed = FakeSimulation(
        {
            "ssi": pd.Series([1_000, 2_000, 0, 800]),
            "person_in_poverty": pd.Series([True, False, False, True]),
            "in_deep_poverty": pd.Series([False, False, False, True]),
        }
    )

    summary = calculate_national_summary(baseline, reformed, 2026)
    values = summary.set_index("metric")["value"].to_dict()

    assert values["annual_ssi_cost"] == 2_300
    assert values["baseline_recipients"] == 2
    assert values["reform_recipients"] == 3
    assert values["new_recipients"] == 1
    assert values["people_lifted_from_poverty"] == 1
    assert values["poverty_rate_reduction"] == 0.25
    assert values["deep_poverty_rate_reduction"] == 0.25


def test_national_summary_uses_microseries_calc_without_weight_variables():
    baseline = FakeSimulation(
        {
            "ssi": pd.Series([0]),
            "person_in_poverty": pd.Series([False]),
            "in_deep_poverty": pd.Series([False]),
        }
    )
    reformed = FakeSimulation(
        {
            "ssi": pd.Series([0]),
            "person_in_poverty": pd.Series([False]),
            "in_deep_poverty": pd.Series([False]),
        }
    )

    calculate_national_summary(baseline, reformed, 2026)
    called_variables = [call[0] for call in baseline.calls + reformed.calls]

    assert "household_weight" not in called_variables
    assert "person_weight" not in called_variables
    assert ("person_in_poverty", {"period": 2026, "map_to": "person"}) in (
        baseline.calls
    )


def test_national_summary_can_skip_poverty_metrics():
    baseline = FakeSimulation({"ssi": pd.Series([0, 100])})
    reformed = FakeSimulation({"ssi": pd.Series([200, 100])})

    summary = calculate_national_summary(
        baseline, reformed, 2026, include_poverty=False
    )

    assert set(summary["metric"]) == {
        "annual_ssi_cost",
        "baseline_recipients",
        "reform_recipients",
        "new_recipients",
        "average_gain",
    }
    assert all(call[0] != "person_in_poverty" for call in baseline.calls)
    assert all(call[0] != "in_deep_poverty" for call in reformed.calls)


def test_resource_bins_aggregate_by_countable_resources():
    baseline = FakeSimulation(
        {
            "ssi_countable_resources": pd.Series([500, 2_500, 4_000, 30_000]),
            "ssi": pd.Series([0, 0, 0, 0]),
        }
    )
    reformed = FakeSimulation(
        {
            "ssi": pd.Series([0, 1_000, 2_000, 0]),
        }
    )

    bins = calculate_resource_bins(baseline, reformed, 2026)
    by_bin = bins.set_index("resource_bin")

    assert by_bin.loc["Under $2,000", "people"] == 1
    assert by_bin.loc["$2,000 to $2,999", "ssi_increase"] == 1_000
    assert by_bin.loc["$3,000 to $9,999", "average_gain"] == 2_000
    assert by_bin.loc["$25,000 or more", "ssi_increase"] == 0
