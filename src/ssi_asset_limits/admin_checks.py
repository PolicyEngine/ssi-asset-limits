"""Check a run's current-law SSI caseload against SSA administrative tables.

Only administrative data is used as the standard. The frame's SSI take-up
flags keep everyone who reported SSI in the CPS and draw everyone else at one
rate per age band. For ages 18-64 and 65 and over that rate is set so that
December 2024 recipients match SSA's counts; too few children qualify to
reach SSA's child count, so the child rate is the share of qualifying
children who report SSI. Agreement in the adult bands therefore shows little.
Everything tabulated here is held out of that targeting: recipients by finer
age band, recipients who also receive Social Security, and recipients by
whether a spouse lives with them and receives SSI.

The module also splits each reform's new recipients into the factors that
produce them (the pool that is eligible apart from resources and fails the
current resource test, the part of that pool the reform admits, and the
take-up flag), by whether they report SSI in the CPS, and by whether they
live with a spouse, so a gap against an outside estimate can be located.

Inputs are a finished run directory (see ``microcosm_run``) and its household
chunks, which carry the frame's Social Security components, marital units
and CPS SSI reports.
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
# category it is compared to. "Spouse does not receive SSI" counts every
# spouse without SSI, including any who would qualify but do not take it up;
# SSA's "ineligible spouse" counts only spouses who do not qualify.
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
    """Hashes of the run tables and the household chunks the checks read."""
    fingerprint = {name: sha256_file(run_dir / name) for name in RUN_FILES}
    metadata = json.loads((run_dir / "run_metadata.json").read_text())
    for path in metadata["diagnostics"]["chunk_paths"]:
        fingerprint[f"chunk:{Path(path).name}"] = sha256_file(Path(path))
    return fingerprint


def _band(age: pd.Series, lower, upper) -> pd.Series:
    mask = pd.Series(True, index=age.index)
    if lower is not None:
        mask &= age >= lower
    if upper is not None:
        mask &= age < upper
    return mask


def _wsum(weights: pd.Series, mask) -> float:
    return float(weights[np.asarray(mask, dtype=bool)].sum())


# CPS-reported SSI. Microcosm's take-up stage keeps a yes for every source
# person who reported SSI, chosen before support rows are pruned, and copies
# it to each support row of that person; a reporter can survive only as a
# PUF support row, which carries the donor's SSI_VAL. So a person reports
# SSI when any row of their source person has SSI_VAL > 0. run_checks
# refuses a run in which such a person lacks the take-up flag.
SSI_REPORT_COLUMN = "SSI_VAL"
SOCIAL_SECURITY_REPORT_COLUMN = "SS_VAL"


def load_frame_inputs(chunk_paths: list[str]) -> pd.DataFrame:
    """Inputs the run does not write: Social Security, units, SSI reports."""
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
                "source_id": person["person_source_id"].to_numpy(),
                "row_reports_ssi": (person[SSI_REPORT_COLUMN] > 0).to_numpy(),
                "reported_social_security": person[
                    SOCIAL_SECURITY_REPORT_COLUMN
                ].to_numpy(),
            }
        )
        frame["marital_unit_size"] = frame.groupby("marital_unit_id")[
            "person_id"
        ].transform("size")
        frames.append(frame)
    inputs = pd.concat(frames, ignore_index=True)
    reporters = set(inputs.loc[inputs["row_reports_ssi"], "source_id"])
    inputs["reports_ssi"] = inputs["source_id"].isin(reporters)
    # Social Security the CPS respondent reported but the frame zeroed
    # (PolicyEngine/microcosm#1178).
    inputs["social_security_erased"] = (
        inputs["reported_social_security"] > 0
    ) & ~inputs["has_social_security"]
    return inputs.drop(columns=["source_id", "row_reports_ssi"])


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


def check_reporters_take_up(persons: pd.DataFrame) -> None:
    """Every CPS SSI reporter must carry the take-up flag the frame sets."""
    unflagged = persons["reports_ssi"] & ~(
        persons[f"takes_up_ssi_if_eligible_{BASELINE}"] > 0
    )
    if unflagged.any():
        raise ValueError(
            f"{int(unflagged.sum())} CPS SSI reporters lack the take-up flag"
        )


def _new_recipients(persons: pd.DataFrame, reform: str) -> pd.Series:
    return (persons[f"ssi_{BASELINE}"] <= 0) & (persons[f"ssi_{reform}"] > 0)


def new_recipients_by_reporting(persons: pd.DataFrame) -> pd.DataFrame:
    """Recipients who report SSI in the CPS, now and among the new ones.

    A new recipient who reports SSI was kept off SSI under current law only
    by imputed savings above the limit, although they report receiving it.
    """
    weights = persons["person_weight"]
    groups = [("current_law", persons[f"ssi_{BASELINE}"] > 0)] + [
        (reform, _new_recipients(persons, reform)) for reform in REFORMS
    ]
    rows = []
    for scenario, recipients in groups:
        for label, lower, upper in POOLED_BANDS:
            band = recipients & _band(persons["age"], lower, upper)
            total = _wsum(weights, band)
            reporting = _wsum(weights, band & persons["reports_ssi"])
            rows.append(
                {
                    "scenario": scenario,
                    "age_band": label,
                    "recipients": total,
                    "reporting_ssi_in_cps": reporting,
                    "share_pct": 100 * reporting / total if total else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _weighted_median(values: pd.Series, weights: pd.Series) -> float:
    if values.empty:
        return 0.0
    order = np.argsort(values.to_numpy())
    cumulative = np.cumsum(weights.to_numpy()[order])
    index = np.searchsorted(cumulative, cumulative[-1] / 2)
    return float(values.to_numpy()[order][index])


def new_recipients_with_erased_social_security(
    persons: pd.DataFrame,
) -> pd.DataFrame:
    """New recipients whose CPS-reported Social Security the frame zeroed."""
    weights = persons["person_weight"]
    erased = persons["social_security_erased"]
    rows = []
    for reform in REFORMS:
        new = _new_recipients(persons, reform)
        for label, lower, upper in POOLED_BANDS:
            band = new & _band(persons["age"], lower, upper)
            affected = band & erased
            total = _wsum(weights, band)
            rows.append(
                {
                    "scenario": reform,
                    "age_band": label,
                    "new_recipients": total,
                    "with_erased_social_security": _wsum(weights, affected),
                    "share_pct": 100 * _wsum(weights, affected) / total
                    if total
                    else 0.0,
                    "records": int(affected.sum()),
                    "median_reported_social_security": _weighted_median(
                        persons.loc[affected, "reported_social_security"],
                        weights[affected],
                    ),
                }
            )
    return pd.DataFrame(rows)


def new_recipients_by_marital_status(persons: pd.DataFrame) -> pd.DataFrame:
    """Each reform's new recipients by whether a spouse lives with them."""
    weights = persons["person_weight"]
    married = persons["marital_unit_size"] == 2
    rows = []
    for reform in REFORMS:
        new = _new_recipients(persons, reform)
        for label, lower, upper in [*POOLED_BANDS, ("All ages", None, None)]:
            band = new & _band(persons["age"], lower, upper)
            total = _wsum(weights, band)
            with_spouse = _wsum(weights, band & married)
            rows.append(
                {
                    "scenario": reform,
                    "age_band": label,
                    "new_recipients": total,
                    "with_spouse": with_spouse,
                    "share_pct": 100 * with_spouse / total if total else 0.0,
                }
            )
    return pd.DataFrame(rows)


def children(persons: pd.DataFrame) -> pd.DataFrame:
    """Why no child gains: disability and savings among children."""
    weights = persons["person_weight"]
    child = persons["age"] < 18
    aged_blind_disabled = persons[f"is_ssi_aged_blind_disabled_{BASELINE}"] > 0
    savings = persons["ssi_countable_resources"]
    measures = {
        "Under 15 and meeting SSI's disability standard": (persons["age"] < 15)
        & (persons[f"meets_ssi_disability_criteria_{BASELINE}"] > 0),
        "Under 18 and aged, blind or disabled": child & aged_blind_disabled,
        "of which with any countable savings": child
        & aged_blind_disabled
        & (savings > 0),
        "of which with countable savings over $2,000": child
        & aged_blind_disabled
        & (savings > 2_000),
        "Under 18 and receiving SSI under current law": child
        & (persons[f"ssi_{BASELINE}"] > 0),
    }
    return pd.DataFrame(
        [
            {
                "measure": measure,
                "records": int(np.asarray(mask, dtype=bool).sum()),
                "weighted": _wsum(weights, mask),
            }
            for measure, mask in measures.items()
        ]
    )


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
    check_reporters_take_up(persons)
    tables = {
        "recipients_by_fine_age": recipients_by_fine_age(persons),
        "recipients_with_social_security": recipients_with_social_security(
            persons
        ),
        "recipients_by_marital_status": recipients_by_marital_status(persons),
        "resources_of_the_eligible": resources_of_the_eligible(persons),
        "new_recipient_decomposition": new_recipient_decomposition(persons),
        "new_recipients_by_reporting": new_recipients_by_reporting(persons),
        "new_recipients_by_marital_status": new_recipients_by_marital_status(
            persons
        ),
        "children": children(persons),
        "new_recipients_with_erased_social_security": (
            new_recipients_with_erased_social_security(persons)
        ),
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
