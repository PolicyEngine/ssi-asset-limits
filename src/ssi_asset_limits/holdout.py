"""Holdout tests for SSI disability-screen prediction methods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from .constants import (
    SSI_DISABILITY_HOLDOUT_DIAGNOSTICS_FILE,
    SSI_DISABILITY_HOLDOUT_METRICS_FILE,
)

POLICYENGINE_SSI_DISABILITY_TARGET = "meets_ssi_disability_criteria"
POLICYENGINE_SSI_DISABILITY_DIFFICULTY_PREDICTORS = [
    "difficulty_dressing_or_bathing",
    "difficulty_hearing",
    "difficulty_seeing",
    "difficulty_doing_errands",
    "difficulty_walking_or_climbing_stairs",
    "difficulty_remembering_or_making_decisions",
]
POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS = [
    "age",
    "is_female",
    "is_married",
    "employment_income",
    "interest_income",
    "dividend_income",
    "rental_income",
    "bank_account_assets",
    "stock_assets",
    "bond_assets",
    "count_under_18",
    *POLICYENGINE_SSI_DISABILITY_DIFFICULTY_PREDICTORS,
    "social_security_disability",
    "has_disability_income",
]

SIPP_JOB_EARNINGS_COLUMNS = [f"TJB{i}_MSUM" for i in range(1, 8)]
SIPP_DISABILITY_INCOME_AMOUNT_COLUMNS = [f"TDIS{i}AMT" for i in range(1, 11)]
SIPP_DIFFICULTY_COLUMNS = {
    "difficulty_dressing_or_bathing": "ESELFCARE",
    "difficulty_hearing": "EHEARING",
    "difficulty_seeing": "ESEEING",
    "difficulty_doing_errands": "EERRANDS",
    "difficulty_walking_or_climbing_stairs": "EAMBULAT",
    "difficulty_remembering_or_making_decisions": "ECOGNIT",
}
POLICYENGINE_SIPP_2023_COLUMNS = sorted(
    {
        "SSUID",
        "PNUM",
        "MONTHCODE",
        "WPFINWGT",
        "TAGE",
        "ESEX",
        "EMS",
        "TPTOTINC",
        "TSSSAMT",
        "TINC_BANK",
        "TINC_STMF",
        "TINC_BOND",
        "TINC_RENT",
        "TVAL_BANK",
        "TVAL_STMF",
        "TVAL_BOND",
        "RSSI_YRYN",
        "ASSI_YRYN",
        "ESSI_BRSN",
        "ASSI_BRSN",
        "ESSRSN2YN",
        "EDISANY",
        *SIPP_JOB_EARNINGS_COLUMNS,
        *SIPP_DISABILITY_INCOME_AMOUNT_COLUMNS,
        *SIPP_DIFFICULTY_COLUMNS.values(),
    }
)
SIPP_OBSERVED_STATUS_VALUES = {0, 1, 9}


@dataclass(frozen=True)
class HoldoutSpec:
    """Column specification for a supervised holdout test."""

    name: str
    target: str
    predictors: tuple[str, ...]
    weight: str = "weight"


@dataclass(frozen=True)
class HoldoutConfig:
    """Estimator and split settings for reproducible holdout tests."""

    test_size: float = 0.30
    random_state: int = 271828
    rf_estimators: int = 500
    rf_min_samples_leaf: int = 25


POLICYENGINE_SSI_DISABILITY_HOLDOUT_SPEC = HoldoutSpec(
    name="policyengine_ssi_disability_2023",
    target=POLICYENGINE_SSI_DISABILITY_TARGET,
    predictors=tuple(POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS),
    weight="household_weight",
)


def read_policyengine_sipp_2023(path: str | Path, nrows: int | None = None):
    """Read the SIPP columns needed for the PE-style SSI disability frame."""

    return pd.read_csv(
        path,
        sep="|",
        usecols=POLICYENGINE_SIPP_2023_COLUMNS,
        nrows=nrows,
    )


def build_policyengine_ssi_disability_training_frame(
    data: pd.DataFrame,
    *,
    time_period: int = 2024,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build the PE-style SIPP frame used to test disability prediction.

    This mirrors the current us-data training setup: December SIPP rows,
    under-65 records, a rough current-law SSI non-disability candidate screen,
    and observed SSI receipt/reason rows only.
    """

    working = data.copy()
    diagnostics = {"raw_rows": float(len(working))}
    month = pd.to_numeric(working["MONTHCODE"], errors="coerce")
    working = working[month.eq(12)]
    diagnostics["december_rows"] = float(len(working))

    frame = pd.DataFrame(index=working.index)
    frame["household_id"] = working["SSUID"]
    frame["age"] = pd.to_numeric(working["TAGE"], errors="coerce")
    frame["is_female"] = _yes(working, "ESEX", value=2)
    frame["is_married"] = _yes(working, "EMS")
    frame["bank_account_assets"] = _nonnegative(working["TVAL_BANK"])
    frame["stock_assets"] = _nonnegative(working["TVAL_STMF"])
    frame["bond_assets"] = _nonnegative(working["TVAL_BOND"])
    monthly_earnings = _sipp_monthly_earned_income(working)
    frame["employment_income"] = monthly_earnings * 12
    frame["interest_income"] = (
        _nonnegative(working["TINC_BANK"]) + _nonnegative(working["TINC_BOND"])
    ) * 12
    frame["dividend_income"] = _nonnegative(working["TINC_STMF"]) * 12
    frame["rental_income"] = _nonnegative(working["TINC_RENT"]) * 12
    frame["household_weight"] = pd.to_numeric(
        working["WPFINWGT"], errors="coerce"
    ).fillna(0)

    for predictor, source_column in SIPP_DIFFICULTY_COLUMNS.items():
        frame[predictor] = _yes(working, source_column)

    frame["is_under_18"] = frame["age"] < 18
    frame["count_under_18"] = (
        frame.groupby(working["SSUID"])["is_under_18"]
        .transform("sum")
        .astype(float)
    )

    disability_income_amount = pd.Series(0.0, index=working.index)
    for column in SIPP_DISABILITY_INCOME_AMOUNT_COLUMNS:
        if column in working:
            disability_income_amount += _nonnegative(working[column])
    frame["social_security_disability"] = np.where(
        _yes(working, "ESSRSN2YN"),
        _nonnegative(working["TSSSAMT"]) * 12,
        0.0,
    )
    frame["has_disability_income"] = _yes(working, "EDISANY") | (
        disability_income_amount > 0
    )

    received_ssi = _yes(working, "RSSI_YRYN")
    under_65 = frame["age"] < 65
    disabled_or_blind_reason = _yes(working, "ESSI_BRSN")
    aged_reason = _yes(working, "ESSI_BRSN", value=2)
    frame[POLICYENGINE_SSI_DISABILITY_TARGET] = (
        received_ssi & under_65 & (disabled_or_blind_reason | ~aged_reason)
    )

    financial_candidate = _ssi_financial_candidate_mask(
        frame,
        working,
        monthly_earnings=monthly_earnings,
        time_period=time_period,
    )
    frame["ssi_disability_training_candidate"] = (
        financial_candidate & under_65
    ) | frame[POLICYENGINE_SSI_DISABILITY_TARGET]

    diagnostics["under_65_rows"] = float(under_65.sum())
    diagnostics["candidate_rows"] = float(
        frame["ssi_disability_training_candidate"].sum()
    )

    observed_mask = _observed_ssi_disability_label_mask(working, received_ssi)
    diagnostics["observed_label_rows"] = float(observed_mask.sum())
    frame = frame.loc[observed_mask].copy()
    frame = frame.loc[frame["ssi_disability_training_candidate"]].drop(
        columns=["ssi_disability_training_candidate", "household_id"]
    )
    frame = frame.dropna(
        subset=[
            *POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS,
            POLICYENGINE_SSI_DISABILITY_TARGET,
            "household_weight",
        ]
    )
    frame = frame[frame["household_weight"] > 0]
    diagnostics["fit_rows"] = float(len(frame))
    diagnostics["weighted_positive_rate"] = _weighted_mean(
        frame[POLICYENGINE_SSI_DISABILITY_TARGET].astype(float),
        frame["household_weight"].astype(float),
    )
    return frame, diagnostics


def evaluate_holdout_models(
    frame: pd.DataFrame,
    *,
    spec: HoldoutSpec,
    config: HoldoutConfig = HoldoutConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate linear-probit and random-forest classifiers on one holdout."""

    required = [*spec.predictors, spec.target, spec.weight]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        missing_list = ", ".join(missing)
        raise KeyError(f"Holdout frame is missing columns: {missing_list}")

    work = (
        frame[required]
        .replace([np.inf, -np.inf], np.nan)
        .dropna(subset=[spec.target, spec.weight])
    )
    work = work[work[spec.weight] > 0].copy()
    y = work[spec.target].astype(int)
    if y.nunique() < 2:
        raise ValueError(
            "Holdout frame must contain both positive and negative labels."
        )

    train_idx, test_idx = train_test_split(
        work.index,
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=y,
    )
    features = work[list(spec.predictors)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    x_train = features.loc[train_idx]
    x_test = features.loc[test_idx]
    y_train = y.loc[train_idx]
    y_test = y.loc[test_idx]
    w_train = work.loc[train_idx, spec.weight].astype(float)
    w_test = work.loc[test_idx, spec.weight].astype(float)

    prepared = _prepare_train_test_features(x_train, x_test)
    probit_probabilities = _predict_linear_probit(
        prepared.scaled_train,
        y_train,
        w_train,
        prepared.scaled_test,
    )
    rf_probabilities = _predict_random_forest(
        prepared.imputed_train,
        y_train,
        w_train,
        prepared.imputed_test,
        config=config,
    )

    metrics = pd.DataFrame(
        [
            _score_predictions(
                model="linear_probit_same_predictors",
                y_test=y_test,
                probabilities=probit_probabilities,
                weights=w_test,
            ),
            _score_predictions(
                model="random_forest_same_predictors",
                y_test=y_test,
                probabilities=rf_probabilities,
                weights=w_test,
            ),
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {"metric": "frame", "value": spec.name},
            {"metric": "rows", "value": float(len(work))},
            {"metric": "train_rows", "value": float(len(train_idx))},
            {"metric": "test_rows", "value": float(len(test_idx))},
            {
                "metric": "weighted_positive_rate",
                "value": _weighted_mean(y, work[spec.weight]),
            },
            {
                "metric": "weighted_positive_rate_train",
                "value": _weighted_mean(y_train, w_train),
            },
            {
                "metric": "weighted_positive_rate_test",
                "value": _weighted_mean(y_test, w_test),
            },
            {"metric": "test_size", "value": config.test_size},
            {"metric": "random_state", "value": float(config.random_state)},
            {"metric": "rf_estimators", "value": float(config.rf_estimators)},
            {
                "metric": "rf_min_samples_leaf",
                "value": float(config.rf_min_samples_leaf),
            },
            {"metric": "predictors", "value": ",".join(spec.predictors)},
        ]
    )
    return metrics, diagnostics


def evaluate_policyengine_sipp_2023_holdout(
    sipp_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    time_period: int = 2024,
    nrows: int | None = None,
    config: HoldoutConfig = HoldoutConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load SIPP 2023 and evaluate PE-style SSI disability holdout models."""

    raw = read_policyengine_sipp_2023(sipp_path, nrows=nrows)
    frame, frame_diagnostics = (
        build_policyengine_ssi_disability_training_frame(
            raw,
            time_period=time_period,
        )
    )
    metrics, diagnostics = evaluate_holdout_models(
        frame,
        spec=POLICYENGINE_SSI_DISABILITY_HOLDOUT_SPEC,
        config=config,
    )
    frame_rows = pd.DataFrame(
        [
            {"metric": f"frame_{metric}", "value": value}
            for metric, value in frame_diagnostics.items()
        ]
    )
    diagnostics = pd.concat([frame_rows, diagnostics], ignore_index=True)
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        metrics.to_csv(
            output / SSI_DISABILITY_HOLDOUT_METRICS_FILE,
            index=False,
        )
        diagnostics.to_csv(
            output / SSI_DISABILITY_HOLDOUT_DIAGNOSTICS_FILE,
            index=False,
        )
    return metrics, diagnostics


@dataclass(frozen=True)
class PreparedFeatures:
    imputed_train: pd.DataFrame
    imputed_test: pd.DataFrame
    scaled_train: pd.DataFrame
    scaled_test: pd.DataFrame


def _prepare_train_test_features(
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
) -> PreparedFeatures:
    medians = x_train.median(numeric_only=True).fillna(0)
    imputed_train = x_train.fillna(medians)
    imputed_test = x_test.fillna(medians)
    means = imputed_train.mean()
    stds = imputed_train.std(ddof=0).replace(0, 1)
    scaled_train = (imputed_train - means) / stds
    scaled_test = (imputed_test - means) / stds
    return PreparedFeatures(
        imputed_train=imputed_train,
        imputed_test=imputed_test,
        scaled_train=scaled_train,
        scaled_test=scaled_test,
    )


def _predict_linear_probit(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    weights: pd.Series,
    x_test: pd.DataFrame,
) -> np.ndarray:
    x_train_const = sm.add_constant(x_train, has_constant="add")
    x_test_const = sm.add_constant(x_test, has_constant="add")
    scaled_weights = weights / weights.mean()
    model = sm.GLM(
        y_train,
        x_train_const,
        family=sm.families.Binomial(link=sm.families.links.Probit()),
        freq_weights=scaled_weights,
    )
    result = model.fit()
    return np.asarray(result.predict(x_test_const), dtype=float)


def _predict_random_forest(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    weights: pd.Series,
    x_test: pd.DataFrame,
    *,
    config: HoldoutConfig,
) -> np.ndarray:
    model = RandomForestClassifier(
        n_estimators=config.rf_estimators,
        min_samples_leaf=config.rf_min_samples_leaf,
        max_features="sqrt",
        random_state=config.random_state,
        n_jobs=-1,
    )
    model.fit(x_train, y_train, sample_weight=weights)
    return model.predict_proba(x_test)[:, 1]


def _score_predictions(
    *,
    model: str,
    y_test: pd.Series,
    probabilities: np.ndarray,
    weights: pd.Series,
) -> dict[str, float | str]:
    probabilities = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return {
        "model": model,
        "weighted_auc": float(
            roc_auc_score(y_test, probabilities, sample_weight=weights)
        ),
        "weighted_average_precision": float(
            average_precision_score(
                y_test,
                probabilities,
                sample_weight=weights,
            )
        ),
        "weighted_brier": float(
            brier_score_loss(y_test, probabilities, sample_weight=weights)
        ),
        "weighted_log_loss": float(
            log_loss(
                y_test,
                probabilities,
                sample_weight=weights,
                labels=[0, 1],
            )
        ),
        "weighted_mean_prediction": _weighted_mean(probabilities, weights),
    }


def _nonnegative(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0)


def _yes(data: pd.DataFrame, column: str, *, value: int = 1) -> pd.Series:
    if column not in data:
        return pd.Series(False, index=data.index)
    return pd.to_numeric(data[column], errors="coerce").fillna(0).eq(value)


def _sipp_monthly_earned_income(data: pd.DataFrame) -> pd.Series:
    job_columns = [
        column for column in SIPP_JOB_EARNINGS_COLUMNS if column in data
    ]
    if job_columns:
        return (
            data[job_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
        )
    return _nonnegative(data["TPTOTINC"])


def _ssi_financial_candidate_mask(
    frame: pd.DataFrame,
    source: pd.DataFrame,
    *,
    monthly_earnings: pd.Series,
    time_period: int,
) -> pd.Series:
    parameters = _ssi_parameters(time_period)
    resource_limit = np.where(
        frame["is_married"].astype(bool),
        parameters["couple_resource_limit"],
        parameters["individual_resource_limit"],
    )
    monthly_income_limit = np.where(
        frame["is_married"].astype(bool),
        parameters["couple_fbr"],
        parameters["individual_fbr"],
    )
    liquid_resources = (
        frame["bank_account_assets"]
        + frame["stock_assets"]
        + frame["bond_assets"]
    )
    monthly_unearned_income = (
        _nonnegative(source["TPTOTINC"]) - monthly_earnings
    ).clip(
        lower=0,
    )
    monthly_countable_income = _approximate_monthly_ssi_countable_income(
        monthly_earned_income=monthly_earnings,
        monthly_unearned_income=monthly_unearned_income,
        general_exclusion=parameters["general_exclusion"],
        earned_exclusion=parameters["earned_exclusion"],
        earned_share_excluded=parameters["earned_share_excluded"],
    )
    is_blind = frame["difficulty_seeing"].fillna(False).astype(bool)
    passes_sga_gate = is_blind | monthly_earnings.le(
        parameters["non_blind_sga"]
    )
    return (
        (liquid_resources <= resource_limit)
        & monthly_countable_income.le(monthly_income_limit)
        & passes_sga_gate
    )


def _ssi_parameters(time_period: int) -> dict[str, float]:
    try:
        from policyengine_us import CountryTaxBenefitSystem

        parameters = CountryTaxBenefitSystem().parameters(
            f"{time_period}-01-01"
        )
        p = parameters.gov.ssa.ssi
        income_exclusions = p.income.exclusions
        return {
            "individual_resource_limit": float(
                p.eligibility.resources.limit.individual
            ),
            "couple_resource_limit": float(
                p.eligibility.resources.limit.couple
            ),
            "individual_fbr": float(p.amount.individual),
            "couple_fbr": float(p.amount.couple),
            "general_exclusion": float(income_exclusions.general),
            "earned_exclusion": float(income_exclusions.earned),
            "earned_share_excluded": float(income_exclusions.earned_share),
            "non_blind_sga": float(parameters.gov.ssa.sga.non_blind),
        }
    except Exception:
        return {
            "individual_resource_limit": 2_000.0,
            "couple_resource_limit": 3_000.0,
            "individual_fbr": 943.0,
            "couple_fbr": 1_415.0,
            "general_exclusion": 20.0,
            "earned_exclusion": 65.0,
            "earned_share_excluded": 0.5,
            "non_blind_sga": 1_550.0,
        }


def _approximate_monthly_ssi_countable_income(
    *,
    monthly_earned_income: pd.Series,
    monthly_unearned_income: pd.Series,
    general_exclusion: float,
    earned_exclusion: float,
    earned_share_excluded: float,
) -> pd.Series:
    applied_general = np.minimum(general_exclusion, monthly_unearned_income)
    countable_unearned = monthly_unearned_income - applied_general
    leftover_general = general_exclusion - applied_general
    earned_after_flat_exclusions = (
        monthly_earned_income - earned_exclusion - leftover_general
    ).clip(lower=0)
    countable_earned = earned_after_flat_exclusions * (
        1 - earned_share_excluded
    )
    return countable_unearned + countable_earned


def _observed_ssi_disability_label_mask(
    source: pd.DataFrame,
    received_ssi: pd.Series,
) -> pd.Series:
    ssi_receipt_observed = _observed_sipp_value(source, "RSSI_YRYN")
    ssi_receipt_observed &= pd.to_numeric(
        source.get("RSSI_YRYN", pd.Series(np.nan, index=source.index)),
        errors="coerce",
    ).isin([1, 2])
    ssi_reason_observed = _observed_sipp_value(source, "ESSI_BRSN")
    ssi_reason_observed &= pd.to_numeric(
        source.get("ESSI_BRSN", pd.Series(np.nan, index=source.index)),
        errors="coerce",
    ).isin([1, 2])
    return ssi_receipt_observed & (~received_ssi | ssi_reason_observed)


def _observed_sipp_value(source: pd.DataFrame, column: str) -> pd.Series:
    mask = (
        source[column].notna()
        if column in source
        else pd.Series(False, index=source.index)
    )
    allocation_column = f"A{column[1:]}"
    if allocation_column in source:
        allocation_status = pd.to_numeric(
            source[allocation_column],
            errors="coerce",
        ).fillna(0)
        mask &= allocation_status.isin(SIPP_OBSERVED_STATUS_VALUES)
    return mask


def _weighted_mean(values, weights) -> float:
    values = pd.Series(values).astype(float)
    weights = pd.Series(weights).astype(float)
    if len(values) == 0 or weights.sum() <= 0:
        return 0.0
    return float(np.average(values, weights=weights))
