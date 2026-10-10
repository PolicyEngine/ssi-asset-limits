"""Turn a microsimulation run's person and household tables into app data.

A run directory holds the outputs of one execution of all scenarios on one
population (see ``microcosm_run``):

- ``persons.csv.gz``: one row per person with ``person_id``,
  ``household_id``, ``person_weight``, ``age``, ``ssi_countable_resources``
  and, for every scenario ``s``, ``ssi_<s>``, ``in_poverty_<s>`` and
  ``in_deep_poverty_<s>``.
- ``households.csv.gz``: one row per household with ``household_id``,
  ``household_weight`` and, for every scenario, ``household_net_income_<s>``,
  ``snap_<s>`` and ``income_tax_<s>``.
- ``run_metadata.json``: provenance written by the runner.

Every figure published here is a weighted sum or share over these rows; none
is scaled from another run.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .calculators import CBPP_AGE_GROUPS, RESOURCE_BINS
from .comparators import (
    CBPP_CITATION,
    CBPP_DATA_YEAR,
    CBPP_NEW_BENEFICIARIES,
    CBPP_URL,
    OACT_LETTERS,
    SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024,
    SSA_SSI_MONTHLY_DEC_2024_LABEL,
    SSA_SSI_MONTHLY_DEC_2024_URL,
)
from .precision import scenario_precision

BASELINE = "baseline"


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    label: str
    individual_limit: float | None
    couple_limit: float | None


SCENARIOS = [
    ScenarioSpec("ten_twenty", "$10,000 / $20,000 limits", 10_000, 20_000),
    ScenarioSpec("no_limit", "No limit", None, None),
]

AGE_LABELS = {
    "children_under_18": "Under 18",
    "adults_18_64": "18 to 64",
    "elderly_65_plus": "65 and over",
}

CBPP_NOTES = {
    ("ten_twenty", "elderly_65_plus"): (
        "CBPP did not publish this row (sample too small); its total less "
        "its other rows leaves about 47,000, but its rows may not sum."
    ),
}


def _age_mask(age: pd.Series, lower: float | None, upper: float | None):
    mask = pd.Series(True, index=age.index)
    if lower is not None:
        mask &= age >= lower
    if upper is not None:
        mask &= age < upper
    return mask


def _wsum(weights: pd.Series, values) -> float:
    return float(np.dot(weights.to_numpy(), np.asarray(values, dtype=float)))


def scenario_summary(
    persons: pd.DataFrame, households: pd.DataFrame, key: str
) -> list[dict]:
    """Headline metrics for one reform scenario against the baseline."""

    w = persons["person_weight"]
    base_ssi = persons[f"ssi_{BASELINE}"]
    ref_ssi = persons[f"ssi_{key}"]
    change = ref_ssi - base_ssi
    gainers = change > 0
    base_rec = base_ssi > 0
    ref_rec = ref_ssi > 0
    hw = households["household_weight"]

    def hdiff(column: str) -> float:
        return _wsum(
            hw,
            households[f"{column}_{key}"] - households[f"{column}_{BASELINE}"],
        )

    gain_weight = float(w[gainers].sum())
    base_pov = persons[f"in_poverty_{BASELINE}"].astype(bool)
    ref_pov = persons[f"in_poverty_{key}"].astype(bool)
    base_deep = persons[f"in_deep_poverty_{BASELINE}"].astype(bool)
    ref_deep = persons[f"in_deep_poverty_{key}"].astype(bool)
    total_weight = float(w.sum())

    rows = [
        (
            "annual_ssi_cost",
            "Added federal SSI, 2026",
            _wsum(w, change),
            "currency",
        ),
        (
            "new_recipients",
            "New SSI recipients",
            _wsum(w, ~base_rec & ref_rec),
            "people",
        ),
        (
            "average_gain",
            "Average gain per person who gains",
            0.0
            if gain_weight == 0
            else _wsum(w[gainers], change[gainers]) / gain_weight,
            "currency",
        ),
        (
            "people_lifted_from_poverty",
            "People moved above the SPM poverty line",
            _wsum(w, base_pov & ~ref_pov),
            "people",
        ),
        (
            "poverty_rate_reduction",
            "Fall in the SPM poverty rate",
            (_wsum(w, base_pov) - _wsum(w, ref_pov)) / total_weight,
            "rate",
        ),
        (
            "deep_poverty_rate_reduction",
            "Fall in the deep poverty rate",
            (_wsum(w, base_deep) - _wsum(w, ref_deep)) / total_weight,
            "rate",
        ),
        (
            "baseline_recipients",
            "SSI recipients, current law",
            _wsum(w, base_rec),
            "people",
        ),
        (
            "reform_recipients",
            "SSI recipients after the change",
            _wsum(w, ref_rec),
            "people",
        ),
        (
            "net_fiscal_cost",
            "Change in household net income",
            hdiff("household_net_income"),
            "currency",
        ),
        ("snap_change", "Change in SNAP benefits", hdiff("snap"), "currency"),
        (
            "income_tax_change",
            "Change in income tax",
            hdiff("income_tax"),
            "currency",
        ),
    ]
    return [
        {"metric": m, "label": label, "value": float(v), "unit": unit}
        for m, label, v, unit in rows
    ]


def scenario_by_age(persons: pd.DataFrame, key: str) -> list[dict]:
    """New recipients and added SSI by age group, with CBPP's figures."""

    w = persons["person_weight"]
    base_ssi = persons[f"ssi_{BASELINE}"]
    ref_ssi = persons[f"ssi_{key}"]
    new = (base_ssi <= 0) & (ref_ssi > 0)
    change = ref_ssi - base_ssi
    cbpp = CBPP_NEW_BENEFICIARIES.get(key, {})
    rows = []
    for group, _, lower, upper in CBPP_AGE_GROUPS:
        mask = _age_mask(persons["age"], lower, upper)
        rows.append(
            {
                "age_group": group,
                "label": AGE_LABELS[group],
                "new_recipients": _wsum(w, new & mask),
                "annual_ssi_cost": _wsum(w, change.where(mask, 0.0)),
                "cbpp_new_beneficiaries": cbpp.get(group),
                "cbpp_note": CBPP_NOTES.get((key, group), ""),
            }
        )
    rows.append(
        {
            "age_group": "total_all_ages",
            "label": "All ages",
            "new_recipients": _wsum(w, new),
            "annual_ssi_cost": _wsum(w, change),
            "cbpp_new_beneficiaries": cbpp.get("total_all_ages"),
            "cbpp_note": "",
        }
    )
    return rows


def scenario_resource_bins(persons: pd.DataFrame, key: str) -> list[dict]:
    """Added SSI by each person's own countable resources under current law."""

    w = persons["person_weight"]
    resources = persons["ssi_countable_resources"]
    change = persons[f"ssi_{key}"] - persons[f"ssi_{BASELINE}"]
    rows = []
    for resource_bin in RESOURCE_BINS:
        mask = resource_bin.mask(resources)
        people = _wsum(w, mask)
        added = _wsum(w, change.where(mask, 0.0))
        rows.append(
            {
                "resource_bin": resource_bin.label,
                "people": people,
                "ssi_increase": added,
                "average_gain": 0.0 if people == 0 else added / people,
            }
        )
    return rows


def baseline_by_age(persons: pd.DataFrame) -> dict:
    """Current-law SSI recipients by age, next to SSA's December 2024 count."""

    w = persons["person_weight"]
    base_ssi = persons[f"ssi_{BASELINE}"]
    rows = []
    for group, _, lower, upper in CBPP_AGE_GROUPS:
        mask = _age_mask(persons["age"], lower, upper)
        rows.append(
            {
                "age_group": group,
                "label": AGE_LABELS[group],
                "policyengine_recipients": _wsum(w, (base_ssi > 0) & mask),
                "ssa_recipients": SSA_FEDERAL_PAYMENT_RECIPIENTS_DEC_2024[
                    group
                ],
            }
        )
    return {
        "ssa_source_label": SSA_SSI_MONTHLY_DEC_2024_LABEL,
        "ssa_source_url": SSA_SSI_MONTHLY_DEC_2024_URL,
        "by_age": rows,
        "total_recipients": _wsum(w, base_ssi > 0),
        "total_federal_ssi": _wsum(w, base_ssi),
    }


def comparators() -> dict:
    return {
        "cbpp": {
            "citation": CBPP_CITATION,
            "url": CBPP_URL,
            "data_year": CBPP_DATA_YEAR,
            "note": (
                "CBPP modeled the chance of claiming SSI or SSDI among people "
                f"with incomes low enough to qualify, using {CBPP_DATA_YEAR} "
                "SIPP data scaled to SSA's caseload by age, with couple "
                "limits twice the individual limit. Figures are rounded to "
                "the nearest 1,000."
            ),
        },
        "oact": [
            {
                **{k: v for k, v in letter.items() if k != "annual"},
                "annual": [
                    {"year": year, "billions": value}
                    for year, value in sorted(letter["annual"].items())
                ],
            }
            for letter in OACT_LETTERS
        ],
    }


PRECISION_NOTE = (
    "Ranges are the 5th to 95th percentiles of a household bootstrap with "
    "2,000 replicates. They show only how much the estimate could move if "
    "the population sample were redrawn; uncertainty in the imputed savings, "
    "the claiming flags, the weights and the rules is not included."
)


def with_precision(by_age: list[dict], precision: pd.DataFrame) -> list[dict]:
    """Attach each row's sampling range and record counts."""

    table = precision.set_index(["statistic", "age_group"])
    rows = []
    for row in by_age:
        new = table.loc[("new_recipients", row["age_group"])]
        cost = table.loc[("annual_ssi_cost", row["age_group"])]
        rows.append(
            {
                **row,
                "new_recipients_low": float(new["low"]),
                "new_recipients_high": float(new["high"]),
                "annual_ssi_cost_low": float(cost["low"]),
                "annual_ssi_cost_high": float(cost["high"]),
                "new_recipient_records": int(new["records"]),
                "new_recipient_effective_records": float(
                    new["effective_records"]
                ),
            }
        )
    return rows


def build_results(
    persons: pd.DataFrame, households: pd.DataFrame, metadata: dict
) -> dict:
    scenarios = []
    baseline_records = None
    for spec in SCENARIOS:
        precision = scenario_precision(persons, spec.key)
        if baseline_records is None:
            baseline_records = precision[
                precision.statistic == "baseline_recipients"
            ].set_index("age_group")
        scenarios.append(
            {
                "key": spec.key,
                "label": spec.label,
                "individual_limit": spec.individual_limit,
                "couple_limit": spec.couple_limit,
                "summary": scenario_summary(persons, households, spec.key),
                "by_age": with_precision(
                    scenario_by_age(persons, spec.key), precision
                ),
                "resource_bins": scenario_resource_bins(persons, spec.key),
            }
        )
    baseline = baseline_by_age(persons)
    for row in baseline["by_age"]:
        row["records"] = int(baseline_records.loc[row["age_group"], "records"])
    return {
        "provenance": metadata["provenance"],
        "precision_note": PRECISION_NOTE,
        "baseline": baseline,
        "scenarios": scenarios,
        "comparators": comparators(),
    }


def write_outputs(results: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    )
    for scenario in results["scenarios"]:
        for table in ("summary", "by_age", "resource_bins"):
            pd.DataFrame(scenario[table]).to_csv(
                out_dir / f"{scenario['key']}_{table}.csv", index=False
            )
    pd.DataFrame(results["baseline"]["by_age"]).to_csv(
        out_dir / "baseline_by_age.csv", index=False
    )


HELD_OUT_TABLES = {
    "recipients_by_fine_age": [
        "age_band",
        "policyengine_recipients",
        "ssa_recipients",
    ],
    "recipients_with_social_security": [
        "age_band",
        "policyengine_share_pct",
        "ssa_share_pct",
    ],
    "recipients_by_marital_status": [
        "marital_status",
        "policyengine_share_pct",
        "ssa_share_pct",
    ],
}


def held_out_checks(checks_dir: Path) -> dict:
    """Tables written by ``admin_checks`` for the same run, for the page."""

    return {
        name: pd.read_csv(checks_dir / f"{name}.csv")[columns].to_dict(
            orient="records"
        )
        for name, columns in HELD_OUT_TABLES.items()
    }


SENSITIVITY_LABELS = {
    "restore_cps_social_security": (
        "Social Security that the population file erased, restored",
        "Reruns the 3,566 households in which the population file set a "
        "person's CPS-reported Social Security to zero "
        "(PolicyEngine/microcosm#1178), with the benefit restored. Weights "
        "are not recalibrated, so the current-law caseload no longer "
        "matches SSA's.",
    ),
    "resource_deeming": (
        "A spouse's and a parent's savings counted, as SSA does",
        "Adds federal resource deeming (20 CFR 416.1202) to the certified "
        "engine as a reform, ahead of the policyengine-us change that adds "
        "it (PolicyEngine/policyengine-us#3557).",
    ),
}


def sensitivity(run_dir: Path) -> dict:
    """Headline rows of one sensitivity run, for comparison on the page."""

    persons = pd.read_csv(run_dir / "persons.csv.gz")
    metadata = json.loads((run_dir / "run_metadata.json").read_text())
    variant = metadata["diagnostics"]["variant"]
    label, description = SENSITIVITY_LABELS[variant]
    return {
        "key": variant,
        "label": label,
        "description": description,
        "baseline_by_age": baseline_by_age(persons)["by_age"],
        "scenarios": [
            {
                "key": spec.key,
                "by_age": [
                    {
                        key: row[key]
                        for key in (
                            "age_group",
                            "label",
                            "new_recipients",
                            "annual_ssi_cost",
                        )
                    }
                    for row in scenario_by_age(persons, spec.key)
                ],
            }
            for spec in SCENARIOS
        ],
    }


def publish(
    run_dir: Path,
    out_dir: Path,
    allow_variant: bool = False,
    checks_dir: Path | None = None,
    sensitivity_dirs: list[Path] | None = None,
) -> dict:
    persons = pd.read_csv(run_dir / "persons.csv.gz")
    households = pd.read_csv(run_dir / "households.csv.gz")
    metadata = json.loads((run_dir / "run_metadata.json").read_text())
    variant = metadata.get("diagnostics", {}).get("variant")
    if variant is not None and not allow_variant:
        raise ValueError(
            f"{run_dir} is a sensitivity run ({variant}), not the certified "
            "engine; pass --allow-variant and an output directory other than "
            "public/data to tabulate it"
        )
    results = build_results(persons, households, metadata)
    if checks_dir is not None:
        results["held_out_checks"] = held_out_checks(checks_dir)
    if sensitivity_dirs:
        results["sensitivities"] = [
            sensitivity(path) for path in sensitivity_dirs
        ]
    write_outputs(results, out_dir)
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("public/data"))
    parser.add_argument("--allow-variant", action="store_true")
    parser.add_argument(
        "--checks-dir",
        type=Path,
        help="Directory of admin_checks tables for this run to include.",
    )
    parser.add_argument(
        "--sensitivity",
        type=Path,
        action="append",
        default=[],
        help="A finished sensitivity run to show beside the estimate.",
    )
    args = parser.parse_args(argv)
    publish(
        args.run_dir,
        args.out_dir,
        args.allow_variant,
        args.checks_dir,
        args.sensitivity,
    )


if __name__ == "__main__":
    main()
