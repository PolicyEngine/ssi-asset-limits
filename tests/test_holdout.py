import numpy as np
import pandas as pd
import pytest

from ssi_asset_limits.holdout import (
    POLICYENGINE_SSI_DISABILITY_HOLDOUT_SPEC,
    POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS,
    POLICYENGINE_SSI_DISABILITY_TARGET,
    HoldoutConfig,
    build_policyengine_ssi_disability_training_frame,
    evaluate_holdout_models,
)
from ssi_asset_limits.holdout_cli import build_parser


def _sipp_row(**overrides):
    row = {
        "SSUID": "1",
        "PNUM": 1,
        "MONTHCODE": 12,
        "WPFINWGT": 1.0,
        "TAGE": 50,
        "ESEX": 2,
        "EMS": 0,
        "TPTOTINC": 300,
        "TSSSAMT": 0,
        "TINC_BANK": 0,
        "TINC_STMF": 0,
        "TINC_BOND": 0,
        "TINC_RENT": 0,
        "TVAL_BANK": 100,
        "TVAL_STMF": 0,
        "TVAL_BOND": 0,
        "RSSI_YRYN": 2,
        "ASSI_YRYN": 1,
        "ESSI_BRSN": 0,
        "ASSI_BRSN": 1,
        "ESSRSN2YN": 0,
        "EDISANY": 0,
        "ESELFCARE": 0,
        "EHEARING": 0,
        "ESEEING": 0,
        "EERRANDS": 0,
        "EAMBULAT": 0,
        "ECOGNIT": 0,
    }
    for index in range(1, 8):
        row[f"TJB{index}_MSUM"] = 0
    for index in range(1, 11):
        row[f"TDIS{index}AMT"] = 0
    row.update(overrides)
    return row


def test_build_policyengine_training_frame_filters_candidates_and_observed():
    data = pd.DataFrame(
        [
            _sipp_row(RSSI_YRYN=1, ESSI_BRSN=1, ESELFCARE=1),
            _sipp_row(SSUID="2"),
            _sipp_row(SSUID="3", TVAL_BANK=50_000),
            _sipp_row(SSUID="4", ASSI_YRYN=2),
            _sipp_row(SSUID="5", TAGE=70),
        ]
    )

    frame, diagnostics = build_policyengine_ssi_disability_training_frame(data)

    assert diagnostics["raw_rows"] == 5
    assert diagnostics["observed_label_rows"] == 4
    assert diagnostics["fit_rows"] == 2
    assert frame[POLICYENGINE_SSI_DISABILITY_TARGET].tolist() == [True, False]
    assert set(POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS).issubset(
        frame.columns
    )


def test_evaluate_holdout_models_compares_linear_probit_and_random_forest():
    rng = np.random.default_rng(0)
    records = []
    for index in range(400):
        age = int(rng.integers(18, 65))
        difficulty = int(rng.random() < 0.25)
        disability_income = int(rng.random() < 0.08)
        earnings = float(rng.gamma(2, 3_000))
        assets = float(rng.gamma(1.5, 1_000))
        index_value = (
            -3.0
            + 0.03 * age
            + 1.2 * difficulty
            + 1.0 * disability_income
            - 0.00005 * earnings
            - 0.00005 * assets
        )
        probability = 1 / (1 + np.exp(-index_value))
        row = {
            "age": age,
            "is_female": int(rng.random() < 0.52),
            "is_married": int(rng.random() < 0.35),
            "employment_income": earnings,
            "interest_income": 0,
            "dividend_income": 0,
            "rental_income": 0,
            "bank_account_assets": assets,
            "stock_assets": 0,
            "bond_assets": 0,
            "count_under_18": int(rng.integers(0, 3)),
            "difficulty_dressing_or_bathing": difficulty,
            "difficulty_hearing": 0,
            "difficulty_seeing": 0,
            "difficulty_doing_errands": difficulty,
            "difficulty_walking_or_climbing_stairs": difficulty,
            "difficulty_remembering_or_making_decisions": 0,
            "social_security_disability": disability_income * 6_000,
            "has_disability_income": disability_income,
            POLICYENGINE_SSI_DISABILITY_TARGET: int(
                rng.random() < probability
            ),
            "household_weight": 1.0 + rng.random(),
        }
        records.append(row)
    frame = pd.DataFrame(records)

    metrics, diagnostics = evaluate_holdout_models(
        frame,
        spec=POLICYENGINE_SSI_DISABILITY_HOLDOUT_SPEC,
        config=HoldoutConfig(rf_estimators=20, rf_min_samples_leaf=5),
    )

    assert set(metrics["model"]) == {
        "linear_probit_same_predictors",
        "random_forest_same_predictors",
    }
    assert metrics["weighted_auc"].between(0, 1).all()
    assert "weighted_positive_rate_test" in set(diagnostics["metric"])


def test_evaluate_holdout_models_requires_two_target_classes():
    frame = pd.DataFrame(
        {
            predictor: [0, 1, 2]
            for predictor in POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS
        }
    )
    frame[POLICYENGINE_SSI_DISABILITY_TARGET] = 0
    frame["household_weight"] = 1

    with pytest.raises(ValueError, match="both positive and negative"):
        evaluate_holdout_models(
            frame,
            spec=POLICYENGINE_SSI_DISABILITY_HOLDOUT_SPEC,
            config=HoldoutConfig(rf_estimators=5),
        )


def test_holdout_cli_parses_model_options():
    args = build_parser().parse_args(
        [
            "--sipp-path",
            "/tmp/pu2023.csv",
            "--output-dir",
            "/tmp/out",
            "--test-size",
            "0.25",
            "--random-state",
            "123",
            "--rf-estimators",
            "10",
            "--rf-min-samples-leaf",
            "3",
            "--nrows",
            "100",
        ]
    )

    assert args.sipp_path == "/tmp/pu2023.csv"
    assert args.output_dir == "/tmp/out"
    assert args.test_size == pytest.approx(0.25)
    assert args.random_state == 123
    assert args.rf_estimators == 10
    assert args.rf_min_samples_leaf == 3
    assert args.nrows == 100
