import pandas as pd
import pytest

from ssi_asset_limits.cbpp import (
    ADULTS_18_64,
    CBPP_TARGET_ROWS,
    ELDERLY_65_PLUS,
    NO_LIMIT,
    TEN_TWENTY,
    TOTAL_ALL_AGES,
    adult_18_64_participation_index,
    calculate_cbpp_age_bridge,
    cbpp_adult_18_64_coefficients,
    cbpp_age_targets,
    cbpp_public_targets,
    infer_cbpp_scenario_key,
)


def test_cbpp_target_rows_have_expected_shape():
    assert all(len(row) == 6 for row in CBPP_TARGET_ROWS)


def test_cbpp_public_targets_include_ten_twenty_headline():
    targets = cbpp_public_targets()
    row = targets[
        (targets["scenario"] == TEN_TWENTY)
        & (targets["dimension"] == "age")
        & (targets["group"] == TOTAL_ALL_AGES)
    ].iloc[0]

    assert row["new_beneficiaries"] == 224_000
    assert row["percent_change"] == 3
    assert row["status"] == "published"


def test_cbpp_age_targets_infer_unpublished_elderly_residual():
    targets = cbpp_age_targets(TEN_TWENTY).set_index("group")

    assert targets.loc[ELDERLY_65_PLUS, "new_beneficiaries"] == 47_000
    assert (
        targets.loc[ELDERLY_65_PLUS, "status"]
        == "inferred_from_total_minus_published_age_groups"
    )
    assert (
        targets.drop(index=TOTAL_ALL_AGES)["new_beneficiaries"].sum()
        == targets.loc[TOTAL_ALL_AGES, "new_beneficiaries"]
    )


def test_adult_18_64_coefficients_include_cbpp_published_terms():
    coefficients = cbpp_adult_18_64_coefficients().set_index("predictor")

    assert coefficients.loc["log_countable_income", "coefficient"] == 0.18
    assert coefficients.loc["not_us_citizen", "coefficient"] == -0.94
    assert coefficients.loc["full_equation", "status"] == (
        "not_published_by_cbpp"
    )


def test_adult_18_64_participation_index_uses_public_coefficients():
    records = pd.DataFrame(
        [
            {
                "log_countable_income": 1,
                "log_countable_assets": 1,
                "age": 40,
                "prevented_from_work": 1,
                "difficulty_errands_alone": 0,
                "serious_difficulty_walking_or_climbing_stairs": 0,
                "any_six_core_disability_measure": 1,
                "condition_limits_kind_or_amount_work": 1,
                "disability_or_health_condition_income": 0,
                "education_category": 2,
                "married": 1,
                "not_us_citizen": 0,
            }
        ]
    )

    assert adult_18_64_participation_index(records).iloc[0] == pytest.approx(
        1.71
    )


def test_infer_cbpp_scenario_key_rejects_unpublished_limit():
    assert infer_cbpp_scenario_key(10_000, 20_000) == TEN_TWENTY

    with pytest.raises(ValueError):
        infer_cbpp_scenario_key(25_000, 50_000)


def test_cbpp_age_bridge_matches_ten_twenty_total():
    pe_age_impacts = pd.DataFrame(
        [
            {
                "age_group": "children_under_18",
                "policyengine_new_recipients": 100_000,
                "policyengine_annual_ssi_cost": 1_000_000_000,
            },
            {
                "age_group": ADULTS_18_64,
                "policyengine_new_recipients": 500_000,
                "policyengine_annual_ssi_cost": 5_000_000_000,
            },
            {
                "age_group": ELDERLY_65_PLUS,
                "policyengine_new_recipients": 200_000,
                "policyengine_annual_ssi_cost": 1_000_000_000,
            },
        ]
    )

    bridge = calculate_cbpp_age_bridge(pe_age_impacts, TEN_TWENTY).set_index(
        "age_group"
    )

    assert bridge.loc[TOTAL_ALL_AGES, "cbpp_new_beneficiaries"] == 224_000
    assert bridge.loc[ELDERLY_65_PLUS, "cbpp_new_beneficiaries"] == 47_000
    assert bridge.loc[ADULTS_18_64, "new_beneficiary_scale"] == pytest.approx(
        154_000 / 500_000
    )


def test_cbpp_age_bridge_only_applies_oact_cost_to_ten_twenty_by_default():
    pe_age_impacts = pd.DataFrame(
        [
            {
                "age_group": "children_under_18",
                "policyengine_new_recipients": 100_000,
                "policyengine_annual_ssi_cost": 1_000_000_000,
            },
            {
                "age_group": ADULTS_18_64,
                "policyengine_new_recipients": 500_000,
                "policyengine_annual_ssi_cost": 5_000_000_000,
            },
            {
                "age_group": ELDERLY_65_PLUS,
                "policyengine_new_recipients": 200_000,
                "policyengine_annual_ssi_cost": 1_000_000_000,
            },
        ]
    )

    bridge = calculate_cbpp_age_bridge(pe_age_impacts, NO_LIMIT).set_index(
        "age_group"
    )

    assert pd.isna(bridge.loc[TOTAL_ALL_AGES, "oact_benefit_amount_scale"])
