import json

import pandas as pd
import pytest

from ssi_asset_limits.microcosm_checks import (
    _aligned_diagnostics,
    baseline_checks,
    chunking_checks,
    frame_checks,
    monotonicity_checks,
    reform_checks,
    write_checks,
)


def frames():
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5],
            "household_id": [10, 10, 20, 30, 30],
            "person_weight": [100.0, 100.0, 50.0, 10.0, 10.0],
            "age": [10, 16, 30, 68, 70],
            "ssi_countable_resources": [0, 0, 15_000, 5_000, 0],
            "ssi_baseline": [6_000, 0, 6_000, 8_000, 0],
            "ssi_ten_twenty": [6_000, 0, 6_000, 6_000, 6_000],
            "ssi_no_limit": [6_000, 0, 8_000, 6_000, 6_000],
        }
    )
    households = pd.DataFrame(
        {
            "household_id": [10, 20, 30],
            "household_weight": [100.0, 50.0, 10.0],
        }
    )
    diagnostics = pd.DataFrame(
        {
            "person_id": persons["person_id"],
            "marital_unit_id": [1, 2, 3, 4, 4],
            "is_disabled": [True, False, True, False, False],
            "meets_ssi_disability_criteria": [
                False,
                False,
                True,
                False,
                False,
            ],
        }
    )
    for scenario in ("baseline", "ten_twenty", "no_limit"):
        diagnostics[f"is_ssi_aged_blind_disabled_{scenario}"] = [
            True,
            False,
            True,
            True,
            True,
        ]
        diagnostics[f"takes_up_ssi_if_eligible_{scenario}"] = [
            True,
            False,
            True,
            True,
            True,
        ]
        diagnostics[f"is_ssi_eligible_{scenario}"] = [
            True,
            False,
            True,
            True,
            scenario != "baseline",
        ]
    return persons, households, diagnostics


def metadata():
    return {
        "provenance": {"analysis_year": 2026},
        "diagnostics": {
            "nesting": {"marital_unit": {"all_nested": True, "units": 4}},
            "full_weight_totals": {"person": 270.0, "household": 160.0},
            "summed_chunk_weight_totals": {
                "person": 270.000000001,
                "household": 160.0,
            },
        },
    }


def test_baseline_reports_unrounded_totals_and_reference_flags():
    persons, _, _ = frames()
    report = baseline_checks(persons)
    counts = report["recipients"]
    assert counts["under_18"]["against_ssa"]["value"] == 100
    assert counts["18_64"]["against_ssa"]["value"] == 50
    assert counts["65_plus"]["against_ssa"]["value"] == 10
    assert counts["total"]["against_ssa"]["value"] == 160
    assert counts["total"]["against_ssa"]["reference"] == 7_289_843
    assert counts["under_18"]["against_ssa"]["more_than_10_percent_off"]
    annual = report["annual_federal_ssi"]
    assert annual["against_ssa"]["value"] == 980_000
    assert annual["against_ssa"]["reference"] == 62_760_000_000


def test_reform_deltas_are_net_of_losses_and_partition_by_age():
    persons, _, _ = frames()
    report = reform_checks(persons)
    assert report["ten_twenty"]["annual_ssi_change"]["value"] == 40_000
    assert report["no_limit"]["annual_ssi_change"]["value"] == 140_000
    assert report["ten_twenty"]["new_recipients"]["value"] == 10
    for scenario in report.values():
        rows = scenario["by_age"].values()
        assert sum(r["annual_ssi_change"] for r in rows) == pytest.approx(
            scenario["annual_ssi_change"]["value"]
        )
        assert sum(r["new_recipients"] for r in rows) == pytest.approx(
            scenario["new_recipients"]["value"]
        )
    children = report["ten_twenty"]["by_age"]["under_18"]
    comparison = children["new_recipients_against_july_build_p"]
    assert comparison["relative_difference"] is None
    assert not comparison["more_than_10_percent_off"]


def test_frame_rates_use_weighted_person_and_household_denominators():
    persons, households, diagnostics = frames()
    report = frame_checks(persons, households, diagnostics)
    assert report["weighted_zero_countable_resources_share"] == pytest.approx(
        210 / 270
    )
    distribution = report["nonzero_resources_per_household"]
    assert distribution[0]["persons_with_nonzero_resources"] == 0
    assert distribution[0]["weighted_household_share"] == pytest.approx(
        100 / 160
    )
    assert distribution[1]["weighted_households"] == 60
    assert report["at_most_one_person_with_nonzero_resources_per_household"]
    disability = report["disability_by_age"]
    assert disability[0]["is_disabled_rate"] == 1
    assert disability[0]["meets_ssi_disability_criteria_rate"] == 0
    assert disability[1]["is_disabled_rate"] == 0
    assert disability[2]["meets_ssi_disability_criteria_rate"] == 1
    takeup = report["takes_up_ssi_if_eligible_by_age"]["baseline"]
    assert takeup[0]["overall_true_rate"] == 0.5
    assert takeup[0]["baseline_eligible_true_rate"] == 1
    assert takeup[0]["weighted_baseline_eligible_persons"] == 100
    abd = report["abd_persons_by_age"]["baseline"]
    assert [row["weighted_abd_persons"] for row in abd] == [100, 50, 20]


def test_resource_distribution_flags_multiple_nonzero_people():
    persons, households, diagnostics = frames()
    persons.loc[4, "ssi_countable_resources"] = 1
    report = frame_checks(persons, households, diagnostics)
    assert not report[
        "at_most_one_person_with_nonzero_resources_per_household"
    ]
    assert report["maximum_persons_per_household_with_nonzero_resources"] == 2
    assert report["nonzero_resources_per_household"][2]["households"] == 1


def test_missing_age_population_has_null_rate():
    persons, households, diagnostics = frames()
    persons["age"] = 70
    report = frame_checks(persons, households, diagnostics)
    assert report["disability_by_age"][0]["is_disabled_rate"] is None
    assert (
        report["takes_up_ssi_if_eligible_by_age"]["baseline"][0][
            "baseline_eligible_true_rate"
        ]
        is None
    )


def test_diagnostics_are_aligned_by_person_not_row_order():
    persons, _, diagnostics = frames()
    reversed_diagnostics = diagnostics.iloc[::-1]
    aligned = _aligned_diagnostics(persons, reversed_diagnostics)
    pd.testing.assert_frame_equal(aligned, diagnostics)
    with pytest.raises(ValueError, match="duplicate person_id"):
        _aligned_diagnostics(persons, pd.concat([diagnostics, diagnostics]))
    with pytest.raises(ValueError, match="different persons"):
        _aligned_diagnostics(persons, diagnostics.iloc[:-1])


def test_nonboolean_diagnostic_fails_instead_of_treating_text_as_true():
    persons, households, diagnostics = frames()
    diagnostics["is_disabled"] = "False"
    with pytest.raises(ValueError, match="must contain booleans"):
        frame_checks(persons, households, diagnostics)


def test_january_snapshot_is_used_when_monthly_flags_have_annual_fractions():
    persons, households, diagnostics = frames()
    for scenario in ("baseline", "ten_twenty", "no_limit"):
        column = f"is_ssi_eligible_{scenario}"
        diagnostics[f"{column}_january"] = diagnostics[column]
        diagnostics[column] = 0.5
    report = frame_checks(persons, households, diagnostics)
    assert (
        report["takes_up_ssi_if_eligible_by_age"]["baseline"][0][
            "baseline_eligible_true_rate"
        ]
        == 1
    )


def test_chunking_weight_check_accepts_floating_point_sum_tolerance():
    report = chunking_checks(metadata())
    assert report["weight_totals"]["person"][
        "equal_within_floating_point_tolerance"
    ]
    changed = metadata()
    changed["diagnostics"]["summed_chunk_weight_totals"]["person"] += 1
    assert not chunking_checks(changed)["weight_totals"]["person"][
        "equal_within_floating_point_tolerance"
    ]


def test_monotonicity_does_not_infer_couple_effect_from_new_spouse_alone():
    persons, _, diagnostics = frames()
    report, cases = monotonicity_checks(persons, diagnostics)
    for scenario in ("ten_twenty", "no_limit"):
        row = report["scenarios"][scenario]
        assert row["person_rows_with_ssi_decline"] == 1
        assert row["weighted_persons_with_ssi_decline"] == 10
        assert row["annual_ssi_loss"] == 20_000
        assert row["unexplained_person_rows"] == 1
        assert row["unexplained_person_ids_first_20"] == [4]
    assert set(cases["cause"]) == {"unexplained"}
    assert set(cases["marital_unit_baseline_eligible_persons"]) == {1}
    assert set(cases["marital_unit_reform_eligible_persons"]) == {2}


def test_monotonicity_couple_cause_requires_recorded_transition_and_identity():
    persons, _, diagnostics = frames()
    for scenario in ("baseline", "ten_twenty", "no_limit"):
        diagnostics[f"ssi_couple_computation_applies_{scenario}"] = False
        diagnostics[f"is_ssi_spousal_deeming_applies_{scenario}"] = False
        diagnostics[f"ssi_amount_if_eligible_{scenario}"] = 12_000.0
        diagnostics[f"ssi_countable_income_{scenario}"] = 4_000.0
    for scenario in ("ten_twenty", "no_limit"):
        diagnostics.loc[3, f"ssi_couple_computation_applies_{scenario}"] = True
        diagnostics.loc[3, f"ssi_amount_if_eligible_{scenario}"] = 9_000
        diagnostics.loc[3, f"ssi_countable_income_{scenario}"] = 3_000
    report, cases = monotonicity_checks(persons, diagnostics)
    assert set(cases["cause"]) == {
        "spouse_eligible_and_couple_computation_started"
    }
    assert report["scenarios"]["ten_twenty"]["unexplained_person_rows"] == 0
    diagnostics.loc[3, "ssi_countable_income_ten_twenty"] = 1_000
    report, cases = monotonicity_checks(persons, diagnostics)
    assert report["scenarios"]["ten_twenty"]["unexplained_person_rows"] == 1
    assert cases.loc[cases["scenario"] == "ten_twenty", "cause"].iloc[0] == (
        "unexplained"
    )


def test_countable_income_identity_still_flags_source_investigation():
    persons, _, diagnostics = frames()
    for scenario in ("baseline", "ten_twenty", "no_limit"):
        diagnostics[f"ssi_couple_computation_applies_{scenario}"] = True
        diagnostics[f"is_ssi_spousal_deeming_applies_{scenario}"] = False
        diagnostics[f"ssi_amount_if_eligible_{scenario}"] = 10_000.0
        diagnostics[f"ssi_countable_income_{scenario}"] = 2_000.0
    for scenario in ("ten_twenty", "no_limit"):
        diagnostics.loc[3, f"ssi_countable_income_{scenario}"] = 4_000
    report, cases = monotonicity_checks(persons, diagnostics)
    assert set(cases["cause"]) == {"recorded_countable_income_increase"}
    assert (
        report["scenarios"]["ten_twenty"][
            "person_rows_needing_mechanism_investigation"
        ]
        == 1
    )


def test_monotonicity_no_loss_outputs_empty_case_file_schema():
    persons, _, diagnostics = frames()
    persons["ssi_ten_twenty"] = persons["ssi_baseline"]
    persons["ssi_no_limit"] = persons["ssi_baseline"]
    report, cases = monotonicity_checks(persons, diagnostics)
    assert cases.empty
    assert "marital_unit_id" in cases
    for scenario in report["scenarios"].values():
        assert scenario["all_ssi_changes_nonnegative"]
        assert scenario["person_rows_with_ssi_decline"] == 0
        assert scenario["annual_ssi_loss"] == 0


def test_saved_checks_roundtrip(tmp_path):
    persons, households, diagnostics = frames()
    persons.to_csv(tmp_path / "persons.csv.gz", index=False)
    households.to_csv(tmp_path / "households.csv.gz", index=False)
    diagnostics.to_csv(tmp_path / "persons_diagnostics.csv.gz", index=False)
    (tmp_path / "run_metadata.json").write_text(json.dumps(metadata()))
    report = write_checks(tmp_path)
    saved = json.loads((tmp_path / "checks.json").read_text())
    assert saved == report
    text = (tmp_path / "checks.txt").read_text()
    assert "A total: 160 recipients" in text
    assert "E ten_twenty SSI declines: 1 person rows" in text
    assert (tmp_path / "monotonicity_cases.csv.gz").exists()
    assert saved["B_reform_deltas"]["no_limit"]["annual_ssi_change"][
        "value"
    ] == (140_000)
