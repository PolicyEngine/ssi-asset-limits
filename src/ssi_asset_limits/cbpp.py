"""CBPP public-method replication helpers.

CBPP's public appendix gives exact rounded target results and the adult
18-64 participation equation. It does not publish the child or 65+ equations,
so this module preserves that distinction instead of filling in hidden
coefficients.

Source:
https://www.cbpp.org/research/social-security/the-case-for-updating-ssi-asset-limits
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, log, sqrt
from pathlib import Path
from typing import Iterable
from urllib.request import urlretrieve

import numpy as np
import pandas as pd

from .constants import OACT_TEN_TWENTY_2026_FEDERAL_SSI_COST

CBPP_SOURCE_URL = (
    "https://www.cbpp.org/research/social-security/"
    "the-case-for-updating-ssi-asset-limits"
)
SIPP_2014_W2_PAGE_URL = (
    "https://www.census.gov/programs-surveys/sipp/data/datasets/"
    "2014-panel/wave-2.html"
)
SIPP_2014_W2_PRIMARY_URL = (
    "https://www2.census.gov/programs-surveys/sipp/data/datasets/"
    "2014/w2/pu2014w2.csv.gz"
)
SIPP_2014_W2_SCHEMA_URL = (
    "https://www2.census.gov/programs-surveys/sipp/data/datasets/"
    "2014/w2/pu2014w2_schema.json"
)
SIPP_2023_DATA_PAGE_URL = (
    "https://www.census.gov/programs-surveys/sipp/data/datasets/"
    "2023-data/2023.html"
)

TEN_TWENTY = "ten_twenty"
TEN_TWENTY_EXCLUDING_RETIREMENT = "ten_twenty_excluding_retirement"
HUNDRED_TWO_HUNDRED = "hundred_two_hundred"
HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT = (
    "hundred_two_hundred_excluding_retirement"
)
NO_LIMIT = "no_limit"

TOTAL_ALL_AGES = "total_all_ages"
CHILDREN_UNDER_18 = "children_under_18"
ADULTS_18_64 = "adults_18_64"
ELDERLY_65_PLUS = "elderly_65_plus"


@dataclass(frozen=True)
class CBPPScenario:
    key: str
    label: str
    individual_limit: float | None
    couple_limit: float | None
    excludes_retirement_accounts: bool = False


@dataclass(frozen=True)
class CBPPSippFormat:
    key: str
    label: str
    required_columns: tuple[str, ...]
    observed_status_columns: tuple[str, ...]
    ssi_receipt_column: str
    default_monthly_fbr: float
    source_description: str
    source_url: str


CBPP_SCENARIOS: dict[str, CBPPScenario] = {
    TEN_TWENTY: CBPPScenario(
        key=TEN_TWENTY,
        label="$10,000 / $20,000",
        individual_limit=10_000,
        couple_limit=20_000,
    ),
    TEN_TWENTY_EXCLUDING_RETIREMENT: CBPPScenario(
        key=TEN_TWENTY_EXCLUDING_RETIREMENT,
        label="$10,000 / $20,000 excluding retirement",
        individual_limit=10_000,
        couple_limit=20_000,
        excludes_retirement_accounts=True,
    ),
    HUNDRED_TWO_HUNDRED: CBPPScenario(
        key=HUNDRED_TWO_HUNDRED,
        label="$100,000 / $200,000",
        individual_limit=100_000,
        couple_limit=200_000,
    ),
    HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT: CBPPScenario(
        key=HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        label="$100,000 / $200,000 excluding retirement",
        individual_limit=100_000,
        couple_limit=200_000,
        excludes_retirement_accounts=True,
    ),
    NO_LIMIT: CBPPScenario(
        key=NO_LIMIT,
        label="No resource limit",
        individual_limit=None,
        couple_limit=None,
    ),
}


CBPP_TARGET_ROWS = [
    # Age groups.
    (TEN_TWENTY, "age", TOTAL_ALL_AGES, "Total, all ages", 224_000, 3),
    (TEN_TWENTY, "age", CHILDREN_UNDER_18, "Children, under 18", 23_000, 2),
    (TEN_TWENTY, "age", ADULTS_18_64, "Adults, aged 18-64", 154_000, 3),
    (
        TEN_TWENTY,
        "age",
        ELDERLY_65_PLUS,
        "Elderly, aged 65 and over",
        None,
        None,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "age",
        TOTAL_ALL_AGES,
        "Total, all ages",
        263_000,
        3,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "age",
        CHILDREN_UNDER_18,
        "Children, under 18",
        23_000,
        2,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "age",
        ADULTS_18_64,
        "Adults, aged 18-64",
        176_000,
        4,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "age",
        ELDERLY_65_PLUS,
        "Elderly, aged 65 and over",
        None,
        None,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "age",
        TOTAL_ALL_AGES,
        "Total, all ages",
        380_000,
        5,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "age",
        CHILDREN_UNDER_18,
        "Children, under 18",
        47_000,
        4,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "age",
        ADULTS_18_64,
        "Adults, aged 18-64",
        248_000,
        5,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "age",
        ELDERLY_65_PLUS,
        "Elderly, aged 65 and over",
        86_000,
        4,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "age",
        TOTAL_ALL_AGES,
        "Total, all ages",
        403_000,
        5,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "age",
        CHILDREN_UNDER_18,
        "Children, under 18",
        47_000,
        4,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "age",
        ADULTS_18_64,
        "Adults, aged 18-64",
        257_000,
        5,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "age",
        ELDERLY_65_PLUS,
        "Elderly, aged 65 and over",
        99_000,
        5,
    ),
    (NO_LIMIT, "age", TOTAL_ALL_AGES, "Total, all ages", 462_000, 6),
    (NO_LIMIT, "age", CHILDREN_UNDER_18, "Children, under 18", 49_000, 4),
    (NO_LIMIT, "age", ADULTS_18_64, "Adults, aged 18-64", 298_000, 6),
    (
        NO_LIMIT,
        "age",
        ELDERLY_65_PLUS,
        "Elderly, aged 65 and over",
        115_000,
        5,
    ),
    # Race and ethnicity groups.
    (TEN_TWENTY, "race_ethnicity", "white", "White", 153_000, 4),
    (TEN_TWENTY, "race_ethnicity", "black", "Black", 30_000, 2),
    (TEN_TWENTY, "race_ethnicity", "asian", "Asian", None, None),
    (TEN_TWENTY, "race_ethnicity", "latino", "Latino", 28_000, 2),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "white",
        "White",
        188_000,
        5,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "black",
        "Black",
        30_000,
        2,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "asian",
        "Asian",
        None,
        None,
    ),
    (
        TEN_TWENTY_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "latino",
        "Latino",
        32_000,
        2,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "race_ethnicity",
        "white",
        "White",
        247_000,
        6,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "race_ethnicity",
        "black",
        "Black",
        39_000,
        2,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "race_ethnicity",
        "asian",
        "Asian",
        30_000,
        9,
    ),
    (
        HUNDRED_TWO_HUNDRED,
        "race_ethnicity",
        "latino",
        "Latino",
        41_000,
        3,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "white",
        "White",
        269_000,
        7,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "black",
        "Black",
        39_000,
        2,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "asian",
        "Asian",
        30_000,
        9,
    ),
    (
        HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT,
        "race_ethnicity",
        "latino",
        "Latino",
        41_000,
        3,
    ),
    (NO_LIMIT, "race_ethnicity", "white", "White", 316_000, 8),
    (NO_LIMIT, "race_ethnicity", "black", "Black", 39_000, 2),
    (NO_LIMIT, "race_ethnicity", "asian", "Asian", 36_000, 10),
    (NO_LIMIT, "race_ethnicity", "latino", "Latino", 41_000, 3),
]


ADULT_18_64_PUBLIC_EQUATION = [
    ("log_countable_income", 0.18),
    ("log_countable_assets", -0.04),
    ("age", 0.02),
    ("prevented_from_work", 0.79),
    ("difficulty_errands_alone", 0.28),
    ("serious_difficulty_walking_or_climbing_stairs", -0.19),
    ("any_six_core_disability_measure", 0.37),
    ("condition_limits_kind_or_amount_work", 0.62),
    ("disability_or_health_condition_income", 0.53),
    ("education_category", -0.32),
    ("married", -0.37),
    ("not_us_citizen", -0.94),
]

CBPP_ADULT_18_64_PREDICTORS = [
    predictor for predictor, _coefficient in ADULT_18_64_PUBLIC_EQUATION
]

# Census SIPP status flags 0 and 1 are not imputed; 9 marks recodes whose
# status can be inferred from component flags. Values 2-8 are imputations.
SIPP_STATUS_OBSERVED_VALUES = {0, 1, 9}
SIPP_2014_W2_REQUIRED_COLUMNS = [
    "SSUID",
    "PNUM",
    "MONTHCODE",
    "WPFINWGT",
    "TAGE",
    "AAGE",
    "RSSICOV",
    "ASSICOV",
    "ESSRSN2YN",
    "ASSRSNYN",
    "TPTOTINC",
    "APTOTINC",
    "TVAL_BANK",
    "TVAL_STMF",
    "TVAL_BOND",
    "AVAL_BANK",
    "AVAL_STMF",
    "AVAL_BOND",
    "EJOBCANT",
    "AJOBCANT",
    "EERRANDS",
    "AERRANDS",
    "EAMBULAT",
    "AAMBULAT",
    "RDIS",
    "EHEARING",
    "AHEARING",
    "ESEEING",
    "ASEEING",
    "ECOGNIT",
    "ACOGNIT",
    "ESELFCARE",
    "ASELFCARE",
    "EDISABL",
    "ADISABL",
    "EDISANY",
    "ADISANY",
    "EEDUC",
    "AEDUC",
    "EMS",
    "ECITIZEN",
    "ACITIZEN",
]

CBPP_ADULT_18_64_OBSERVED_STATUS_COLUMNS = [
    "AAGE",
    "ASSICOV",
    "ASSRSNYN",
    "APTOTINC",
    "AVAL_BANK",
    "AVAL_STMF",
    "AVAL_BOND",
    "AJOBCANT",
    "AERRANDS",
    "AAMBULAT",
    "AHEARING",
    "ASEEING",
    "ACOGNIT",
    "ASELFCARE",
    "ADISABL",
    "ADISANY",
    "AEDUC",
    "ACITIZEN",
]

SIPP_2023_CALENDAR_REQUIRED_COLUMNS = [
    column
    for column in SIPP_2014_W2_REQUIRED_COLUMNS
    if column not in ("RSSICOV", "ASSICOV")
] + [
    "RSSI_YRYN",
    "ASSI_YRYN",
]

CBPP_ADULT_18_64_OBSERVED_STATUS_COLUMNS_2023 = [
    column
    for column in CBPP_ADULT_18_64_OBSERVED_STATUS_COLUMNS
    if column != "ASSICOV"
] + ["ASSI_YRYN"]

SIPP_FORMAT_2014_WAVE2 = "2014-wave2"
SIPP_FORMAT_2023_CALENDAR = "2023-calendar"
CBPP_SIPP_FORMATS = {
    SIPP_FORMAT_2014_WAVE2: CBPPSippFormat(
        key=SIPP_FORMAT_2014_WAVE2,
        label="2014 SIPP Wave 2",
        required_columns=tuple(SIPP_2014_W2_REQUIRED_COLUMNS),
        observed_status_columns=tuple(
            CBPP_ADULT_18_64_OBSERVED_STATUS_COLUMNS
        ),
        ssi_receipt_column="RSSICOV",
        default_monthly_fbr=721.0,
        source_description="2014 SIPP panel Wave 2",
        source_url=SIPP_2014_W2_PRIMARY_URL,
    ),
    SIPP_FORMAT_2023_CALENDAR: CBPPSippFormat(
        key=SIPP_FORMAT_2023_CALENDAR,
        label="2023 SIPP calendar-year file",
        required_columns=tuple(SIPP_2023_CALENDAR_REQUIRED_COLUMNS),
        observed_status_columns=tuple(
            CBPP_ADULT_18_64_OBSERVED_STATUS_COLUMNS_2023
        ),
        ssi_receipt_column="RSSI_YRYN",
        default_monthly_fbr=841.0,
        source_description="2023 SIPP release, reference year 2022",
        source_url=SIPP_2023_DATA_PAGE_URL,
    ),
}


def infer_sipp_format_from_columns(columns: Iterable[str]) -> str:
    """Infer the supported SIPP format from available column names."""

    available = set(columns)
    if {"RSSICOV", "ASSICOV"}.issubset(available):
        return SIPP_FORMAT_2014_WAVE2
    if {"RSSI_YRYN", "ASSI_YRYN"}.issubset(available):
        return SIPP_FORMAT_2023_CALENDAR
    raise ValueError(
        "Could not infer SIPP format. Expected 2014 Wave 2 columns "
        "RSSICOV/ASSICOV or 2023 calendar columns RSSI_YRYN/ASSI_YRYN."
    )


def cbpp_public_targets() -> pd.DataFrame:
    """Return CBPP's rounded public Table 1 target values."""

    rows = []
    for (
        scenario,
        dimension,
        group,
        label,
        new_beneficiaries,
        percent_change,
    ) in CBPP_TARGET_ROWS:
        rows.append(
            {
                "scenario": scenario,
                "scenario_label": CBPP_SCENARIOS[scenario].label,
                "dimension": dimension,
                "group": group,
                "label": label,
                "new_beneficiaries": new_beneficiaries,
                "percent_change": percent_change,
                "status": (
                    "published"
                    if new_beneficiaries is not None
                    else "not_published_reliability"
                ),
                "source_url": CBPP_SOURCE_URL,
            }
        )
    return pd.DataFrame(rows)


def cbpp_adult_18_64_coefficients() -> pd.DataFrame:
    """Return the adult 18-64 coefficients CBPP published."""

    return pd.DataFrame(
        [
            {
                "age_group": ADULTS_18_64,
                "predictor": predictor,
                "coefficient": coefficient,
                "status": "published",
                "source_url": CBPP_SOURCE_URL,
            }
            for predictor, coefficient in ADULT_18_64_PUBLIC_EQUATION
        ]
        + [
            {
                "age_group": "children_under_18_or_elderly_65_plus",
                "predictor": "full_equation",
                "coefficient": pd.NA,
                "status": "not_published_by_cbpp",
                "source_url": CBPP_SOURCE_URL,
            }
        ]
    )


def infer_cbpp_scenario_key(
    individual_limit: float,
    couple_limit: float,
    excludes_retirement_accounts: bool = False,
) -> str:
    """Infer the CBPP scenario that matches the requested resource limits."""

    if individual_limit >= 1e11 and couple_limit >= 1e11:
        return NO_LIMIT
    if individual_limit == 10_000 and couple_limit == 20_000:
        return (
            TEN_TWENTY_EXCLUDING_RETIREMENT
            if excludes_retirement_accounts
            else TEN_TWENTY
        )
    if individual_limit == 100_000 and couple_limit == 200_000:
        return (
            HUNDRED_TWO_HUNDRED_EXCLUDING_RETIREMENT
            if excludes_retirement_accounts
            else HUNDRED_TWO_HUNDRED
        )
    raise ValueError(
        "CBPP only published target rows for $10k/$20k, "
        "$100k/$200k, and no-limit scenarios."
    )


def cbpp_age_targets(
    scenario_key: str = TEN_TWENTY,
    infer_unpublished_from_total: bool = True,
) -> pd.DataFrame:
    """Return CBPP age targets, optionally inferring unpublished residuals."""

    targets = cbpp_public_targets()
    age_targets = targets[
        (targets["scenario"] == scenario_key) & (targets["dimension"] == "age")
    ].copy()

    if infer_unpublished_from_total:
        total = age_targets.loc[
            age_targets["group"] == TOTAL_ALL_AGES, "new_beneficiaries"
        ].iloc[0]
        published_groups = age_targets[
            (age_targets["group"] != TOTAL_ALL_AGES)
            & age_targets["new_beneficiaries"].notna()
        ]
        residual = float(total) - float(
            published_groups["new_beneficiaries"].sum()
        )
        missing_mask = (age_targets["group"] != TOTAL_ALL_AGES) & age_targets[
            "new_beneficiaries"
        ].isna()
        if missing_mask.sum() == 1:
            age_targets.loc[missing_mask, "new_beneficiaries"] = residual
            age_targets.loc[missing_mask, "status"] = (
                "inferred_from_total_minus_published_age_groups"
            )

    return age_targets.reset_index(drop=True)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def adult_18_64_participation_index(records: pd.DataFrame) -> pd.Series:
    """Calculate CBPP's public adult 18-64 probit index.

    CBPP did not publish an intercept. The returned value is therefore the
    public linear index, not a fully calibrated probability.
    """

    index = pd.Series(0.0, index=records.index)
    for predictor, coefficient in ADULT_18_64_PUBLIC_EQUATION:
        if predictor not in records:
            raise KeyError(f"Missing CBPP adult predictor: {predictor}")
        index = index + records[predictor].fillna(0) * coefficient
    return index


def adult_18_64_public_probability(records: pd.DataFrame) -> pd.Series:
    """Convert the public adult 18-64 index to a normal-CDF probability."""

    return adult_18_64_participation_index(records).map(_normal_cdf)


def log_positive(value: float) -> float:
    """Natural log transform for positive values, with zero mapped to zero."""

    if value <= 0:
        return 0.0
    return log(value)


def download_sipp_2014_wave2(data_dir: str | Path) -> Path:
    """Download Census SIPP 2014 Wave 2 schema and primary CSV if needed."""

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    schema_path = data_path / "pu2014w2_schema.json"
    primary_path = data_path / "pu2014w2.csv.gz"

    if not schema_path.exists():
        urlretrieve(SIPP_2014_W2_SCHEMA_URL, schema_path)
    if not primary_path.exists():
        urlretrieve(SIPP_2014_W2_PRIMARY_URL, primary_path)

    return primary_path


def read_sipp_2014_wave2(
    sipp_path: str | Path,
    columns: list[str] | None = None,
    nrows: int | None = None,
    chunksize: int | None = None,
) -> pd.DataFrame:
    """Read selected columns from the SIPP 2014 Wave 2 pipe file."""

    return pd.read_csv(
        sipp_path,
        sep="|",
        usecols=columns,
        nrows=nrows,
        chunksize=chunksize,
        low_memory=False,
    )


def _yes(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").eq(1)


def _nonnegative(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.where(numeric > 0, 0)


def _observed_status_mask(data: pd.DataFrame, columns: list[str]) -> pd.Series:
    mask = pd.Series(True, index=data.index)
    for column in columns:
        values = pd.to_numeric(data[column], errors="coerce")
        mask &= values.isin(SIPP_STATUS_OBSERVED_VALUES)
    return mask


def build_cbpp_adult_18_64_training_frame(
    data: pd.DataFrame,
    *,
    observed_only: bool = True,
    monthly_fbr: float | None = None,
    income_limit_multiple: float = 2.0,
    sipp_format: str = SIPP_FORMAT_2014_WAVE2,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build an adult 18-64 SIPP frame for refitting CBPP's probit.

    This follows CBPP's public description where possible: income-eligible
    people, separate adult age group, and exclusion of rows with imputed key
    data. The current public-use implementation uses a simple income screen
    rather than full SSI spouse/parent deeming.
    """

    format_config = CBPP_SIPP_FORMATS[sipp_format]
    if monthly_fbr is None:
        monthly_fbr = format_config.default_monthly_fbr

    working = data.copy()
    diagnostics = {"raw_rows": float(len(working))}

    working = working[
        pd.to_numeric(working["MONTHCODE"], errors="coerce").eq(12)
    ]
    diagnostics["december_rows"] = float(len(working))

    age = pd.to_numeric(working["TAGE"], errors="coerce")
    working = working[age.between(18, 64, inclusive="both")]
    diagnostics["adult_18_64_rows"] = float(len(working))

    monthly_income = _nonnegative(working["TPTOTINC"])
    income_eligible = monthly_income <= monthly_fbr * income_limit_multiple
    working = working[income_eligible]
    diagnostics["income_eligible_rows"] = float(len(working))

    if observed_only:
        observed_mask = _observed_status_mask(
            working,
            list(format_config.observed_status_columns),
        )
        working = working[observed_mask]
    diagnostics["observed_rows"] = float(len(working))

    frame = pd.DataFrame(index=working.index)
    frame["participates_ssi_or_ssdi"] = (
        _yes(working[format_config.ssi_receipt_column])
        | _yes(working["ESSRSN2YN"])
    ).astype(int)
    frame["countable_income"] = monthly_income.loc[working.index]
    frame["log_countable_income"] = frame["countable_income"].map(log_positive)
    resources = (
        _nonnegative(working["TVAL_BANK"])
        + _nonnegative(working["TVAL_STMF"])
        + _nonnegative(working["TVAL_BOND"])
    )
    frame["countable_assets"] = resources
    frame["log_countable_assets"] = frame["countable_assets"].map(log_positive)
    frame["age"] = pd.to_numeric(working["TAGE"], errors="coerce")
    frame["prevented_from_work"] = _yes(working["EJOBCANT"]).astype(int)
    frame["difficulty_errands_alone"] = _yes(working["EERRANDS"]).astype(int)
    frame["serious_difficulty_walking_or_climbing_stairs"] = _yes(
        working["EAMBULAT"]
    ).astype(int)
    frame["any_six_core_disability_measure"] = (
        _yes(working["RDIS"])
        | _yes(working["EHEARING"])
        | _yes(working["ESEEING"])
        | _yes(working["ECOGNIT"])
        | _yes(working["EAMBULAT"])
        | _yes(working["ESELFCARE"])
        | _yes(working["EERRANDS"])
    ).astype(int)
    frame["condition_limits_kind_or_amount_work"] = _yes(
        working["EDISABL"]
    ).astype(int)
    frame["disability_or_health_condition_income"] = _yes(
        working["EDISANY"]
    ).astype(int)
    frame["education_category"] = pd.to_numeric(
        working["EEDUC"], errors="coerce"
    )
    frame["married"] = pd.to_numeric(working["EMS"], errors="coerce").eq(1)
    frame["married"] = frame["married"].astype(int)
    frame["not_us_citizen"] = pd.to_numeric(
        working["ECITIZEN"], errors="coerce"
    ).eq(2)
    frame["not_us_citizen"] = frame["not_us_citizen"].astype(int)
    frame["weight"] = pd.to_numeric(working["WPFINWGT"], errors="coerce")

    frame = frame.dropna()
    frame = frame[frame["weight"] > 0]
    diagnostics["fit_rows"] = float(len(frame))
    diagnostics["sipp_format"] = format_config.key
    diagnostics["sipp_format_label"] = format_config.label
    diagnostics["monthly_fbr"] = monthly_fbr
    diagnostics["weighted_participation_rate"] = _weighted_mean(
        frame["participates_ssi_or_ssdi"],
        frame["weight"],
    )
    diagnostics["weighted_mean_income"] = _weighted_mean(
        monthly_income.loc[frame.index],
        frame["weight"],
    )
    diagnostics["weighted_mean_resources"] = _weighted_mean(
        resources.loc[frame.index],
        frame["weight"],
    )

    return frame, diagnostics


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    if len(values) == 0:
        return 0.0
    return float(
        np.average(values.astype(float), weights=weights.astype(float))
    )


def fit_cbpp_adult_18_64_probit(
    training_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fit CBPP's adult 18-64 probit specification from a training frame."""

    import statsmodels.api as sm

    x = training_frame[CBPP_ADULT_18_64_PREDICTORS]
    x = sm.add_constant(x, has_constant="add")
    y = training_frame["participates_ssi_or_ssdi"]
    weights = training_frame["weight"]
    weights = weights / weights.mean()

    model = sm.GLM(
        y,
        x,
        family=sm.families.Binomial(link=sm.families.links.Probit()),
        freq_weights=weights,
    )
    result = model.fit()

    coefficients = pd.DataFrame(
        {
            "term": result.params.index,
            "coefficient": result.params.values,
            "standard_error": result.bse.values,
            "p_value": result.pvalues.values,
            "published_cbpp_coefficient": [
                dict(ADULT_18_64_PUBLIC_EQUATION).get(term, pd.NA)
                for term in result.params.index
            ],
        }
    )
    published = pd.to_numeric(
        coefficients["published_cbpp_coefficient"],
        errors="coerce",
    )
    coefficients["coefficient_minus_published"] = (
        coefficients["coefficient"] - published
    )
    diagnostics = {
        "converged": bool(result.converged),
        "nobs": float(result.nobs),
        "weight_normalization": "mean_one",
        "deviance": float(result.deviance),
        "pearson_chi2": float(result.pearson_chi2),
    }
    return coefficients, diagnostics


def calculate_cbpp_adult_18_64_scenario_counts(
    training_frame: pd.DataFrame,
    coefficients: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate adult 18-64 counts in CBPP's public asset scenarios."""

    probabilities = predict_cbpp_adult_18_64_probability(
        training_frame,
        coefficients,
    )
    weights = training_frame["weight"].astype(float)
    weighted_probabilities = probabilities * weights
    current_limit = np.where(
        training_frame["married"].astype(bool),
        3_000,
        2_000,
    )
    assets = training_frame["countable_assets"].astype(float)
    current_mask = assets <= current_limit

    rows = [
        _cbpp_scenario_count_row(
            scenario="current_law",
            label="Current-law resource limit",
            mask=current_mask,
            weighted_probabilities=weighted_probabilities,
        )
    ]
    for scenario_key in (TEN_TWENTY, HUNDRED_TWO_HUNDRED, NO_LIMIT):
        scenario = CBPP_SCENARIOS[scenario_key]
        if scenario.individual_limit is None or scenario.couple_limit is None:
            scenario_limit = np.full(len(training_frame), np.inf)
        else:
            scenario_limit = np.where(
                training_frame["married"].astype(bool),
                scenario.couple_limit,
                scenario.individual_limit,
            )
        scenario_mask = assets <= scenario_limit
        new_mask = (~current_mask) & scenario_mask
        rows.append(
            _cbpp_scenario_count_row(
                scenario=scenario_key,
                label=scenario.label,
                mask=new_mask,
                weighted_probabilities=weighted_probabilities,
            )
        )
    return pd.DataFrame(rows)


def predict_cbpp_adult_18_64_probability(
    training_frame: pd.DataFrame,
    coefficients: pd.DataFrame,
) -> pd.Series:
    """Predict adult 18-64 participation probabilities."""

    coefficient_by_term = coefficients.set_index("term")["coefficient"].astype(
        float
    )
    index = pd.Series(
        coefficient_by_term.get("const", 0.0),
        index=training_frame.index,
        dtype=float,
    )
    for predictor in CBPP_ADULT_18_64_PREDICTORS:
        index += (
            training_frame[predictor].astype(float)
            * coefficient_by_term[predictor]
        )
    return index.map(_normal_cdf)


def _cbpp_scenario_count_row(
    *,
    scenario: str,
    label: str,
    mask: pd.Series | np.ndarray,
    weighted_probabilities: pd.Series,
) -> dict[str, float | str]:
    count = float(weighted_probabilities[mask].sum())
    return {
        "scenario": scenario,
        "label": label,
        "adult_18_64_predicted_beneficiaries": count,
    }


def calculate_cbpp_age_bridge(
    policyengine_age_impacts: pd.DataFrame,
    scenario_key: str = TEN_TWENTY,
    oact_annual_cost: float | None = None,
) -> pd.DataFrame:
    """Bridge PolicyEngine age impacts to CBPP's public age targets."""

    if oact_annual_cost is None and scenario_key == TEN_TWENTY:
        oact_annual_cost = OACT_TEN_TWENTY_2026_FEDERAL_SSI_COST

    targets = cbpp_age_targets(scenario_key)
    pe = policyengine_age_impacts.set_index("age_group")
    rows = []

    for target in targets.to_dict("records"):
        age_group = target["group"]
        if age_group == TOTAL_ALL_AGES:
            continue
        pe_row = pe.loc[age_group]
        pe_new = float(pe_row["policyengine_new_recipients"])
        pe_cost = float(pe_row["policyengine_annual_ssi_cost"])
        cbpp_new = float(target["new_beneficiaries"])
        pe_average_cost = 0.0 if pe_new == 0 else pe_cost / pe_new
        rows.append(
            {
                "scenario": scenario_key,
                "age_group": age_group,
                "label": target["label"],
                "policyengine_new_recipients": pe_new,
                "policyengine_annual_ssi_cost": pe_cost,
                "policyengine_average_cost_per_new_recipient": pe_average_cost,
                "cbpp_new_beneficiaries": cbpp_new,
                "cbpp_target_status": target["status"],
                "new_beneficiary_scale": 0.0
                if pe_new == 0
                else cbpp_new / pe_new,
                "cbpp_matched_annual_ssi_cost": cbpp_new * pe_average_cost,
                "oact_benefit_amount_scale": pd.NA,
            }
        )

    total_row = _total_bridge_row(rows, scenario_key, oact_annual_cost)
    return pd.DataFrame(rows + [total_row])


def _total_bridge_row(
    rows: Iterable[dict],
    scenario_key: str,
    oact_annual_cost: float | None,
) -> dict:
    rows = list(rows)
    pe_new = sum(row["policyengine_new_recipients"] for row in rows)
    pe_cost = sum(row["policyengine_annual_ssi_cost"] for row in rows)
    cbpp_new = sum(row["cbpp_new_beneficiaries"] for row in rows)
    cbpp_cost = sum(row["cbpp_matched_annual_ssi_cost"] for row in rows)
    return {
        "scenario": scenario_key,
        "age_group": TOTAL_ALL_AGES,
        "label": "Total, all ages",
        "policyengine_new_recipients": pe_new,
        "policyengine_annual_ssi_cost": pe_cost,
        "policyengine_average_cost_per_new_recipient": (
            0.0 if pe_new == 0 else pe_cost / pe_new
        ),
        "cbpp_new_beneficiaries": cbpp_new,
        "cbpp_target_status": "published_total_with_age_residuals",
        "new_beneficiary_scale": 0.0 if pe_new == 0 else cbpp_new / pe_new,
        "cbpp_matched_annual_ssi_cost": cbpp_cost,
        "oact_benefit_amount_scale": (
            pd.NA
            if cbpp_cost == 0 or oact_annual_cost is None
            else oact_annual_cost / cbpp_cost
        ),
    }
