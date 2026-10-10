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


def build_results(
    persons: pd.DataFrame, households: pd.DataFrame, metadata: dict
) -> dict:
    scenarios = []
    for spec in SCENARIOS:
        scenarios.append(
            {
                "key": spec.key,
                "label": spec.label,
                "individual_limit": spec.individual_limit,
                "couple_limit": spec.couple_limit,
                "summary": scenario_summary(persons, households, spec.key),
                "by_age": scenario_by_age(persons, spec.key),
                "resource_bins": scenario_resource_bins(persons, spec.key),
            }
        )
    return {
        "provenance": metadata["provenance"],
        "baseline": baseline_by_age(persons),
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


def publish(run_dir: Path, out_dir: Path, allow_variant: bool = False) -> dict:
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
    write_outputs(results, out_dir)
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("public/data"))
    parser.add_argument("--allow-variant", action="store_true")
    args = parser.parse_args(argv)
    publish(args.run_dir, args.out_dir, args.allow_variant)


if __name__ == "__main__":
    main()
