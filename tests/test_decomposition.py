import pandas as pd
import pytest

from ssi_asset_limits.decomposition import (
    CBPP_NONFINANCIAL_PREDICTORS,
    build_policyengine_sipp_scoring_frame,
    summarize_asset_scenario,
)
from ssi_asset_limits.decomposition_cli import build_parser


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


def test_summarize_asset_scenario_counts_newly_eligible_people():
    frame = pd.DataFrame(
        {
            "weight": [10.0, 20.0, 30.0],
            "countable_assets": [1_000.0, 5_000.0, 15_000.0],
            "married": [False, False, True],
        }
    )
    probabilities = pd.Series([0.5, 0.25, 0.1], index=frame.index)

    row = summarize_asset_scenario(
        frame,
        probabilities=probabilities,
        weight="weight",
        assets="countable_assets",
        married="married",
        step="x",
        label="test",
        model="test_model",
        scope="adult_18_64_sipp",
        individual_limit=10_000,
        couple_limit=20_000,
    )

    assert row["current_law_predicted_recipients"] == pytest.approx(5)
    assert row["newly_eligible_predicted_recipients"] == pytest.approx(8)
    assert row["reform_predicted_recipients"] == pytest.approx(13)


def test_nonfinancial_predictors_drop_income_and_asset_logs():
    assert "log_countable_income" not in CBPP_NONFINANCIAL_PREDICTORS
    assert "log_countable_assets" not in CBPP_NONFINANCIAL_PREDICTORS
    assert "age" in CBPP_NONFINANCIAL_PREDICTORS


def test_policyengine_sipp_scoring_frame_keeps_asset_ineligible_adults():
    data = pd.DataFrame(
        [
            _sipp_row(TVAL_BANK=100),
            _sipp_row(SSUID="2", TVAL_BANK=8_000, EAMBULAT=1),
            _sipp_row(SSUID="3", TAGE=70, TVAL_BANK=8_000),
        ]
    )

    frame = build_policyengine_sipp_scoring_frame(data, time_period=2024)

    assert len(frame) == 2
    assert frame["countable_assets"].tolist() == [100, 8_000]
    assert frame["ssi_income_sga_eligible"].tolist() == [True, True]


def test_decomposition_cli_parses_inputs():
    args = build_parser().parse_args(
        [
            "--sipp-2024-path",
            "/tmp/pu2024.csv",
            "--sipp-2014-path",
            "/tmp/pu2014w2.csv.gz",
            "--output-dir",
            "/tmp/out",
            "--ecps-results-dir",
            "/tmp/ecps",
            "--skip-2014",
            "--nrows",
            "100",
        ]
    )

    assert args.sipp_2024_path == "/tmp/pu2024.csv"
    assert args.sipp_2014_path == "/tmp/pu2014w2.csv.gz"
    assert args.output_dir == "/tmp/out"
    assert args.ecps_results_dir == "/tmp/ecps"
    assert args.skip_2014 is True
    assert args.nrows == 100
