"""Sequential SSI asset-limit decomposition experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import RandomForestClassifier

from .cbpp import (
    ADULTS_18_64,
    CBPP_ADULT_18_64_PREDICTORS,
    CBPP_SIPP_FORMATS,
    SIPP_FORMAT_2023_CALENDAR,
    TEN_TWENTY,
    TOTAL_ALL_AGES,
    build_cbpp_adult_18_64_training_frame,
    cbpp_age_targets,
    download_sipp_2014_wave2,
    infer_sipp_format_from_columns,
    read_sipp_2014_wave2,
)
from .holdout import (
    POLICYENGINE_SIPP_2023_COLUMNS,
    POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS,
    POLICYENGINE_SSI_DISABILITY_TARGET,
    SIPP_DIFFICULTY_COLUMNS,
    _approximate_monthly_ssi_countable_income,
    _nonnegative,
    _sipp_monthly_earned_income,
    _ssi_parameters,
    _yes,
    build_policyengine_ssi_disability_training_frame,
)

SIPP_CHUNK_SIZE = 100_000
FINANCIAL_CBPP_PREDICTORS = (
    "log_countable_income",
    "log_countable_assets",
)
CBPP_NONFINANCIAL_PREDICTORS = tuple(
    predictor
    for predictor in CBPP_ADULT_18_64_PREDICTORS
    if predictor not in FINANCIAL_CBPP_PREDICTORS
)


@dataclass(frozen=True)
class DecompositionConfig:
    """Settings for a reproducible decomposition run."""

    sipp_2024_path: Path
    sipp_2014_path: Path | None = None
    sipp_2014_data_dir: Path = Path(".cache/sipp2014w2")
    output_dir: Path = Path(".local-results/sipp-decomposition")
    individual_limit: float = 10_000
    couple_limit: float = 20_000
    sipp_2024_monthly_fbr: float = 914.0
    sipp_2024_time_period: int = 2024
    income_limit_multiple: float = 2.0
    rf_estimators: int = 500
    rf_min_samples_leaf: int = 25
    random_state: int = 271828
    nrows: int | None = None
    run_2014: bool = True
    ecps_results_dir: Path | None = None


def run_decomposition(
    config: DecompositionConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run sequential SIPP/eCPS SSI asset-limit decomposition experiments."""

    results: list[dict[str, float | str]] = []
    diagnostics: list[dict[str, float | str]] = []

    if config.individual_limit == 10_000 and config.couple_limit == 20_000:
        results.extend(cbpp_public_reference_rows())

    if config.run_2014:
        sipp_2014_path = config.sipp_2014_path
        if sipp_2014_path is None:
            sipp_2014_path = download_sipp_2014_wave2(
                config.sipp_2014_data_dir
            )
        frame_2014, frame_diagnostics = build_cbpp_frame_from_file(
            sipp_2014_path,
            sipp_format="2014-wave2",
            observed_only=True,
            monthly_fbr=None,
            income_limit_multiple=config.income_limit_multiple,
            nrows=config.nrows,
        )
        row, extra = run_cbpp_predictor_experiment(
            frame_2014,
            step="pre_a",
            label="2014 SIPP, CBPP-style probit with public predictors",
            model="weighted_probit",
            predictors=tuple(CBPP_ADULT_18_64_PREDICTORS),
            config=config,
        )
        results.append(row)
        diagnostics.extend(
            _diagnostic_rows("pre_a", frame_diagnostics | extra)
        )

    frame_2024, frame_2024_diagnostics = build_cbpp_frame_from_file(
        config.sipp_2024_path,
        sipp_format=SIPP_FORMAT_2023_CALENDAR,
        observed_only=True,
        monthly_fbr=config.sipp_2024_monthly_fbr,
        income_limit_multiple=config.income_limit_multiple,
        nrows=config.nrows,
    )

    for step, label, model, predictors in [
        (
            "a",
            "2024 SIPP, CBPP-style probit with income/assets",
            "weighted_probit",
            tuple(CBPP_ADULT_18_64_PREDICTORS),
        ),
        (
            "b",
            "2024 SIPP, CBPP-style probit excluding income/assets",
            "weighted_probit",
            CBPP_NONFINANCIAL_PREDICTORS,
        ),
        (
            "c",
            "2024 SIPP, CBPP-style random forest excluding income/assets",
            "random_forest",
            CBPP_NONFINANCIAL_PREDICTORS,
        ),
    ]:
        row, extra = run_cbpp_predictor_experiment(
            frame_2024,
            step=step,
            label=label,
            model=model,
            predictors=predictors,
            config=config,
        )
        results.append(row)
        diagnostics.extend(
            _diagnostic_rows(step, frame_2024_diagnostics | extra)
        )

    row, extra = run_policyengine_sipp_experiment(config)
    results.append(row)
    diagnostics.extend(_diagnostic_rows("d", extra))

    if config.ecps_results_dir is not None:
        results.extend(read_ecps_experiment_rows(config.ecps_results_dir))

    results_df = pd.DataFrame(results)
    diagnostics_df = pd.DataFrame(diagnostics)
    return results_df, diagnostics_df


def cbpp_public_reference_rows() -> list[dict[str, float | str]]:
    """Return CBPP's published target rows for reference."""

    targets = cbpp_age_targets(TEN_TWENTY)
    rows = []
    for group, scope in [
        (TOTAL_ALL_AGES, "all_ages_cbpp_public"),
        (ADULTS_18_64, "adult_18_64_cbpp_public"),
    ]:
        target = targets[targets["group"] == group].iloc[0]
        rows.append(
            {
                "step": f"cbpp_public_{group}",
                "label": "CBPP published $10k/$20k target",
                "scope": scope,
                "model": "cbpp_published_target",
                "current_law_predicted_recipients": np.nan,
                "reform_predicted_recipients": np.nan,
                "newly_eligible_predicted_recipients": float(
                    target["new_beneficiaries"]
                ),
                "individual_limit": 10_000.0,
                "couple_limit": 20_000.0,
                "predictors": "not_published_for_all_groups",
            }
        )
    return rows


def build_cbpp_frame_from_file(
    sipp_path: str | Path,
    *,
    sipp_format: str | None = None,
    observed_only: bool = True,
    monthly_fbr: float | None = None,
    income_limit_multiple: float = 2.0,
    nrows: int | None = None,
) -> tuple[pd.DataFrame, dict[str, float | str]]:
    """Read SIPP chunks and build CBPP's adult 18-64 training frame."""

    sipp_path = Path(sipp_path)
    if sipp_format is None:
        sipp_format = infer_sipp_format_from_columns(
            read_sipp_2014_wave2(sipp_path, nrows=0).columns
        )
    required_columns = list(CBPP_SIPP_FORMATS[sipp_format].required_columns)

    if nrows is not None:
        data = read_sipp_2014_wave2(
            sipp_path,
            columns=required_columns,
            nrows=nrows,
        )
        frame, diagnostics = build_cbpp_adult_18_64_training_frame(
            data,
            observed_only=observed_only,
            monthly_fbr=monthly_fbr,
            income_limit_multiple=income_limit_multiple,
            sipp_format=sipp_format,
        )
        diagnostics |= _cbpp_frame_weighted_diagnostics(frame)
        diagnostics["sipp_path"] = str(sipp_path)
        return frame, diagnostics

    frames = []
    diagnostics: dict[str, float | str] = {
        "raw_rows": 0.0,
        "december_rows": 0.0,
        "adult_18_64_rows": 0.0,
        "income_eligible_rows": 0.0,
        "observed_rows": 0.0,
        "fit_rows": 0.0,
        "sipp_format": sipp_format,
        "sipp_path": str(sipp_path),
    }
    reader = read_sipp_2014_wave2(
        sipp_path,
        columns=required_columns,
        chunksize=SIPP_CHUNK_SIZE,
    )
    for chunk in reader:
        frame, chunk_diagnostics = build_cbpp_adult_18_64_training_frame(
            chunk,
            observed_only=observed_only,
            monthly_fbr=monthly_fbr,
            income_limit_multiple=income_limit_multiple,
            sipp_format=sipp_format,
        )
        frames.append(frame)
        for metric in (
            "raw_rows",
            "december_rows",
            "adult_18_64_rows",
            "income_eligible_rows",
            "observed_rows",
            "fit_rows",
        ):
            diagnostics[metric] = float(diagnostics[metric]) + float(
                chunk_diagnostics[metric]
            )

    training_frame = pd.concat(frames, ignore_index=True)
    diagnostics |= _cbpp_frame_weighted_diagnostics(training_frame)
    diagnostics["monthly_fbr"] = (
        monthly_fbr
        if monthly_fbr is not None
        else CBPP_SIPP_FORMATS[sipp_format].default_monthly_fbr
    )
    diagnostics["income_limit_multiple"] = income_limit_multiple
    diagnostics["observed_only"] = observed_only
    return training_frame, diagnostics


def run_cbpp_predictor_experiment(
    frame: pd.DataFrame,
    *,
    step: str,
    label: str,
    model: str,
    predictors: tuple[str, ...],
    config: DecompositionConfig,
) -> tuple[dict[str, float | str], dict[str, float | str]]:
    """Fit one CBPP-frame predictor experiment and summarize the scenario."""

    if model == "weighted_probit":
        probabilities, model_diagnostics = fit_weighted_probit_probabilities(
            frame,
            predictors=predictors,
            target="participates_ssi_or_ssdi",
            weight="weight",
        )
    elif model == "random_forest":
        probabilities, model_diagnostics = fit_random_forest_probabilities(
            frame,
            predictors=predictors,
            target="participates_ssi_or_ssdi",
            weight="weight",
            config=config,
        )
    else:
        raise ValueError(f"Unsupported model: {model}")

    row = summarize_asset_scenario(
        frame,
        probabilities=probabilities,
        weight="weight",
        assets="countable_assets",
        married="married",
        step=step,
        label=label,
        model=model,
        scope="adult_18_64_sipp",
        individual_limit=config.individual_limit,
        couple_limit=config.couple_limit,
    )
    row["predictors"] = ",".join(predictors)
    return row, model_diagnostics


def fit_weighted_probit_probabilities(
    frame: pd.DataFrame,
    *,
    predictors: tuple[str, ...],
    target: str,
    weight: str,
) -> tuple[pd.Series, dict[str, float | str]]:
    """Fit a weighted probit and return in-sample probabilities."""

    work = frame[[*predictors, target, weight]].replace(
        [np.inf, -np.inf],
        np.nan,
    )
    work = work.dropna()
    y = work[target].astype(int)
    if y.nunique() < 2:
        raise ValueError("The probit training frame needs two target classes.")
    x = sm.add_constant(
        work[list(predictors)].apply(pd.to_numeric, errors="coerce"),
        has_constant="add",
    )
    weights = work[weight].astype(float)
    model = sm.GLM(
        y,
        x,
        family=sm.families.Binomial(link=sm.families.links.Probit()),
        freq_weights=weights / weights.mean(),
    )
    result = model.fit()
    probabilities = pd.Series(result.predict(x), index=work.index)
    return probabilities.reindex(frame.index).fillna(0), {
        "model_nobs": float(result.nobs),
        "model_converged": bool(result.converged),
        "model_deviance": float(result.deviance),
        "weighted_mean_prediction": _weighted_mean(probabilities, weights),
        "weighted_positive_rate": _weighted_mean(y, weights),
    }


def fit_random_forest_probabilities(
    frame: pd.DataFrame,
    *,
    predictors: tuple[str, ...],
    target: str,
    weight: str,
    config: DecompositionConfig,
) -> tuple[pd.Series, dict[str, float | str]]:
    """Fit a weighted random forest and return in-sample probabilities."""

    work = frame[[*predictors, target, weight]].replace(
        [np.inf, -np.inf],
        np.nan,
    )
    work = work.dropna(subset=[target, weight])
    work = work[work[weight] > 0].copy()
    y = work[target].astype(int)
    if y.nunique() < 2:
        raise ValueError(
            "The random-forest training frame needs two target classes."
        )
    x = work[list(predictors)].apply(pd.to_numeric, errors="coerce")
    medians = x.median(numeric_only=True).fillna(0)
    x = x.fillna(medians)
    model = RandomForestClassifier(
        n_estimators=config.rf_estimators,
        min_samples_leaf=config.rf_min_samples_leaf,
        max_features="sqrt",
        random_state=config.random_state,
        n_jobs=-1,
    )
    weights = work[weight].astype(float)
    model.fit(x, y, sample_weight=weights)
    probabilities = pd.Series(
        model.predict_proba(x)[:, 1],
        index=work.index,
    )
    return probabilities.reindex(frame.index).fillna(0), {
        "model_nobs": float(len(work)),
        "rf_estimators": float(config.rf_estimators),
        "rf_min_samples_leaf": float(config.rf_min_samples_leaf),
        "weighted_mean_prediction": _weighted_mean(probabilities, weights),
        "weighted_positive_rate": _weighted_mean(y, weights),
    }


def summarize_asset_scenario(
    frame: pd.DataFrame,
    *,
    probabilities: pd.Series,
    weight: str,
    assets: str,
    married: str,
    step: str,
    label: str,
    model: str,
    scope: str,
    individual_limit: float,
    couple_limit: float,
    eligible: pd.Series | None = None,
) -> dict[str, float | str]:
    """Summarize current-law and newly resource-eligible predicted counts."""

    weights = frame[weight].astype(float)
    probabilities = probabilities.reindex(frame.index).fillna(0).astype(float)
    countable_assets = frame[assets].astype(float)
    is_married = frame[married].astype(bool)
    current_limit = np.where(is_married, 3_000.0, 2_000.0)
    reform_limit = np.where(is_married, couple_limit, individual_limit)
    current_asset_eligible = countable_assets <= current_limit
    reform_asset_eligible = countable_assets <= reform_limit
    new_asset_eligible = (~current_asset_eligible) & reform_asset_eligible
    if eligible is None:
        eligible = pd.Series(True, index=frame.index)
    eligible = eligible.reindex(frame.index).fillna(False).astype(bool)
    weighted_probability = weights * probabilities
    current = eligible & current_asset_eligible
    new = eligible & new_asset_eligible
    reform = eligible & reform_asset_eligible

    return {
        "step": step,
        "label": label,
        "scope": scope,
        "model": model,
        "current_law_predicted_recipients": float(
            weighted_probability[current].sum()
        ),
        "reform_predicted_recipients": float(
            weighted_probability[reform].sum()
        ),
        "newly_eligible_predicted_recipients": float(
            weighted_probability[new].sum()
        ),
        "weighted_rows": float(weights.sum()),
        "unweighted_rows": float(len(frame)),
        "individual_limit": individual_limit,
        "couple_limit": couple_limit,
    }


def run_policyengine_sipp_experiment(
    config: DecompositionConfig,
) -> tuple[dict[str, float | str], dict[str, float | str]]:
    """Run the PE-style full-predictor random forest on 2024 SIPP only."""

    data = pd.read_csv(
        config.sipp_2024_path,
        sep="|",
        usecols=POLICYENGINE_SIPP_2023_COLUMNS,
        nrows=config.nrows,
    )
    training_frame, training_diagnostics = (
        build_policyengine_ssi_disability_training_frame(
            data,
            time_period=config.sipp_2024_time_period,
        )
    )
    scoring_frame = build_policyengine_sipp_scoring_frame(
        data,
        time_period=config.sipp_2024_time_period,
    )
    probabilities, model_diagnostics = fit_random_forest_probabilities(
        training_frame,
        predictors=tuple(POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS),
        target=POLICYENGINE_SSI_DISABILITY_TARGET,
        weight="household_weight",
        config=config,
    )
    scoring_probabilities = predict_random_forest_on_frame(
        training_frame,
        scoring_frame,
        predictors=tuple(POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS),
        target=POLICYENGINE_SSI_DISABILITY_TARGET,
        weight="household_weight",
        config=config,
    )
    scoring_probabilities = scoring_probabilities * disability_signal(
        scoring_frame
    )
    row = summarize_asset_scenario(
        scoring_frame,
        probabilities=scoring_probabilities,
        weight="household_weight",
        assets="countable_assets",
        married="is_married",
        step="d",
        label="2024 SIPP, PolicyEngine full predictor random forest",
        model="policyengine_full_random_forest",
        scope="adult_18_64_sipp",
        individual_limit=config.individual_limit,
        couple_limit=config.couple_limit,
        eligible=scoring_frame["ssi_income_sga_eligible"],
    )
    row["predictors"] = ",".join(POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS)
    diagnostics = {
        **{f"training_{k}": v for k, v in training_diagnostics.items()},
        **{f"model_{k}": v for k, v in model_diagnostics.items()},
        "scoring_rows": float(len(scoring_frame)),
        "scoring_weighted_rows": float(
            scoring_frame["household_weight"].sum()
        ),
        "scoring_weighted_mean_prediction": _weighted_mean(
            scoring_probabilities,
            scoring_frame["household_weight"],
        ),
        "training_weighted_mean_prediction_in_sample": _weighted_mean(
            probabilities,
            training_frame["household_weight"],
        ),
    }
    return row, diagnostics


def predict_random_forest_on_frame(
    training_frame: pd.DataFrame,
    scoring_frame: pd.DataFrame,
    *,
    predictors: tuple[str, ...],
    target: str,
    weight: str,
    config: DecompositionConfig,
) -> pd.Series:
    """Fit a weighted random forest and score a separate frame."""

    train = training_frame[[*predictors, target, weight]].replace(
        [np.inf, -np.inf],
        np.nan,
    )
    train = train.dropna(subset=[target, weight])
    train = train[train[weight] > 0].copy()
    x_train = train[list(predictors)].apply(pd.to_numeric, errors="coerce")
    medians = x_train.median(numeric_only=True).fillna(0)
    x_train = x_train.fillna(medians)
    y_train = train[target].astype(int)
    model = RandomForestClassifier(
        n_estimators=config.rf_estimators,
        min_samples_leaf=config.rf_min_samples_leaf,
        max_features="sqrt",
        random_state=config.random_state,
        n_jobs=-1,
    )
    model.fit(x_train, y_train, sample_weight=train[weight].astype(float))
    x_score = scoring_frame[list(predictors)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    x_score = x_score.fillna(medians)
    return pd.Series(
        model.predict_proba(x_score)[:, 1],
        index=scoring_frame.index,
    )


def build_policyengine_sipp_scoring_frame(
    data: pd.DataFrame,
    *,
    time_period: int,
) -> pd.DataFrame:
    """Build adult 18-64 SIPP rows to score with the PE-style model."""

    working = data[
        pd.to_numeric(data["MONTHCODE"], errors="coerce").eq(12)
    ].copy()
    frame = pd.DataFrame(index=working.index)
    frame["age"] = pd.to_numeric(working["TAGE"], errors="coerce")
    frame["is_female"] = _yes(working, "ESEX", value=2)
    frame["is_married"] = _yes(working, "EMS")
    frame["bank_account_assets"] = _nonnegative(working["TVAL_BANK"])
    frame["stock_assets"] = _nonnegative(working["TVAL_STMF"])
    frame["bond_assets"] = _nonnegative(working["TVAL_BOND"])
    frame["countable_assets"] = (
        frame["bank_account_assets"]
        + frame["stock_assets"]
        + frame["bond_assets"]
    )
    monthly_earnings = _sipp_monthly_earned_income(working)
    frame["employment_income"] = monthly_earnings * 12
    frame["interest_income"] = (
        _nonnegative(working["TINC_BANK"]) + _nonnegative(working["TINC_BOND"])
    ) * 12
    frame["dividend_income"] = _nonnegative(working["TINC_STMF"]) * 12
    frame["rental_income"] = _nonnegative(working["TINC_RENT"]) * 12
    frame["household_weight"] = pd.to_numeric(
        working["WPFINWGT"],
        errors="coerce",
    ).fillna(0)

    for predictor, source_column in SIPP_DIFFICULTY_COLUMNS.items():
        frame[predictor] = _yes(working, source_column)

    frame["is_under_18"] = frame["age"] < 18
    frame["count_under_18"] = (
        frame.groupby(working["SSUID"])["is_under_18"]
        .transform("sum")
        .astype(float)
    )
    frame["social_security_disability"] = np.where(
        _yes(working, "ESSRSN2YN"),
        _nonnegative(working["TSSSAMT"]) * 12,
        0.0,
    )
    disability_income_amount = pd.Series(0.0, index=working.index)
    for column in [f"TDIS{i}AMT" for i in range(1, 11)]:
        if column in working:
            disability_income_amount += _nonnegative(working[column])
    frame["has_disability_income"] = _yes(working, "EDISANY") | (
        disability_income_amount > 0
    )
    frame["ssi_income_sga_eligible"] = ssi_income_sga_eligible(
        frame,
        working,
        monthly_earnings=monthly_earnings,
        time_period=time_period,
    )
    frame = frame[
        frame["age"].between(18, 64, inclusive="both")
        & (frame["household_weight"] > 0)
    ]
    return frame.drop(columns=["is_under_18"]).dropna(
        subset=[
            *POLICYENGINE_SSI_DISABILITY_MODEL_PREDICTORS,
            "countable_assets",
            "household_weight",
        ]
    )


def ssi_income_sga_eligible(
    frame: pd.DataFrame,
    source: pd.DataFrame,
    *,
    monthly_earnings: pd.Series,
    time_period: int,
) -> pd.Series:
    """Approximate SSI non-resource income and SGA eligibility."""

    parameters = _ssi_parameters(time_period)
    monthly_income_limit = np.where(
        frame["is_married"].astype(bool),
        parameters["couple_fbr"],
        parameters["individual_fbr"],
    )
    monthly_unearned_income = (
        _nonnegative(source["TPTOTINC"]) - monthly_earnings
    ).clip(lower=0)
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
    return pd.Series(
        monthly_countable_income.le(monthly_income_limit) & passes_sga_gate,
        index=frame.index,
    )


def disability_signal(frame: pd.DataFrame) -> pd.Series:
    """Match PE's post-model requirement for at least one disability signal."""

    difficulty_signal = (
        frame[
            [
                "difficulty_dressing_or_bathing",
                "difficulty_hearing",
                "difficulty_seeing",
                "difficulty_doing_errands",
                "difficulty_walking_or_climbing_stairs",
                "difficulty_remembering_or_making_decisions",
            ]
        ]
        .astype(bool)
        .any(axis=1)
    )
    return (
        difficulty_signal
        | frame["social_security_disability"].astype(float).gt(0)
        | frame["has_disability_income"].astype(bool)
    ).astype(float)


def read_ecps_experiment_rows(
    output_dir: str | Path,
) -> list[dict[str, float | str]]:
    """Read a completed eCPS microsim output directory for step e."""

    output_dir = Path(output_dir)
    national = pd.read_csv(output_dir / "national_summary.csv")
    values = national.set_index("metric")["value"].astype(float)
    rows: list[dict[str, float | str]] = [
        {
            "step": "e",
            "label": "eCPS, full PolicyEngine microsimulation",
            "scope": "all_ages_ecps",
            "model": "policyengine_microsimulation",
            "current_law_predicted_recipients": values.get(
                "baseline_recipients",
                np.nan,
            ),
            "reform_predicted_recipients": values.get(
                "reform_recipients",
                np.nan,
            ),
            "newly_eligible_predicted_recipients": values.get(
                "new_recipients",
                np.nan,
            ),
            "annual_ssi_cost": values.get("annual_ssi_cost", np.nan),
            "average_gain": values.get("average_gain", np.nan),
            "predictors": "full_policyengine_model_and_ecps_inputs",
        }
    ]
    age_bridge = output_dir / "cbpp_age_bridge.csv"
    if age_bridge.exists():
        age_rows = pd.read_csv(age_bridge)
        adult = age_rows[age_rows["age_group"] == "adults_18_64"]
        if not adult.empty:
            adult_row = adult.iloc[0]
            rows.append(
                {
                    "step": "e_adult_18_64",
                    "label": (
                        "eCPS, full PolicyEngine microsimulation, "
                        "adult 18-64 bridge"
                    ),
                    "scope": "adult_18_64_ecps",
                    "model": "policyengine_microsimulation",
                    "current_law_predicted_recipients": np.nan,
                    "reform_predicted_recipients": np.nan,
                    "newly_eligible_predicted_recipients": float(
                        adult_row["policyengine_new_recipients"]
                    ),
                    "annual_ssi_cost": float(
                        adult_row["policyengine_annual_ssi_cost"]
                    ),
                    "average_gain": float(
                        adult_row[
                            "policyengine_average_cost_per_new_recipient"
                        ]
                    ),
                    "predictors": "full_policyengine_model_and_ecps_inputs",
                }
            )
    return rows


def write_decomposition_outputs(
    results: pd.DataFrame,
    diagnostics: pd.DataFrame,
    output_dir: str | Path,
) -> None:
    """Persist decomposition result and diagnostic tables."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "sipp_decomposition_results.csv", index=False)
    diagnostics.to_csv(
        output / "sipp_decomposition_diagnostics.csv",
        index=False,
    )


def _cbpp_frame_weighted_diagnostics(
    frame: pd.DataFrame,
) -> dict[str, float]:
    if frame.empty:
        return {
            "weighted_participation_rate": 0.0,
            "weighted_mean_income": 0.0,
            "weighted_mean_resources": 0.0,
        }
    weights = frame["weight"].astype(float)
    return {
        "weighted_participation_rate": _weighted_mean(
            frame["participates_ssi_or_ssdi"],
            weights,
        ),
        "weighted_mean_income": _weighted_mean(
            frame["countable_income"],
            weights,
        ),
        "weighted_mean_resources": _weighted_mean(
            frame["countable_assets"],
            weights,
        ),
    }


def _weighted_mean(values, weights) -> float:
    values = pd.Series(values).astype(float)
    weights = pd.Series(weights).astype(float)
    if len(values) == 0 or weights.sum() <= 0:
        return 0.0
    return float(np.average(values, weights=weights))


def _diagnostic_rows(
    step: str,
    diagnostics: dict[str, float | str],
) -> list[dict[str, float | str]]:
    return [
        {"step": step, "metric": metric, "value": value}
        for metric, value in diagnostics.items()
    ]
