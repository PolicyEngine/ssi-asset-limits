import json

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ssi_asset_limits.comparators import OACT_LETTERS
from ssi_asset_limits.publish import (
    SCENARIOS,
    baseline_by_age,
    build_results,
    publish,
    scenario_by_age,
    scenario_resource_bins,
    scenario_summary,
)

KEYS = ["baseline"] + [spec.key for spec in SCENARIOS]


def toy_frames():
    """Four people in three households, values chosen to hand-check."""

    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "household_id": [10, 10, 20, 30],
            "person_weight": [100.0, 100.0, 50.0, 10.0],
            "age": [70, 68, 30, 10],
            "ssi_countable_resources": [5_000.0, 0.0, 15_000.0, 0.0],
            "ssi_baseline": [0.0, 0.0, 0.0, 6_000.0],
            "ssi_ten_twenty": [4_000.0, 0.0, 0.0, 6_000.0],
            "ssi_no_limit": [4_000.0, 0.0, 8_000.0, 6_000.0],
            "in_poverty_baseline": [True, True, True, False],
            "in_poverty_ten_twenty": [False, False, True, False],
            "in_poverty_no_limit": [False, False, False, False],
            "in_deep_poverty_baseline": [False, False, True, False],
            "in_deep_poverty_ten_twenty": [False, False, True, False],
            "in_deep_poverty_no_limit": [False, False, False, False],
        }
    )
    households = pd.DataFrame(
        {
            "household_id": [10, 20, 30],
            "household_weight": [100.0, 50.0, 10.0],
        }
    )
    for key in KEYS:
        bump = {"baseline": 0.0, "ten_twenty": 4_000.0, "no_limit": 4_000.0}
        households[f"household_net_income_{key}"] = [
            20_000.0 + bump[key],
            30_000.0 + (8_000.0 if key == "no_limit" else 0.0),
            9_000.0,
        ]
        households[f"snap_{key}"] = [
            1_000.0 - (500.0 if key != "baseline" else 0.0),
            0.0,
            0.0,
        ]
        households[f"income_tax_{key}"] = [0.0, 0.0, 0.0]
    return persons, households


def metric(rows, key):
    return next(row["value"] for row in rows if row["metric"] == key)


def test_summary_hand_checked():
    persons, households = toy_frames()
    rows = scenario_summary(persons, households, "ten_twenty")
    # Person 1 gains $4,000 at weight 100.
    assert metric(rows, "annual_ssi_cost") == pytest.approx(400_000)
    assert metric(rows, "new_recipients") == pytest.approx(100)
    assert metric(rows, "average_gain") == pytest.approx(4_000)
    # Persons 1 and 2 leave poverty (weight 100 each).
    assert metric(rows, "people_lifted_from_poverty") == pytest.approx(200)
    assert metric(rows, "baseline_recipients") == pytest.approx(10)
    assert metric(rows, "reform_recipients") == pytest.approx(110)
    assert metric(rows, "net_fiscal_cost") == pytest.approx(400_000)
    assert metric(rows, "snap_change") == pytest.approx(-50_000)


def test_by_age_hand_checked():
    persons, _ = toy_frames()
    rows = {r["age_group"]: r for r in scenario_by_age(persons, "no_limit")}
    assert rows["elderly_65_plus"]["new_recipients"] == pytest.approx(100)
    assert rows["adults_18_64"]["new_recipients"] == pytest.approx(50)
    assert rows["children_under_18"]["new_recipients"] == 0
    assert rows["adults_18_64"]["annual_ssi_cost"] == pytest.approx(400_000)
    assert rows["total_all_ages"]["cbpp_new_beneficiaries"] == 462_000
    ten = {r["age_group"]: r for r in scenario_by_age(persons, "ten_twenty")}
    assert ten["elderly_65_plus"]["cbpp_new_beneficiaries"] is None
    assert "not publish" in ten["elderly_65_plus"]["cbpp_note"]


def test_baseline_by_age_uses_ssa_federal_payment_counts():
    persons, _ = toy_frames()
    result = baseline_by_age(persons)
    by_group = {r["age_group"]: r for r in result["by_age"]}
    assert by_group["children_under_18"]["policyengine_recipients"] == 10
    assert by_group["elderly_65_plus"]["ssa_recipients"] == 2_382_142
    assert sum(r["ssa_recipients"] for r in result["by_age"]) == 7_289_843


def test_oact_letters_sum_to_their_totals_within_rounding():
    for letter in OACT_LETTERS:
        annual = sum(v for v in letter["annual"].values() if v is not None)
        # Annual figures are rounded to $0.1 billion; allow for that.
        assert annual == pytest.approx(letter["total_billions"], abs=0.15)


def test_publish_round_trip(tmp_path):
    persons, households = toy_frames()
    run = tmp_path / "run"
    run.mkdir()
    persons.to_csv(run / "persons.csv.gz", index=False)
    households.to_csv(run / "households.csv.gz", index=False)
    (run / "run_metadata.json").write_text(
        json.dumps({"provenance": {"analysis_year": 2026}})
    )
    out = tmp_path / "out"
    results = publish(run, out)
    written = json.loads((out / "results.json").read_text())
    assert written == json.loads(json.dumps(results))
    assert (out / "ten_twenty_by_age.csv").exists()
    assert [s["key"] for s in written["scenarios"]] == [
        "ten_twenty",
        "no_limit",
    ]


@st.composite
def populations(draw):
    n = draw(st.integers(min_value=1, max_value=40))
    floats = st.floats(min_value=0, max_value=20_000, allow_nan=False)
    persons = pd.DataFrame(
        {
            "person_id": np.arange(n),
            "household_id": np.arange(n),
            "person_weight": draw(
                st.lists(
                    st.floats(min_value=0.1, max_value=1e4),
                    min_size=n,
                    max_size=n,
                )
            ),
            "age": draw(st.lists(st.integers(0, 90), min_size=n, max_size=n)),
            "ssi_countable_resources": draw(
                st.lists(floats, min_size=n, max_size=n)
            ),
        }
    )
    for key in KEYS:
        persons[f"ssi_{key}"] = draw(st.lists(floats, min_size=n, max_size=n))
        flags = draw(st.lists(st.booleans(), min_size=n, max_size=n))
        persons[f"in_poverty_{key}"] = flags
        persons[f"in_deep_poverty_{key}"] = flags
    households = pd.DataFrame(
        {
            "household_id": persons["household_id"],
            "household_weight": persons["person_weight"],
        }
    )
    for key in KEYS:
        households[f"household_net_income_{key}"] = persons[f"ssi_{key}"]
        households[f"snap_{key}"] = 0.0
        households[f"income_tax_{key}"] = 0.0
    return persons, households


@settings(max_examples=150, deadline=None)
@given(populations())
def test_accounting_identities(frames):
    persons, households = frames
    for spec in SCENARIOS:
        summary = scenario_summary(persons, households, spec.key)
        by_age = {
            r["age_group"]: r for r in scenario_by_age(persons, spec.key)
        }
        groups = ["children_under_18", "adults_18_64", "elderly_65_plus"]
        total = metric(summary, "annual_ssi_cost")
        # Age groups partition people: their parts add to the totals.
        assert sum(
            by_age[g]["annual_ssi_cost"] for g in groups
        ) == pytest.approx(total, rel=1e-9, abs=1e-6)
        assert sum(
            by_age[g]["new_recipients"] for g in groups
        ) == pytest.approx(
            metric(summary, "new_recipients"), rel=1e-9, abs=1e-9
        )
        # Resource bins partition people with non-negative resources.
        bins = scenario_resource_bins(persons, spec.key)
        assert sum(b["ssi_increase"] for b in bins) == pytest.approx(
            total, rel=1e-9, abs=1e-6
        )
        assert sum(b["people"] for b in bins) == pytest.approx(
            persons["person_weight"].sum(), rel=1e-9
        )
        # Recipients after = before + new - those who stop receiving.
        w = persons["person_weight"]
        lost = (persons["ssi_baseline"] > 0) & (
            persons[f"ssi_{spec.key}"] <= 0
        )
        assert metric(summary, "reform_recipients") == pytest.approx(
            metric(summary, "baseline_recipients")
            + metric(summary, "new_recipients")
            - float(w[lost].sum()),
            rel=1e-9,
            abs=1e-6,
        )
        # Household net income here equals SSI, so the two changes agree.
        assert metric(summary, "net_fiscal_cost") == pytest.approx(
            total, rel=1e-9, abs=1e-6
        )


@settings(max_examples=60, deadline=None)
@given(populations(), st.floats(min_value=0.5, max_value=20))
def test_weight_scaling(frames, factor):
    persons, households = frames
    scaled_p = persons.assign(person_weight=persons["person_weight"] * factor)
    scaled_h = households.assign(
        household_weight=households["household_weight"] * factor
    )
    for spec in SCENARIOS:
        a = scenario_summary(persons, households, spec.key)
        b = scenario_summary(scaled_p, scaled_h, spec.key)
        for row_a, row_b in zip(a, b):
            if row_a["metric"] in {
                "average_gain",
                "poverty_rate_reduction",
                "deep_poverty_rate_reduction",
            }:
                assert row_b["value"] == pytest.approx(
                    row_a["value"], rel=1e-9, abs=1e-9
                )
            else:
                assert row_b["value"] == pytest.approx(
                    row_a["value"] * factor, rel=1e-9, abs=1e-6
                )


def test_no_change_reform_publishes_zero_deltas():
    persons, households = toy_frames()
    for key in ("ten_twenty", "no_limit"):
        persons[f"ssi_{key}"] = persons["ssi_baseline"]
        households[f"household_net_income_{key}"] = households[
            "household_net_income_baseline"
        ]
        households[f"snap_{key}"] = households["snap_baseline"]
        persons[f"in_poverty_{key}"] = persons["in_poverty_baseline"]
        persons[f"in_deep_poverty_{key}"] = persons["in_deep_poverty_baseline"]
    results = build_results(persons, households, {"provenance": {}})
    for scenario in results["scenarios"]:
        for row in scenario["summary"]:
            if row["metric"] not in {
                "baseline_recipients",
                "reform_recipients",
            }:
                assert row["value"] == 0


def test_sensitivity_runs_cannot_be_published_as_the_estimate(tmp_path):
    persons, households = toy_frames()
    run = tmp_path / "run"
    run.mkdir()
    persons.to_csv(run / "persons.csv.gz", index=False)
    households.to_csv(run / "households.csv.gz", index=False)
    (run / "run_metadata.json").write_text(
        json.dumps(
            {
                "provenance": {"analysis_year": 2026},
                "diagnostics": {"variant": "resource_deeming"},
            }
        )
    )
    with pytest.raises(ValueError, match="sensitivity run"):
        publish(run, tmp_path / "out")
    results = publish(run, tmp_path / "variant-out", allow_variant=True)
    assert [s["key"] for s in results["scenarios"]] == [
        "ten_twenty",
        "no_limit",
    ]
