import json

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ssi_asset_limits.admin_checks import FINGERPRINT_FILE, run_fingerprint
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


def test_poverty_rates_count_people_not_households():
    persons, households = toy_frames()
    rows = scenario_summary(persons, households, "ten_twenty")
    # Household 10 has two people who leave poverty; the population is 260
    # people in 160 weighted households.
    assert metric(rows, "poverty_rate_reduction") == pytest.approx(200 / 260)
    assert metric(rows, "deep_poverty_rate_reduction") == 0
    no_limit = scenario_summary(persons, households, "no_limit")
    assert metric(no_limit, "poverty_rate_reduction") == pytest.approx(
        250 / 260
    )
    assert metric(no_limit, "deep_poverty_rate_reduction") == pytest.approx(
        50 / 260
    )


@pytest.mark.parametrize("value", [0.5, "False"])
def test_publisher_refuses_poverty_flags_that_are_not_true_or_false(value):
    persons, households = toy_frames()
    persons["in_poverty_ten_twenty"] = persons["in_poverty_ten_twenty"].astype(
        object
    )
    persons.loc[0, "in_poverty_ten_twenty"] = value
    with pytest.raises(ValueError, match="in_poverty_ten_twenty"):
        scenario_summary(persons, households, "ten_twenty")


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
    """People grouped into households of one or more, sharing its weight."""

    n = draw(st.integers(min_value=1, max_value=40))
    floats = st.floats(min_value=0, max_value=20_000, allow_nan=False)
    membership = draw(st.lists(st.integers(0, n - 1), min_size=n, max_size=n))
    household_of = pd.factorize(pd.Series(membership))[0]
    count = int(household_of.max()) + 1
    household_weight = np.array(
        draw(
            st.lists(
                st.floats(min_value=0.1, max_value=1e4),
                min_size=count,
                max_size=count,
            )
        )
    )
    persons = pd.DataFrame(
        {
            "person_id": np.arange(n),
            "household_id": household_of,
            "person_weight": household_weight[household_of],
            "age": draw(st.lists(st.integers(0, 90), min_size=n, max_size=n)),
            "ssi_countable_resources": draw(
                st.lists(floats, min_size=n, max_size=n)
            ),
        }
    )
    for key in KEYS:
        persons[f"ssi_{key}"] = draw(st.lists(floats, min_size=n, max_size=n))
        persons[f"in_poverty_{key}"] = draw(
            st.lists(st.booleans(), min_size=n, max_size=n)
        )
        persons[f"in_deep_poverty_{key}"] = persons[
            f"in_poverty_{key}"
        ] & np.array(draw(st.lists(st.booleans(), min_size=n, max_size=n)))
    households = pd.DataFrame(
        {
            "household_id": np.arange(count),
            "household_weight": household_weight,
        }
    )
    for key in KEYS:
        households[f"household_net_income_{key}"] = (
            persons.groupby("household_id")[f"ssi_{key}"]
            .sum()
            .reindex(households["household_id"])
            .to_numpy()
        )
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
        # Poverty rates are shares of people, not of households.
        for flag, name in (
            ("in_poverty", "poverty_rate_reduction"),
            ("in_deep_poverty", "deep_poverty_rate_reduction"),
        ):
            before = float(w[persons[f"{flag}_baseline"]].sum())
            after = float(w[persons[f"{flag}_{spec.key}"]].sum())
            assert metric(summary, name) == pytest.approx(
                (before - after) / float(w.sum()), rel=1e-9, abs=1e-12
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


def test_held_out_checks_are_embedded_when_given(tmp_path):
    persons, households = toy_frames()
    run = tmp_path / "run"
    run.mkdir()
    persons.to_csv(run / "persons.csv.gz", index=False)
    households.to_csv(run / "households.csv.gz", index=False)
    (run / "run_metadata.json").write_text(
        json.dumps({"provenance": {"analysis_year": 2026}})
    )
    checks = tmp_path / "checks"
    checks.mkdir()
    pd.DataFrame(
        {
            "age_band": ["60-64"],
            "policyengine_recipients": [92_000.0],
            "policyengine_share_pct": [1.5],
            "ssa_share_pct": [10.5],
            "ssa_recipients": [779_505.0],
        }
    ).to_csv(checks / "recipients_by_fine_age.csv", index=False)
    pd.DataFrame(
        {
            "age_band": ["65 or older"],
            "policyengine_share_pct": [16.1],
            "ssa_share_pct": [57.1],
            "extra": [1],
        }
    ).to_csv(checks / "recipients_with_social_security.csv", index=False)
    pd.DataFrame(
        {
            "marital_status": ["No spouse"],
            "ssa_category": ["No spouse"],
            "policyengine_share_pct": [78.5],
            "ssa_share_pct": [91.8],
        }
    ).to_csv(checks / "recipients_by_marital_status.csv", index=False)
    pd.DataFrame(
        {
            "scenario": ["ten_twenty"],
            "age_band": ["18-64"],
            "recipients": [153_211.0],
            "reporting_ssi_in_cps": [23_345.0],
            "share_pct": [15.2],
        }
    ).to_csv(checks / "new_recipients_by_reporting.csv", index=False)
    pd.DataFrame(
        {
            "scenario": ["ten_twenty"],
            "age_band": ["All ages"],
            "new_recipients": [515_839.0],
            "with_spouse": [349_739.0],
            "share_pct": [67.8],
        }
    ).to_csv(checks / "new_recipients_by_marital_status.csv", index=False)
    pd.DataFrame(
        {
            "measure": ["Under 18 and aged, blind or disabled"],
            "records": [98],
            "weighted": [307_319.0],
        }
    ).to_csv(checks / "children.csv", index=False)
    pd.DataFrame(
        {
            "scenario": ["ten_twenty"],
            "age_band": ["65 or older"],
            "new_recipients": [362_628.0],
            "with_erased_social_security": [195_000.0],
            "share_pct": [53.8],
            "records": [41],
            "median_reported_social_security": [24_111.0],
        }
    ).to_csv(
        checks / "new_recipients_with_erased_social_security.csv", index=False
    )
    persons[["person_id"]].to_csv(
        run / "persons_diagnostics.csv.gz", index=False
    )
    chunk = tmp_path / "chunk_0000.h5"
    chunk.write_bytes(b"chunk")
    (run / "run_metadata.json").write_text(
        json.dumps(
            {
                "provenance": {"analysis_year": 2026},
                "diagnostics": {"chunk_paths": [str(chunk)]},
            }
        )
    )
    (checks / FINGERPRINT_FILE).write_text(json.dumps(run_fingerprint(run)))
    results = publish(run, tmp_path / "out", checks_dir=checks)
    tables = results["held_out_checks"]
    assert tables["recipients_by_fine_age"] == [
        {
            "age_band": "60-64",
            "policyengine_recipients": 92_000.0,
            "ssa_recipients": 779_505.0,
        }
    ]
    assert "extra" not in tables["recipients_with_social_security"][0]
    assert "held_out_checks" not in publish(run, tmp_path / "out2")
    # Tables from a different run, or from different chunks, are refused.
    chunk.write_bytes(b"other chunk")
    with pytest.raises(ValueError, match="different run"):
        publish(run, tmp_path / "out4", checks_dir=checks)
    chunk.write_bytes(b"chunk")
    persons.assign(age=persons["age"] + 1).to_csv(
        run / "persons.csv.gz", index=False
    )
    with pytest.raises(ValueError, match="different run"):
        publish(run, tmp_path / "out3", checks_dir=checks)


PROVENANCE = {
    "analysis_year": 2026,
    "dataset_sha256": "abc",
    "dataset_build_id": "build",
    "model_version": "2.2.1",
    "code_commit": "c0ffee",
    "generated_at": "2026-10-10T00:00:00+00:00",
    "method_note": "The run's own note.",
}


def write_run(path, persons, households, variant=None, **overrides):
    path.mkdir()
    persons.to_csv(path / "persons.csv.gz", index=False)
    households.to_csv(path / "households.csv.gz", index=False)
    diagnostics = {}
    if variant is not None:
        diagnostics = {
            "variant": variant,
            "candidate": {"households": 3_566},
            "variant_source_sha256": "f00d",
        }
    (path / "run_metadata.json").write_text(
        json.dumps(
            {
                "provenance": {**PROVENANCE, **overrides},
                "diagnostics": diagnostics,
            }
        )
    )


def test_sensitivity_runs_are_summarised_beside_the_estimate(tmp_path):
    persons, households = toy_frames()
    write_run(tmp_path / "run", persons, households)
    restored = persons.assign(ssi_ten_twenty=persons["ssi_baseline"])
    write_run(
        tmp_path / "restored",
        restored,
        households,
        "restore_cps_social_security",
        code_commit="beef",
    )
    results = publish(
        tmp_path / "run",
        tmp_path / "out",
        sensitivity_dirs=[tmp_path / "restored"],
    )
    (sens,) = results["sensitivities"]
    assert sens["key"] == "restore_cps_social_security"
    by_age = {
        row["age_group"]: row
        for row in next(
            s for s in sens["scenarios"] if s["key"] == "no_limit"
        )["by_age"]
    }
    # Persons 1 (70) and 3 (30) are new under removal.
    assert by_age["elderly_65_plus"]["new_recipient_records"] == 1
    assert by_age["total_all_ages"]["new_recipient_records"] == 2
    assert "3,566 households" in sens["description"]
    assert sens["provenance"]["code_commit"] == "beef"
    assert sens["provenance"]["variant_source_sha256"] == "f00d"
    ten = next(s for s in sens["scenarios"] if s["key"] == "ten_twenty")
    total = next(
        r for r in ten["by_age"] if r["age_group"] == "total_all_ages"
    )
    assert total["new_recipients"] == 0
    main_total = next(
        r
        for r in results["scenarios"][0]["by_age"]
        if r["age_group"] == "total_all_ages"
    )
    assert main_total["new_recipients"] == pytest.approx(100)
    # The run's own method note stays in run_metadata.json.
    assert "method_note" not in results["provenance"]
    assert results["population"] == {
        "households": 3,
        "persons": 4,
        # Weights 100, 50, 10: the two largest hold 93.75 percent.
        "households_with_99pct_of_weight": 3,
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"dataset_sha256": "other"}, "dataset_sha256"),
        ({"model_version": "2.38.1"}, "model_version"),
        ("people", "different people"),
        ("weights", "different person weights"),
        ("swapped", "different person weights"),
    ],
)
def test_sensitivity_runs_must_share_the_published_population(
    tmp_path, change, message
):
    persons, households = toy_frames()
    write_run(tmp_path / "run", persons, households)
    other = persons
    overrides = {}
    if change == "people":
        other = persons.assign(person_id=persons["person_id"] + 100)
    elif change == "weights":
        other = persons.assign(person_weight=persons["person_weight"] * 1.01)
    elif change == "swapped":
        # Same total, but two people trade weights.
        swapped = persons["person_weight"].to_numpy().copy()
        swapped[[2, 3]] = swapped[[3, 2]]
        other = persons.assign(person_weight=swapped)
    else:
        overrides = change
    write_run(
        tmp_path / "variant",
        other,
        households,
        "resource_deeming",
        **overrides,
    )
    with pytest.raises(ValueError, match=message):
        publish(
            tmp_path / "run",
            tmp_path / "out",
            sensitivity_dirs=[tmp_path / "variant"],
        )


def test_a_spliced_rerun_may_change_only_the_households_it_reran(tmp_path):
    persons, households = toy_frames()
    write_run(tmp_path / "run", persons, households)
    # The restore rerun reran one household (candidate count 3,566 in the
    # helper); shrink that to 1 and change two households.
    changed = persons.assign(
        ssi_no_limit=persons["ssi_no_limit"] + [1.0, 0.0, 1.0, 0.0]
    )
    write_run(
        tmp_path / "restored",
        changed,
        households,
        "restore_cps_social_security",
    )
    metadata_path = tmp_path / "restored" / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["diagnostics"]["candidate"]["households"] = 1
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="changes 2 households"):
        publish(
            tmp_path / "run",
            tmp_path / "out",
            sensitivity_dirs=[tmp_path / "restored"],
        )
    metadata["diagnostics"]["candidate"]["households"] = 2
    metadata_path.write_text(json.dumps(metadata))
    publish(
        tmp_path / "run",
        tmp_path / "out2",
        sensitivity_dirs=[tmp_path / "restored"],
    )
