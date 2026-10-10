"""Sensitivity: restore CPS-reported Social Security erased by the PUF channel.

PolicyEngine/microcosm#1178: on `puf_tax_detail` support rows the four Social
Security components are replaced by PUF-model predictions, and a zero
prediction erases a benefit the CPS respondent reported (`SS_VAL > 0`).

This script reruns only the households that contain such a person, with the
CPS amount restored, and splices them into a finished certified run. Every
other household's inputs are unchanged, and households are computed
independently, so the spliced tables are what a full run on the repaired
population would give. The restored amount goes to the retirement component
at 62 and over and to the disability component below 62; SSI counts every
component the same way, so the split does not change SSI.

This is a diagnostic. The repaired population is not recalibrated, so its
current-law SSI caseload no longer matches SSA's, and it is never published
as the estimate.

    python scripts/ss_restore_sensitivity.py <certified run dir> <out dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from ssi_asset_limits.microcosm_chunks import ENTITIES, _subset_extra_table
from ssi_asset_limits.microcosm_run import SCENARIOS, sha256_file

COMPONENTS = [
    "social_security_retirement",
    "social_security_disability",
    "social_security_survivors",
    "social_security_dependents",
]


def affected_households(person: pd.DataFrame) -> set:
    modeled = person[COMPONENTS].sum(axis=1)
    erased = (person["SS_VAL"] > 0) & (modeled <= 0)
    return set(person.loc[erased, "person_household_id"])


def restore(person: pd.DataFrame) -> pd.DataFrame:
    person = person.copy()
    modeled = person[COMPONENTS].sum(axis=1)
    erased = (person["SS_VAL"] > 0) & (modeled <= 0)
    older = person["age"] >= 62
    person.loc[erased & older, "social_security_retirement"] = person.loc[
        erased & older, "SS_VAL"
    ]
    person.loc[erased & ~older, "social_security_disability"] = person.loc[
        erased & ~older, "SS_VAL"
    ]
    return person


def build_candidate(chunk_paths: list[str], destination: Path) -> dict:
    """Write one H5 holding only the affected households, repaired."""

    collected: dict[str, list] = {}
    restored_rows = 0
    for path in chunk_paths:
        with pd.HDFStore(path, "r") as store:
            tables = {key: store[key] for key in store.keys()}
        person = tables["/person"]
        households = affected_households(person)
        if not households:
            continue
        keep = person["person_household_id"].isin(households)
        repaired = restore(person.loc[keep])
        restored_rows += int(
            (
                repaired[COMPONENTS].sum(axis=1)
                != person.loc[keep, COMPONENTS].sum(axis=1)
            ).sum()
        )
        selected = {
            "person": set(repaired["person_id"]),
            "household": households,
            "marital_unit": set(repaired["person_marital_unit_id"]),
            "tax_unit": set(repaired["person_tax_unit_id"]),
            "spm_unit": set(repaired["person_spm_unit_id"]),
            "family": set(repaired["person_family_id"]),
        }
        for key, value in tables.items():
            entity = key.strip("/")
            if entity == "person":
                subset = repaired
            elif entity in ENTITIES:
                subset = value.loc[
                    value[f"{entity}_id"].isin(selected[entity])
                ]
            elif key == "/_time_period":
                subset = value
            else:
                subset = _subset_extra_table(value, selected)
            collected.setdefault(key, []).append(subset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with pd.HDFStore(destination, "w", complevel=1, complib="zlib") as out:
        for key, parts in collected.items():
            value = parts[0] if key == "/_time_period" else pd.concat(parts)
            out.put(key, value, format="fixed")
    return {
        "households": int(sum(len(p) for p in collected["/household"])),
        "persons": int(sum(len(p) for p in collected["/person"])),
        "restored_person_rows": restored_rows,
        "sha256": sha256_file(destination),
    }


def run_scenarios(candidate: Path, workers: Path) -> None:
    for scenario in SCENARIOS:
        destination = workers / scenario
        if (destination / "receipt.json").exists():
            continue
        subprocess.run(
            [
                "heavy",
                "--mem",
                "8",
                "--",
                sys.executable,
                "-m",
                "ssi_asset_limits.microcosm_run",
                "_worker",
                "--chunk",
                str(candidate),
                "--scenario",
                scenario,
                "--out-dir",
                str(destination),
            ],
            check=True,
        )


def splice(certified: Path, workers: Path, out_dir: Path) -> None:
    """Replace the affected households' rows in the certified run's tables."""

    from ssi_asset_limits.microcosm_run import _merge_scenarios

    for name, identifier in (
        ("persons", "person_id"),
        ("households", "household_id"),
        ("persons_diagnostics", "person_id"),
    ):
        base = pd.read_csv(certified / f"{name}.csv.gz")
        repaired = _merge_scenarios(workers, name, identifier)
        replaced = base[identifier].isin(repaired[identifier])
        if replaced.sum() != len(repaired):
            raise ValueError(f"{name}: repaired ids do not match the run")
        spliced = pd.concat(
            [base.loc[~replaced], repaired[base.columns]], ignore_index=True
        )
        spliced.to_csv(out_dir / f"{name}.csv.gz", index=False)


def main() -> None:
    certified, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((certified / "run_metadata.json").read_text())
    candidate = out_dir / "chunks" / "affected_households_repaired.h5"
    if not candidate.exists():
        summary = build_candidate(
            metadata["diagnostics"]["chunk_paths"], candidate
        )
        (out_dir / "candidate.json").write_text(json.dumps(summary, indent=2))
    run_scenarios(candidate, out_dir / "workers")
    splice(certified, out_dir / "workers", out_dir)
    provenance = dict(metadata["provenance"])
    provenance["method_note"] += (
        " Sensitivity, not the certified population: households where the "
        "PUF channel erased a CPS-reported Social Security benefit were rerun "
        "with that benefit restored (PolicyEngine/microcosm#1178), without "
        "recalibration."
    )
    diagnostics = dict(metadata["diagnostics"])
    diagnostics["variant"] = "restore_cps_social_security"
    diagnostics["candidate"] = json.loads(
        (out_dir / "candidate.json").read_text()
    )
    (out_dir / "run_metadata.json").write_text(
        json.dumps(
            {"provenance": provenance, "diagnostics": diagnostics}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
