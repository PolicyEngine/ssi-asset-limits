"""Check a run's current-law SSI caseload against SSA administrative tables.

Only administrative data is used as the standard. The frame's SSI take-up
draws are set so that December 2024 recipients in three pooled age bands
(under 18, 18-64, 65 and over) match SSA's counts. The release enforces the
two adult bands; the child band falls far short because the frame has almost
no disabled children. Agreement in the adult bands therefore shows little.
Everything tabulated here is held out of that targeting: recipients by finer
age band, recipients who also receive Social Security, and recipients by
whether a spouse lives with them and receives SSI.

The module also splits each reform's new recipients into the factors that
produce them (the pool that is eligible apart from resources and fails the
current resource test, the part of that pool the reform admits, and the
take-up flag), so a gap against an outside estimate can be located.

Inputs are a finished run directory (see ``microcosm_run``) and its household
chunks, which carry the frame's Social Security components.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .calculators import RESOURCE_BINS
from .microcosm_run import sha256_file

BASELINE = "baseline"
REFORMS = ("ten_twenty", "no_limit")

# SSA, Annual Statistical Supplement 2025, Table 7.E3: recipients of federally
# administered payments, December 2024, percentage distribution by age.
SSA_7E3_URL = (
    "https://www.ssa.gov/policy/docs/statcomps/supplement/2025/7e.html"
)
SSA_FEDERALLY_ADMINISTERED_DEC_2024 = 7_423_856
SSA_AGE_SHARES = [
    ("Under 5", 0, 5, 1.7),
    ("5-9", 5, 10, 4.2),
    ("10-14", 10, 15, 4.6),
    ("15-17", 15, 18, 2.9),
    ("18-21", 18, 22, 3.9),
    ("22-29", 22, 30, 7.2),
    ("30-39", 30, 40, 9.1),
    ("40-49", 40, 50, 8.6),
    ("50-59", 50, 60, 14.0),
    ("60-64", 60, 65, 10.5),
    ("65-69", 65, 70, 10.2),
    ("70-74", 70, 75, 8.2),
    ("75-79", 75, 80, 6.1),
    ("80 or older", 80, None, 8.7),
]

# SSA, SSI Annual Statistical Report 2024, Table 9: federally administered
# recipients with Social Security benefits, December 2024, by age.
SSA_ASR_SECT02_URL = (
    "https://www.ssa.gov/policy/docs/statcomps/ssi_asr/2024/sect02.html"
)
SSA_WITH_SOCIAL_SECURITY = {
    "Under 18": (56_705, 1_002_887),
    "18-64": (1_080_790, 3_951_866),
    "65 or older": (1_410_664, 2_469_103),
}

# Same report, Table 12: recipients by marital status (ineligible spouses are
# not counted as recipients). Each model category is paired with the SSA
# category it is compared to. The model has no SSI eligibility status for a
# spouse who does not receive SSI, so "spouse does not receive SSI" also
# counts eligible spouses who do not take it up; SSA's "ineligible spouse"
# does not.
SSA_MARITAL = {
    "No spouse": 6_817_742,
    "Eligible spouse": 424_996,
    "Ineligible spouse": 181_118,
}
MARITAL_CATEGORIES = [
    ("No spouse", "No spouse"),
    ("Spouse also receives SSI", "Eligible spouse"),
    ("Spouse does not receive SSI", "Ineligible spouse"),
]

POOLED_BANDS = [
    ("Under 18", None, 18),
    ("18-64", 18, 65),
    ("65 or older", 65, None),
]
SOCIAL_SECURITY_COLUMNS = [
    "social_security_retirement",
    "social_security_disability",
    "social_security_survivors",
    "social_security_dependents",
]


# The run outputs every table here is computed from. ``run_checks`` records
# their hashes so the publisher can refuse tables from a different run.
RUN_FILES = ("persons.csv.gz", "persons_diagnostics.csv.gz")
FINGERPRINT_FILE = "run_fingerprint.json"


def run_fingerprint(run_dir: Path) -> dict[str, str]:
    return {name: sha256_file(run_dir / name) for name in RUN_FILES}


def _band(age: pd.Series, lower, upper) -> pd.Series:
    mask = pd.Series(True, index=age.index)
    if lower is not None:
        mask &= age >= lower
    if upper is not None:
        mask &= age < upper
    return mask


def _wsum(weights: pd.Series, mask) -> float:
    return float(weights[np.asarray(mask, dtype=bool)].sum())


def load_frame_inputs(chunk_paths: list[str]) -> pd.DataFrame:
    """Inputs the run does not write: Social Security and unit size."""
    frames = []
    for path in chunk_paths:
        with pd.HDFStore(path, "r") as store:
            person = store["/person"]
        frame = pd.DataFrame(
            {
                "person_id": person["person_id"].to_numpy(),
                "has_social_security": (
                    person[SOCIAL_SECURITY_COLUMNS].sum(axis=1) > 0
                ).to_numpy(),
                "marital_unit_id": person["person_marital_unit_id"].to_numpy(),
            }
        )
        frame["marital_unit_size"] = frame.groupby("marital_unit_id")[
            "person_id"
        ].transform("size")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def recipients_by_fine_age(persons: pd.DataFrame) -> pd.DataFrame:
    weights = persons["person_weight"]
    recipient = persons[f"ssi_{BASELINE}"] > 0
    total = _wsum(weights, recipient)
    rows = []
    for label, lower, upper, ssa_share in SSA_AGE_SHARES:
        count = _wsum(weights, recipient & _band(persons["age"], lower, upper))
        rows.append(
            {
                "age_band": label,
                "policyengine_recipients": count,
                "policyengine_share_pct": 100 * count / total,
                "ssa_share_pct": ssa_share,
                "ssa_recipients": ssa_share
                / 100
                * SSA_FEDERALLY_ADMINISTERED_DEC_2024,
            }
        )
    frame = pd.DataFrame(rows)
    frame["policyengine_over_ssa"] = (
        frame["policyengine_recipients"] / frame["ssa_recipients"]
    )
    return frame


def recipients_with_social_security(persons: pd.DataFrame) -> pd.DataFrame:
    weights = persons["person_weight"]
    recipient = persons[f"ssi_{BASELINE}"] > 0
    rows = []
    for label, lower, upper in POOLED_BANDS:
        band = recipient & _band(persons["age"], lower, upper)
        both = _wsum(weights, band & persons["has_social_security"])
        everyone = _wsum(weights, band)
        ssa_both, ssa_all = SSA_WITH_SOCIAL_SECURITY[label]
        rows.append(
            {
                "age_band": label,
                "policyengine_recipients": everyone,
                "policyengine_with_social_security": both,
                "policyengine_share_pct": 100 * both / everyone
                if everyone
                else 0.0,
                "ssa_with_social_security": ssa_both,
                "ssa_share_pct": 100 * ssa_both / ssa_all,
            }
        )
    return pd.DataFrame(rows)


def recipients_by_marital_status(persons: pd.DataFrame) -> pd.DataFrame:
    """Recipients by whether a spouse lives with them and receives SSI.

    A spouse counts as receiving SSI when the other member of the person's
    marital unit has positive current-law SSI. Whether the pair files a joint
    claim (``ssi_claim_is_joint``) is not used: it tests aged, blind or
    disabled status, not payment.
    """
    if persons["marital_unit_size"].max() > 2:
        raise ValueError("a marital unit has more than two people")
    weights = persons["person_weight"]
    recipient = persons[f"ssi_{BASELINE}"] > 0
    married = persons["marital_unit_size"] == 2
    recipients_in_unit = recipient.groupby(
        persons["marital_unit_id"]
    ).transform("sum")
    partner_receives = married & (recipients_in_unit == 2)
    masks = {
        "No spouse": recipient & ~married,
        "Spouse also receives SSI": recipient & partner_receives,
        "Spouse does not receive SSI": recipient & married & ~partner_receives,
    }
    total = _wsum(weights, recipient)
    ssa_total = sum(SSA_MARITAL.values())
    return pd.DataFrame(
        [
            {
                "marital_status": label,
                "ssa_category": ssa_label,
                "policyengine_recipients": _wsum(weights, masks[label]),
                "policyengine_share_pct": 100
                * _wsum(weights, masks[label])
                / total,
                "ssa_recipients": SSA_MARITAL[ssa_label],
                "ssa_share_pct": 100 * SSA_MARITAL[ssa_label] / ssa_total,
            }
            for label, ssa_label in MARITAL_CATEGORIES
        ]
    )


def eligible_apart_from_resources(persons: pd.DataFrame) -> pd.Series:
    """People the engine would pay with no resource test, take-up aside.

    Under the no-limit scenario the resource test always passes, so
    ``is_ssi_eligible`` is the aged, blind or disabled and immigration tests,
    and a positive benefit rate less countable income is the income test.
    """
    eligible = persons[f"is_ssi_eligible_{REFORMS[1]}"] > 0
    payable = (
        persons[f"ssi_amount_if_eligible_{REFORMS[1]}"]
        - persons[f"ssi_countable_income_{REFORMS[1]}"]
    ) > 0
    return eligible & payable


def resources_of_the_eligible(persons: pd.DataFrame) -> pd.DataFrame:
    weights = persons["person_weight"]
    pool = eligible_apart_from_resources(persons)
    rows = []
    for label, lower, upper in POOLED_BANDS:
        band = pool & _band(persons["age"], lower, upper)
        total = _wsum(weights, band)
        for resource_bin in RESOURCE_BINS:
            mask = band & resource_bin.mask(persons["ssi_countable_resources"])
            count = _wsum(weights, mask)
            rows.append(
                {
                    "age_band": label,
                    "own_countable_resources": resource_bin.label,
                    "people": count,
                    "share_pct": 100 * count / total if total else 0.0,
                }
            )
        zero = _wsum(weights, band & (persons["ssi_countable_resources"] == 0))
        rows.append(
            {
                "age_band": label,
                "own_countable_resources": "of which exactly $0",
                "people": zero,
                "share_pct": 100 * zero / total if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def new_recipient_decomposition(persons: pd.DataFrame) -> pd.DataFrame:
    """Factor each reform's new recipients by age band.

    pool = eligible apart from resources; excluded = pool members who fail
    the current resource test; admitted = excluded members who pass the
    reform's test; new recipients = admitted members whose take-up flag is
    true (the model's own count of new recipients is reported beside it).
    """
    weights = persons["person_weight"]
    pool = eligible_apart_from_resources(persons)
    fails_now = persons[f"meets_ssi_resource_test_{BASELINE}"] < 1
    takes_up = persons[f"takes_up_ssi_if_eligible_{BASELINE}"] > 0
    rows = []
    for reform in REFORMS:
        passes_reform = persons[f"meets_ssi_resource_test_{reform}"] >= 1
        new = (persons[f"ssi_{BASELINE}"] <= 0) & (
            persons[f"ssi_{reform}"] > 0
        )
        for label, lower, upper in POOLED_BANDS:
            band = _band(persons["age"], lower, upper)
            excluded = _wsum(weights, band & pool & fails_now)
            admitted = _wsum(weights, band & pool & fails_now & passes_reform)
            claiming = _wsum(
                weights, band & pool & fails_now & passes_reform & takes_up
            )
            rows.append(
                {
                    "scenario": reform,
                    "age_band": label,
                    "eligible_apart_from_resources": _wsum(
                        weights, band & pool
                    ),
                    "of_which_recipients_now": _wsum(
                        weights, band & pool & (persons[f"ssi_{BASELINE}"] > 0)
                    ),
                    "excluded_by_resource_test": excluded,
                    "admitted_by_reform": admitted,
                    "admitted_with_take_up_flag": claiming,
                    "take_up_rate_among_admitted_pct": 100
                    * claiming
                    / admitted
                    if admitted
                    else 0.0,
                    "model_new_recipients": _wsum(weights, band & new),
                }
            )
    return pd.DataFrame(rows)


def pool_definition_check(persons: pd.DataFrame) -> pd.DataFrame:
    """How well the pool reproduces the engine's own no-limit recipients.

    With no resource test, a pool member whose take-up flag is true should
    be exactly a person the engine pays. Disagreements measure the error in
    reconstructing the income test from annual totals.
    """
    weights = persons["person_weight"]
    pool = eligible_apart_from_resources(persons)
    takes_up = persons[f"takes_up_ssi_if_eligible_{BASELINE}"] > 0
    paid = persons[f"ssi_{REFORMS[1]}"] > 0
    return pd.DataFrame(
        [
            {
                "paid_with_no_limit": _wsum(weights, paid),
                "pool_with_take_up_flag": _wsum(weights, pool & takes_up),
                "paid_but_not_in_pool": _wsum(
                    weights, paid & ~(pool & takes_up)
                ),
                "in_pool_but_not_paid": _wsum(
                    weights, pool & takes_up & ~paid
                ),
            }
        ]
    )


def run_checks(run_dir: Path, out_dir: Path) -> dict[str, pd.DataFrame]:
    persons = pd.read_csv(run_dir / "persons.csv.gz")
    diagnostics = pd.read_csv(run_dir / "persons_diagnostics.csv.gz")
    metadata = json.loads((run_dir / "run_metadata.json").read_text())
    inputs = load_frame_inputs(metadata["diagnostics"]["chunk_paths"])
    keep = [c for c in diagnostics.columns if c not in persons.columns]
    persons = persons.merge(
        diagnostics[["person_id", *keep]], on="person_id", validate="1:1"
    ).merge(inputs, on="person_id", validate="1:1", suffixes=("", "_input"))
    if "marital_unit_id_input" in persons:
        # The run records marital units too; they must be the frame's.
        if not persons["marital_unit_id"].equals(
            persons["marital_unit_id_input"]
        ):
            raise ValueError("run and frame disagree on marital units")
        persons = persons.drop(columns="marital_unit_id_input")
    tables = {
        "recipients_by_fine_age": recipients_by_fine_age(persons),
        "recipients_with_social_security": recipients_with_social_security(
            persons
        ),
        "recipients_by_marital_status": recipients_by_marital_status(persons),
        "resources_of_the_eligible": resources_of_the_eligible(persons),
        "new_recipient_decomposition": new_recipient_decomposition(persons),
        "pool_definition_check": pool_definition_check(persons),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
    (out_dir / FINGERPRINT_FILE).write_text(
        json.dumps(run_fingerprint(run_dir), indent=2) + "\n"
    )
    return tables


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    for name, table in run_checks(args.run_dir, args.out_dir).items():
        print(f"\n== {name}")
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
