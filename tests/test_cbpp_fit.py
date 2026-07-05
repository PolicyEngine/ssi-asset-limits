import numpy as np
import pandas as pd
import pytest

from ssi_asset_limits.cbpp import (
    CBPP_ADULT_18_64_PREDICTORS,
    SIPP_FORMAT_2023_CALENDAR,
    build_cbpp_adult_18_64_training_frame,
    calculate_cbpp_adult_18_64_scenario_counts,
    fit_cbpp_adult_18_64_probit,
    infer_sipp_format_from_columns,
)
from ssi_asset_limits.cbpp_fit_cli import build_parser


def _row(**overrides):
    row = {
        "SSUID": "1",
        "PNUM": 1,
        "MONTHCODE": 12,
        "WPFINWGT": 1.0,
        "TAGE": 50,
        "AAGE": 1,
        "RSSICOV": 0,
        "ASSICOV": 1,
        "ESSRSN2YN": 0,
        "ASSRSNYN": 1,
        "TPTOTINC": 500,
        "APTOTINC": 1,
        "TVAL_BANK": 100,
        "TVAL_STMF": 0,
        "TVAL_BOND": 0,
        "AVAL_BANK": 1,
        "AVAL_STMF": 0,
        "AVAL_BOND": 0,
        "EJOBCANT": 0,
        "AJOBCANT": 1,
        "EERRANDS": 0,
        "AERRANDS": 1,
        "EAMBULAT": 0,
        "AAMBULAT": 1,
        "RDIS": 0,
        "EHEARING": 0,
        "AHEARING": 1,
        "ESEEING": 0,
        "ASEEING": 1,
        "ECOGNIT": 0,
        "ACOGNIT": 1,
        "ESELFCARE": 0,
        "ASELFCARE": 1,
        "EDISABL": 0,
        "ADISABL": 1,
        "EDISANY": 0,
        "ADISANY": 1,
        "EEDUC": 40,
        "AEDUC": 1,
        "EMS": 1,
        "ECITIZEN": 1,
        "ACITIZEN": 1,
    }
    row.update(overrides)
    return row


def test_build_cbpp_adult_training_frame_filters_like_public_method():
    data = pd.DataFrame(
        [
            _row(RSSICOV=1, EJOBCANT=1),
            _row(SSUID="2", TAGE=17),
            _row(SSUID="3", APTOTINC=2),
            _row(SSUID="4", TPTOTINC=10_000),
        ]
    )

    frame, diagnostics = build_cbpp_adult_18_64_training_frame(data)

    assert diagnostics["raw_rows"] == 4
    assert diagnostics["adult_18_64_rows"] == 3
    assert diagnostics["income_eligible_rows"] == 2
    assert diagnostics["observed_rows"] == 1
    assert frame["participates_ssi_or_ssdi"].tolist() == [1]
    assert frame["prevented_from_work"].tolist() == [1]
    assert set(CBPP_ADULT_18_64_PREDICTORS).issubset(frame.columns)


def test_build_cbpp_adult_training_frame_supports_2023_sipp_columns():
    data = pd.DataFrame(
        [
            _row(
                RSSI_YRYN=1,
                ASSI_YRYN=1,
                EJOBCANT=1,
                TPTOTINC=800,
            ),
            _row(
                SSUID="2",
                RSSI_YRYN=2,
                ASSI_YRYN=1,
                TPTOTINC=500,
            ),
        ]
    ).drop(columns=["RSSICOV", "ASSICOV"])

    frame, diagnostics = build_cbpp_adult_18_64_training_frame(
        data,
        sipp_format=SIPP_FORMAT_2023_CALENDAR,
    )

    assert diagnostics["sipp_format"] == SIPP_FORMAT_2023_CALENDAR
    assert diagnostics["monthly_fbr"] == pytest.approx(841)
    assert frame["participates_ssi_or_ssdi"].tolist() == [1, 0]
    assert (
        infer_sipp_format_from_columns(data.columns)
        == SIPP_FORMAT_2023_CALENDAR
    )


def test_fit_cbpp_adult_probit_returns_public_comparison_columns():
    records = []
    rng = np.random.default_rng(0)
    for idx in range(300):
        age = int(rng.integers(18, 65))
        prevented = int(rng.random() < 0.22)
        errands = int(rng.random() < 0.12)
        walking = int(rng.random() < 0.16)
        core_disability = int(rng.random() < 0.24)
        work_limit = int(rng.random() < 0.2)
        disability_income = int(rng.random() < 0.08)
        married = int(rng.random() < 0.45)
        noncitizen = int(rng.random() < 0.1)
        index = (
            -2.6
            + 0.02 * age
            + 0.7 * prevented
            + 0.3 * errands
            - 0.1 * walking
            + 0.4 * core_disability
            + 0.5 * work_limit
            + 0.6 * disability_income
            - 0.3 * married
            - 0.7 * noncitizen
        )
        probability = 1 / (1 + np.exp(-index))
        participates = int(rng.random() < probability)
        records.append(
            {
                "participates_ssi_or_ssdi": participates,
                "countable_assets": 100 + idx,
                "log_countable_income": 0.2 + idx / 100,
                "log_countable_assets": 0.1 + idx / 120,
                "age": age,
                "prevented_from_work": prevented,
                "difficulty_errands_alone": errands,
                "serious_difficulty_walking_or_climbing_stairs": walking,
                "any_six_core_disability_measure": core_disability,
                "condition_limits_kind_or_amount_work": work_limit,
                "disability_or_health_condition_income": disability_income,
                "education_category": 30 + (idx % 10),
                "married": married,
                "not_us_citizen": noncitizen,
                "weight": 1.0,
            }
        )
    frame = pd.DataFrame(records)

    coefficients, diagnostics = fit_cbpp_adult_18_64_probit(frame)
    scenario_counts = calculate_cbpp_adult_18_64_scenario_counts(
        frame,
        coefficients,
    )

    assert "published_cbpp_coefficient" in coefficients.columns
    assert "coefficient_minus_published" in coefficients.columns
    assert "const" in set(coefficients["term"])
    assert diagnostics["nobs"] == 300
    assert isinstance(diagnostics["converged"], bool)
    assert "ten_twenty" in set(scenario_counts["scenario"])
    assert (scenario_counts["adult_18_64_predicted_beneficiaries"] >= 0).all()


def test_cbpp_fit_cli_parses_download_options():
    args = build_parser().parse_args(
        [
            "--output-dir",
            "/tmp/out",
            "--sipp-path",
            "/tmp/pu2014w2.csv.gz",
            "--include-imputed",
            "--sipp-format",
            "2023-calendar",
            "--monthly-fbr",
            "841",
            "--income-limit-multiple",
            "1.5",
            "--nrows",
            "100",
        ]
    )

    assert args.output_dir == "/tmp/out"
    assert args.sipp_path == "/tmp/pu2014w2.csv.gz"
    assert args.include_imputed is True
    assert args.sipp_format == "2023-calendar"
    assert args.monthly_fbr == pytest.approx(841)
    assert args.income_limit_multiple == pytest.approx(1.5)
    assert args.nrows == 100
