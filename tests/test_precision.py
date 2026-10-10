import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ssi_asset_limits.precision import (
    bootstrap_ranges,
    person_contributions,
    record_counts,
    scenario_precision,
)


def frame(n_households=200, seed=1):
    rng = np.random.default_rng(seed)
    persons = pd.DataFrame(
        {
            "person_id": np.arange(n_households),
            "household_id": np.arange(n_households),
            "person_weight": rng.uniform(1, 100, n_households),
            "age": rng.integers(0, 90, n_households),
            "ssi_baseline": 0.0,
        }
    )
    gains = rng.random(n_households) < 0.2
    persons["ssi_ten_twenty"] = np.where(gains, 6_000.0, 0.0)
    return persons


def test_estimate_and_counts_by_hand():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "household_id": [10, 10, 20, 30],
            "person_weight": [100.0, 100.0, 50.0, 10.0],
            "age": [70, 68, 30, 10],
            "ssi_baseline": [0.0, 0.0, 0.0, 6_000.0],
            "ssi_ten_twenty": [4_000.0, 2_000.0, 1_000.0, 6_000.0],
        }
    )
    table = scenario_precision(persons, "ten_twenty").set_index(
        ["statistic", "age_group"]
    )
    elderly = table.loc[("new_recipients", "elderly_65_plus")]
    assert elderly["estimate"] == 200
    assert elderly["records"] == 2
    assert elderly["effective_records"] == pytest.approx(2)
    assert table.loc[("annual_ssi_cost", "total_all_ages"), "estimate"] == (
        100 * 4_000 + 100 * 2_000 + 50 * 1_000
    )
    child = table.loc[("new_recipients", "children_under_18")]
    assert (child["estimate"], child["low"], child["high"]) == (0, 0, 0)
    assert child["records"] == 0
    assert (
        table.loc[("baseline_recipients", "children_under_18"), "records"] == 1
    )


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    persons = frame()
    first = scenario_precision(persons, "ten_twenty")
    second = scenario_precision(persons, "ten_twenty")
    pd.testing.assert_frame_equal(first, second)
    total = first[
        (first.statistic == "new_recipients")
        & (first.age_group == "total_all_ages")
    ].iloc[0]
    assert total["low"] < total["estimate"] < total["high"]


def test_household_members_move_together():
    """Two people in one household are resampled as a unit."""
    contributions = pd.DataFrame({"x": [1.0, 1.0, 1.0, 1.0]})
    together = bootstrap_ranges(contributions, pd.Series([1, 1, 2, 2]))
    apart = bootstrap_ranges(contributions, pd.Series([1, 2, 3, 4]))
    width = lambda r: float(r.loc["x", "high"] - r.loc["x", "low"])  # noqa: E731
    assert width(together) > width(apart)


def test_range_narrows_as_the_sample_grows():
    def relative_width(n):
        table = scenario_precision(frame(n, seed=7), "ten_twenty")
        row = table[
            (table.statistic == "new_recipients")
            & (table.age_group == "total_all_ages")
        ].iloc[0]
        return (row["high"] - row["low"]) / row["estimate"]

    assert relative_width(4_000) < relative_width(400) < relative_width(40)


@settings(max_examples=40, deadline=None)
@given(st.floats(min_value=0.1, max_value=50))
def test_ranges_scale_with_the_weights(factor):
    persons = frame(150, seed=3)
    scaled = persons.assign(person_weight=persons["person_weight"] * factor)
    a = scenario_precision(persons, "ten_twenty")
    b = scenario_precision(scaled, "ten_twenty")
    for column in ("estimate", "low", "high"):
        np.testing.assert_allclose(b[column], a[column] * factor, rtol=1e-9)
    np.testing.assert_allclose(b["effective_records"], a["effective_records"])
    assert (b["records"] == a["records"]).all()


def test_effective_records_never_exceed_records():
    persons = frame(300, seed=5)
    contributions = person_contributions(persons, "ten_twenty")
    counts = record_counts(contributions, persons["person_weight"])
    assert (counts["effective_records"] <= counts["records"] + 1e-9).all()
    assert (counts["effective_records"] >= 0).all()
