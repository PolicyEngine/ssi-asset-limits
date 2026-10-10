"""Reproduce validation checks from a completed certified Microcosm run.

This module reads saved tables only; it never imports or runs the tax model.
Run ``python -m ssi_asset_limits.microcosm_checks RUN_DIRECTORY`` to write the
small ``checks.json`` report. SSI amounts in the person table are annual.
Checks D and E use January 2026 diagnostic flags when the runner records
monthly flags both as annual fractions and as January snapshots.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .comparators import (
    SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024,
    SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL,
    SSA_SSI_MONTHLY_DEC_2024_URL,
)

SCENARIOS = ("baseline", "ten_twenty", "no_limit")
AGE_BANDS = (
    ("under_18", 0, 18, "children_under_18"),
    ("18_64", 18, 65, "adults_18_64"),
    ("65_plus", 65, None, "elderly_65_plus"),
)
DISABILITY_BANDS = (
    ("0_14", 0, 15),
    ("15_17", 15, 18),
    ("18_64", 18, 65),
    ("65_plus", 65, None),
)
JULY_BUILD_P = {
    "model_version": "1.764.6",
    "baseline_recipients": {
        "under_18": 180_000,
        "18_64": 3_800_000,
        "65_plus": 2_310_000,
        "total": 6_290_000,
    },
    "baseline_annual_ssi": 57_900_000_000,
    "ten_twenty": {
        "annual_ssi_change": 3_610_000_000,
        "new_recipients": 516_000,
        "new_recipients_by_age": {
            "under_18": 0,
            "18_64": 153_211,
            "65_plus": 362_628,
        },
    },
    "no_limit": {
        "annual_ssi_change": 6_830_000_000,
        "new_recipients": 947_000,
    },
}


def _weighted(weights: pd.Series, values) -> float:
    return float(np.dot(weights, np.asarray(values, dtype=float)))


def _age_mask(age: pd.Series, lower: int, upper: int | None) -> pd.Series:
    mask = age >= lower
    return mask if upper is None else mask & (age < upper)


def _comparison(value: float, reference: float) -> dict:
    difference = value - reference
    percent = None if reference == 0 else difference / reference
    return {
        "value": float(value),
        "reference": float(reference),
        "difference": float(difference),
        "relative_difference": percent,
        "more_than_10_percent_off": (
            difference != 0 if percent is None else abs(percent) > 0.1
        ),
    }


def baseline_checks(persons: pd.DataFrame) -> dict:
    """A: recipient counts and annual federal SSI against fixed references."""
    weights = persons["person_weight"]
    receives = persons["ssi_baseline"] > 0
    rows = {}
    for label, lower, upper, ssa_label in AGE_BANDS:
        count = _weighted(
            weights, receives & _age_mask(persons["age"], lower, upper)
        )
        rows[label] = {
            "against_ssa": _comparison(
                count, SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024[ssa_label]
            ),
            "against_july_build_p": _comparison(
                count, JULY_BUILD_P["baseline_recipients"][label]
            ),
        }
    count = _weighted(weights, receives)
    rows["total"] = {
        "against_ssa": _comparison(
            count, SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024_TOTAL
        ),
        "against_july_build_p": _comparison(
            count, JULY_BUILD_P["baseline_recipients"]["total"]
        ),
    }
    annual_ssi = _weighted(weights, persons["ssi_baseline"])
    return {
        "recipients": rows,
        "annual_federal_ssi": {
            "against_ssa": _comparison(annual_ssi, 5_230_000_000 * 12),
            "against_july_build_p": _comparison(
                annual_ssi, JULY_BUILD_P["baseline_annual_ssi"]
            ),
        },
        "ssa_source_url": SSA_SSI_MONTHLY_DEC_2024_URL,
        "comparison_note": (
            "2026 annual model recipients are compared with December 2024 "
            "federal-payment recipients; the approximate $5.23 billion "
            "December payment is multiplied by 12. July Build P figures "
            "are the earlier run supplied with this analysis, some rounded."
        ),
    }


def reform_checks(persons: pd.DataFrame) -> dict:
    """B: annual SSI and new-recipient changes, including age partitions."""
    weights = persons["person_weight"]
    baseline = persons["ssi_baseline"]
    results = {}
    for scenario in SCENARIOS[1:]:
        reform = persons[f"ssi_{scenario}"]
        change = reform - baseline
        new = (baseline <= 0) & (reform > 0)
        rows = {}
        reference = JULY_BUILD_P[scenario]
        for label, lower, upper, _ in AGE_BANDS:
            mask = _age_mask(persons["age"], lower, upper)
            new_recipients = _weighted(weights, new & mask)
            row = {
                "annual_ssi_change": _weighted(weights, change.where(mask, 0)),
                "new_recipients": new_recipients,
            }
            if label in reference.get("new_recipients_by_age", {}):
                row["new_recipients_against_july_build_p"] = _comparison(
                    new_recipients, reference["new_recipients_by_age"][label]
                )
            rows[label] = row
        results[scenario] = {
            "annual_ssi_change": _comparison(
                _weighted(weights, change), reference["annual_ssi_change"]
            ),
            "new_recipients": _comparison(
                _weighted(weights, new), reference["new_recipients"]
            ),
            "by_age": rows,
        }
    return results


def _flag(
    diagnostics: pd.DataFrame, variable: str, scenario: str
) -> pd.Series:
    column = f"{variable}_{scenario}"
    january_column = f"{column}_january"
    if january_column in diagnostics:
        column = january_column
    if column not in diagnostics and variable in diagnostics:
        column = variable
    if column not in diagnostics:
        raise ValueError(f"Missing diagnostic column: {column}")
    values = diagnostics[column]
    if values.isna().any() or not values.isin([True, False, 0, 1]).all():
        raise ValueError(f"Diagnostic column must contain booleans: {column}")
    return values.astype(bool)


def _rate(weights: pd.Series, values, mask: pd.Series) -> float | None:
    total = float(weights[mask].sum())
    return (
        None if total == 0 else _weighted(weights[mask], values[mask]) / total
    )


def frame_checks(
    persons: pd.DataFrame,
    households: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> dict:
    """D: resources, disability, take-up and ABD population facts."""
    weights = persons["person_weight"]
    resources = persons["ssi_countable_resources"]
    nonzero = (resources != 0).groupby(persons["household_id"]).sum()
    household_counts = households["household_id"].map(nonzero).fillna(0)
    household_weights = households["household_weight"]
    distribution = []
    for count in sorted(household_counts.unique()):
        mask = household_counts == count
        weighted_households = float(household_weights[mask].sum())
        distribution.append(
            {
                "persons_with_nonzero_resources": int(count),
                "households": int(mask.sum()),
                "weighted_households": weighted_households,
                "weighted_household_share": (
                    weighted_households / float(household_weights.sum())
                ),
            }
        )
    disability = []
    disabled = _flag(diagnostics, "is_disabled", "baseline")
    disability_criteria = _flag(
        diagnostics, "meets_ssi_disability_criteria", "baseline"
    )
    for label, lower, upper in DISABILITY_BANDS:
        mask = _age_mask(persons["age"], lower, upper)
        disability.append(
            {
                "age_band": label,
                "weighted_persons": float(weights[mask].sum()),
                "is_disabled_rate": _rate(weights, disabled, mask),
                "meets_ssi_disability_criteria_rate": _rate(
                    weights, disability_criteria, mask
                ),
            }
        )
    takeup = {}
    abd = {}
    baseline_eligible = _flag(diagnostics, "is_ssi_eligible", "baseline")
    for scenario in SCENARIOS:
        takes_up = _flag(diagnostics, "takes_up_ssi_if_eligible", scenario)
        aged_blind_disabled = _flag(
            diagnostics, "is_ssi_aged_blind_disabled", scenario
        )
        takeup_rows = []
        abd_rows = []
        for label, lower, upper, _ in AGE_BANDS:
            mask = _age_mask(persons["age"], lower, upper)
            eligible_mask = mask & baseline_eligible
            takeup_rows.append(
                {
                    "age_band": label,
                    "overall_true_rate": _rate(weights, takes_up, mask),
                    "baseline_eligible_true_rate": _rate(
                        weights, takes_up, eligible_mask
                    ),
                    "weighted_baseline_eligible_persons": float(
                        weights[eligible_mask].sum()
                    ),
                }
            )
            abd_rows.append(
                {
                    "age_band": label,
                    "weighted_abd_persons": _weighted(
                        weights, aged_blind_disabled & mask
                    ),
                }
            )
        takeup[scenario] = takeup_rows
        abd[scenario] = abd_rows
    return {
        "flag_period": (
            "January 2026 snapshots when available; annual flags for "
            "variables defined annually. SSI amounts are annual 2026."
        ),
        "weighted_zero_countable_resources_share": _rate(
            weights, resources == 0, pd.Series(True, index=persons.index)
        ),
        "nonzero_resources_per_household": distribution,
        "maximum_persons_per_household_with_nonzero_resources": int(
            household_counts.max()
        ),
        "at_most_one_person_with_nonzero_resources_per_household": bool(
            (household_counts <= 1).all()
        ),
        "negative_resource_person_rows": int((resources < 0).sum()),
        "disability_by_age": disability,
        "takes_up_ssi_if_eligible_by_age": takeup,
        "abd_persons_by_age": abd,
    }


def _aligned_diagnostics(
    persons: pd.DataFrame, diagnostics: pd.DataFrame
) -> pd.DataFrame:
    if persons["person_id"].duplicated().any():
        raise ValueError("Person table contains duplicate person_id values")
    if diagnostics["person_id"].duplicated().any():
        raise ValueError(
            "Diagnostic table contains duplicate person_id values"
        )
    if set(persons["person_id"]) != set(diagnostics["person_id"]):
        raise ValueError(
            "Person and diagnostic tables contain different persons"
        )
    return (
        diagnostics.set_index("person_id")
        .loc[persons["person_id"]]
        .reset_index()
    )


def chunking_checks(metadata: dict) -> dict:
    """C: preserve the runner's full-file nesting and weight proof."""
    diagnostics = metadata["diagnostics"]
    full = diagnostics["full_weight_totals"]
    chunks = diagnostics["summed_chunk_weight_totals"]
    totals = {}
    for entity in ("person", "household"):
        totals[entity] = {
            "full_file": float(full[entity]),
            "summed_chunks": float(chunks[entity]),
            "difference": float(chunks[entity] - full[entity]),
            "equal_within_floating_point_tolerance": bool(
                np.isclose(full[entity], chunks[entity], rtol=1e-12, atol=1e-6)
            ),
        }
    return {"nesting": diagnostics["nesting"], "weight_totals": totals}


def monotonicity_checks(
    persons: pd.DataFrame, diagnostics: pd.DataFrame
) -> tuple[dict, pd.DataFrame]:
    """E: count every decline and retain evidence for its marital-unit cause.

    Classification requires recorded changes in the actual inputs to the SSI
    formulas. An unexplained decline stays unexplained rather than inferring
    a spouse effect from the benefit amounts alone. In certified pe-US 2.2.1,
    joint-claim status depends on ABD status, not the resource test, so simply
    relaxing resources should not create a new couple computation.
    """
    weights = persons["person_weight"]
    baseline = persons["ssi_baseline"]
    marital_unit = diagnostics["marital_unit_id"]
    baseline_eligible = _flag(diagnostics, "is_ssi_eligible", "baseline")
    baseline_counts = baseline_eligible.groupby(marital_unit).transform("sum")
    cases = []
    reports = {}
    flag_cache = {}

    def number(index: int, variable: str, scenario: str) -> float | None:
        column = f"{variable}_{scenario}"
        return (
            float(diagnostics.at[index, column])
            if column in diagnostics
            else None
        )

    def flag(index: int, variable: str, scenario: str) -> bool | None:
        columns = (
            f"{variable}_{scenario}_january",
            f"{variable}_{scenario}",
            variable,
        )
        if not any(column in diagnostics for column in columns):
            return None
        key = (variable, scenario)
        if key not in flag_cache:
            flag_cache[key] = _flag(diagnostics, variable, scenario)
        return bool(flag_cache[key].at[index])

    for scenario in SCENARIOS[1:]:
        change = persons[f"ssi_{scenario}"] - baseline
        loses = change < 0
        reform_eligible = _flag(diagnostics, "is_ssi_eligible", scenario)
        reform_counts = reform_eligible.groupby(marital_unit).transform("sum")
        scenario_cases = []
        for index in persons.index[loses]:
            row = {
                "person_id": persons.at[index, "person_id"],
                "household_id": persons.at[index, "household_id"],
                "marital_unit_id": marital_unit.at[index],
                "scenario": scenario,
                "person_weight": float(weights.at[index]),
                "ssi_baseline": float(baseline.at[index]),
                "ssi_reform": float(persons.at[index, f"ssi_{scenario}"]),
                "annual_ssi_loss": float(-change.at[index]),
                "marital_unit_baseline_eligible_persons": int(
                    baseline_counts.at[index]
                ),
                "marital_unit_reform_eligible_persons": int(
                    reform_counts.at[index]
                ),
            }
            for variable in (
                "ssi_amount_if_eligible",
                "ssi_countable_income",
                "ssi_income_deemed_from_ineligible_spouse",
                "ssi_marital_earned_income",
                "ssi_marital_unearned_income",
            ):
                for key in ("baseline", scenario):
                    row[f"{variable}_{key}"] = number(index, variable, key)
            for variable in (
                "is_ssi_eligible",
                "takes_up_ssi_if_eligible",
                "ssi_claim_is_joint",
                "ssi_couple_computation_applies",
                "is_ssi_spousal_deeming_applies",
            ):
                for key in ("baseline", scenario):
                    row[f"{variable}_{key}"] = flag(index, variable, key)
            takeup_before = row["takes_up_ssi_if_eligible_baseline"]
            takeup_after = row[f"takes_up_ssi_if_eligible_{scenario}"]
            couple_before = row["ssi_couple_computation_applies_baseline"]
            couple_after = row[f"ssi_couple_computation_applies_{scenario}"]
            deeming_before = row["is_ssi_spousal_deeming_applies_baseline"]
            deeming_after = row[f"is_ssi_spousal_deeming_applies_{scenario}"]
            amount_before = row["ssi_amount_if_eligible_baseline"]
            amount_after = row[f"ssi_amount_if_eligible_{scenario}"]
            income_before = row["ssi_countable_income_baseline"]
            income_after = row[f"ssi_countable_income_{scenario}"]
            financial_values = (
                amount_before,
                amount_after,
                income_before,
                income_after,
            )
            financial_match = False
            if all(value is not None for value in financial_values):
                # With no cap, floor(amount minus countable income) must
                # reproduce both annual benefits before naming a mechanism.
                # A varying monthly floor can fail this annual identity;
                # that case remains flagged for monthly investigation.
                financial_match = bool(
                    deeming_before is False
                    and deeming_after is False
                    and np.isclose(
                        max(0, amount_before - income_before),
                        row["ssi_baseline"],
                        rtol=1e-7,
                        atol=0.01,
                    )
                    and np.isclose(
                        max(0, amount_after - income_after),
                        row["ssi_reform"],
                        rtol=1e-7,
                        atol=0.01,
                    )
                )
            row["uncapped_annual_formula_reproduces_both_benefits"] = (
                financial_match
            )
            cause = "unexplained"
            if (
                takeup_before is True
                and takeup_after is False
                and row["ssi_reform"] == 0
            ):
                cause = "takeup_became_false"
            elif (
                baseline_eligible.at[index]
                and not reform_eligible.at[index]
                and row["ssi_reform"] == 0
            ):
                cause = "eligibility_became_false"
            elif (
                couple_before is False
                and couple_after is True
                and reform_counts.at[index] > baseline_counts.at[index]
                and financial_match
                and amount_after < amount_before
            ):
                cause = "spouse_eligible_and_couple_computation_started"
            elif (
                financial_match
                and couple_before == couple_after
                and amount_after == amount_before
                and income_after > income_before
            ):
                # This is a numerical explanation, with the marital income
                # components retained for tracing the source of the increase.
                cause = "recorded_countable_income_increase"
            elif (
                financial_match
                and income_after == income_before
                and amount_after < amount_before
            ):
                cause = "recorded_maximum_benefit_decrease"
            elif row["annual_ssi_loss"] <= 1e-6 and financial_match:
                cause = "floating_point_roundoff"
            row["cause"] = cause
            scenario_cases.append(row)
            cases.append(row)
        grouped = []
        for cause in sorted({row["cause"] for row in scenario_cases}):
            rows = [row for row in scenario_cases if row["cause"] == cause]
            grouped.append(
                {
                    "cause": cause,
                    "person_rows": len(rows),
                    "weighted_persons": sum(r["person_weight"] for r in rows),
                    "annual_ssi_loss": sum(
                        r["person_weight"] * r["annual_ssi_loss"] for r in rows
                    ),
                }
            )
        unknown = [
            row for row in scenario_cases if row["cause"] == "unexplained"
        ]
        unresolved = [
            row
            for row in scenario_cases
            if row["cause"]
            in {
                "unexplained",
                "recorded_countable_income_increase",
                "recorded_maximum_benefit_decrease",
            }
        ]
        reports[scenario] = {
            "person_rows_with_ssi_decline": int(loses.sum()),
            "weighted_persons_with_ssi_decline": _weighted(weights, loses),
            "annual_ssi_loss": _weighted(weights, (-change).where(loses, 0)),
            "causes": grouped,
            "unexplained_person_rows": len(unknown),
            "person_rows_needing_mechanism_investigation": len(unresolved),
            "unexplained_person_ids_first_20": [
                int(row["person_id"]) for row in unknown[:20]
            ],
            "all_ssi_changes_nonnegative": bool(not loses.any()),
        }
    columns = [
        "person_id",
        "household_id",
        "marital_unit_id",
        "scenario",
        "person_weight",
        "ssi_baseline",
        "ssi_reform",
        "annual_ssi_loss",
        "cause",
    ]
    cases_frame = (
        pd.DataFrame(cases) if cases else pd.DataFrame(columns=columns)
    )
    return {
        "scenarios": reports,
        "case_details_file": "monotonicity_cases.csv.gz",
        "classification_note": (
            "January 2026 marital flags and annual benefit components are "
            "retained for every decline. Formula identities must reproduce "
            "both benefits before classifying an amount or income effect. "
            "Joint claims in pe-US 2.2.1 depend on ABD status and tax-unit "
            "roles rather than the resource test, so spouse resource "
            "eligibility alone cannot start couple computation."
        ),
        "model_sources": [
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/"
                "ssi_claim_is_joint.py",
                "lines": [11, 15],
                "finding": (
                    "Joint claim is based on ABD and head/spouse roles."
                ),
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/"
                "ssi_couple_computation_applies.py",
                "lines": [18, 36],
                "finding": (
                    "Couple computation uses joint claim and facility status."
                ),
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/"
                "ssi_amount_if_eligible.py",
                "lines": [28, 41],
                "finding": (
                    "Couple computation sets the base rate to couple rate / 2."
                ),
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/"
                "uncapped_ssi.py",
                "lines": [11, 16],
                "finding": "Eligible person's maximum less countable income.",
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/eligibility/"
                "income/ssi_countable_income.py",
                "lines": [68, 85],
                "finding": (
                    "Countable income halves the couple pool or adds "
                    "spousal deemed income."
                ),
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/"
                "ssi_if_takes_up.py",
                "lines": [20, 39],
                "finding": (
                    "Benefit is floored at zero and capped for "
                    "spousal deeming."
                ),
            },
            {
                "path": "policyengine_us/variables/gov/ssa/ssi/ssi.py",
                "lines": [12, 13],
                "finding": "Payment requires take-up.",
            },
        ],
    }, cases_frame


def write_checks(run_directory: str | Path) -> dict:
    """Read a run and save a deterministic report beside its tables."""
    run = Path(run_directory)
    persons = pd.read_csv(run / "persons.csv.gz")
    households = pd.read_csv(run / "households.csv.gz")
    diagnostics = _aligned_diagnostics(
        persons, pd.read_csv(run / "persons_diagnostics.csv.gz")
    )
    metadata = json.loads((run / "run_metadata.json").read_text())
    monotonicity, cases = monotonicity_checks(persons, diagnostics)
    checks = {
        "A_baseline": baseline_checks(persons),
        "B_reform_deltas": reform_checks(persons),
        "C_chunking": chunking_checks(metadata),
        "D_frame": frame_checks(persons, households, diagnostics),
        "E_monotonicity": monotonicity,
    }
    cases.to_csv(run / "monotonicity_cases.csv.gz", index=False)
    (run / "checks.json").write_text(
        json.dumps(checks, indent=2, allow_nan=False) + "\n"
    )
    (run / "checks.txt").write_text(format_report(checks) + "\n")
    return checks


def format_report(checks: dict) -> str:
    """Concise A–E report with numbers suitable for a run's audit record."""
    lines = []
    baseline = checks["A_baseline"]
    for band, row in baseline["recipients"].items():
        ssa = row["against_ssa"]
        july = row["against_july_build_p"]
        lines.append(
            f"A {band}: {ssa['value']:,.0f} recipients; "
            f"SSA {ssa['reference']:,.0f} "
            f"({ssa['relative_difference']:+.1%}); "
            f"July Build P {july['reference']:,.0f} "
            f"({july['relative_difference']:+.1%}); "
            f">10% SSA discrepancy: {ssa['more_than_10_percent_off']}"
        )
    annual = baseline["annual_federal_ssi"]
    lines.append(
        f"A annual federal SSI: ${annual['against_ssa']['value']:,.0f}; "
        f"SSA annualized ${annual['against_ssa']['reference']:,.0f}; "
        f"July Build P ${annual['against_july_build_p']['reference']:,.0f}"
    )
    for scenario, row in checks["B_reform_deltas"].items():
        lines.append(
            f"B {scenario}: added SSI "
            f"${row['annual_ssi_change']['value']:,.0f}; "
            f"new recipients {row['new_recipients']['value']:,.0f}; "
            f"vs July Build P "
            f"{row['annual_ssi_change']['relative_difference']:+.1%} / "
            f"{row['new_recipients']['relative_difference']:+.1%}"
        )
        for band, age_row in row["by_age"].items():
            lines.append(
                f"B {scenario} {band}: added SSI "
                f"${age_row['annual_ssi_change']:,.0f}; "
                f"new recipients {age_row['new_recipients']:,.0f}"
            )
    for entity, row in checks["C_chunking"]["weight_totals"].items():
        lines.append(
            f"C {entity} weights: full {row['full_file']:.9f}; "
            f"chunks {row['summed_chunks']:.9f}; "
            f"difference {row['difference']:.9g}"
        )
    frame = checks["D_frame"]
    lines.append(
        "D zero countable resources: "
        f"{frame['weighted_zero_countable_resources_share']:.6%}; "
        "maximum persons per household with nonzero resources: "
        f"{frame['maximum_persons_per_household_with_nonzero_resources']}"
    )
    for row in frame["nonzero_resources_per_household"]:
        lines.append(
            f"D households with {row['persons_with_nonzero_resources']} "
            f"nonzero-resource persons: {row['households']:,} rows / "
            f"{row['weighted_households']:,.0f} weighted households "
            f"({row['weighted_household_share']:.6%})"
        )

    def rate(value: float | None) -> str:
        return "n/a (zero denominator)" if value is None else f"{value:.6%}"

    for row in frame["disability_by_age"]:
        lines.append(
            f"D {row['age_band']} disability: "
            f"is_disabled {rate(row['is_disabled_rate'])}; "
            "meets_ssi_disability_criteria "
            f"{rate(row['meets_ssi_disability_criteria_rate'])}"
        )
    for row in frame["takes_up_ssi_if_eligible_by_age"]["baseline"]:
        lines.append(
            f"D {row['age_band']} take-up: "
            f"overall {rate(row['overall_true_rate'])}; "
            f"baseline eligible {rate(row['baseline_eligible_true_rate'])}"
        )
    for row in frame["abd_persons_by_age"]["baseline"]:
        lines.append(
            f"D {row['age_band']} ABD persons: "
            f"{row['weighted_abd_persons']:,.0f}"
        )
    for scenario, row in checks["E_monotonicity"]["scenarios"].items():
        lines.append(
            f"E {scenario} SSI declines: "
            f"{row['person_rows_with_ssi_decline']:,} person rows / "
            f"{row['weighted_persons_with_ssi_decline']:,.0f} weighted "
            f"persons / ${row['annual_ssi_loss']:,.2f}; "
            f"unexplained {row['unexplained_person_rows']:,}; "
            "needing mechanism investigation "
            f"{row['person_rows_needing_mechanism_investigation']:,}"
        )
        for cause in row["causes"]:
            lines.append(
                f"E {scenario} {cause['cause']}: "
                f"{cause['person_rows']:,} person rows / "
                f"${cause['annual_ssi_loss']:,.2f}"
            )
    lines.append(f"D/E flag period: {frame['flag_period']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    arguments = parser.parse_args()
    checks = write_checks(arguments.run_directory)
    print(format_report(checks))


if __name__ == "__main__":
    main()
