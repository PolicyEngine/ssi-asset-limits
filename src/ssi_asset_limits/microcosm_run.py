"""Run the certified US default in exact, isolated household batches.

SSI amounts defined for MONTH are calculated for each of the twelve months
of 2026 and summed; YEAR amounts are calculated for 2026. Monthly diagnostic
booleans are stored as the fraction of those months that are true (and
``*_january`` flags retain January's state for marital-unit checks). Resources
and age are January snapshots when their variables are monthly. Each engine
scenario runs in a fresh process admitted by ``heavy`` (see
``WORKER_MEM_GIB``); an interrupted run resumes from the workers that
finished. No engine calculation runs in the coordinator or unit tests.

Output weights use the model's 2026 weights, including its population
uprating; the separate input partition proof compares the unchanged 2024
frame weights (person weights inherited from households when not stored).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCENARIOS = ("baseline", "ten_twenty", "no_limit")
YEAR = 2026
# Structural reforms that can be layered on the certified engine for a
# sensitivity run: name -> (module, class, what it changes). A run with a
# variant is never the published estimate; ``publish`` refuses it.
VARIANTS = {
    "resource_deeming": (
        "ssi_asset_limits.sensitivity.ssi_resource_deeming_reform",
        "SSIResourceDeemingReform",
        "SSI resource deeming from ineligible spouses and parents "
        "(20 CFR 416.1202) installed on the certified engine as a reform",
    ),
}
# Memory declared to the admission gate for each worker, and the ceiling a
# worker's measured peak may not pass.
WORKER_MEM_GIB = 18
ADMISSION_RETRIES = 5
DATASET_SHA256 = (
    "6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84"
)
PROVENANCE_FIELDS = {
    "analysis_year",
    "policyengine_version",
    "bundle_id",
    "model_package",
    "model_version",
    "dataset",
    "dataset_build_id",
    "dataset_sha256",
    "generated_at",
    "code_commit",
    "method_note",
}
DIAGNOSTIC_FLAGS = (
    "is_ssi_aged_blind_disabled",
    "meets_ssi_resource_test",
    "takes_up_ssi_if_eligible",
    "is_ssi_eligible",
    "is_disabled",
    "meets_ssi_disability_criteria",
)
MARITAL_FLAGS = (
    "ssi_claim_is_joint",
    "ssi_couple_computation_applies",
    "is_ssi_spousal_deeming_applies",
)
MARITAL_AMOUNTS = (
    "ssi_amount_if_eligible",
    "ssi_countable_income",
    "ssi_income_deemed_from_ineligible_spouse",
    "ssi_marital_earned_income",
    "ssi_marital_unearned_income",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def peak_rss_gib() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (2**30 if sys.platform == "darwin" else 2**20)


POVERTY_FLAG_PREFIXES = ("in_poverty_", "in_deep_poverty_")


def is_flag(values: pd.Series) -> bool:
    """True for a boolean column or a numeric column of only 0 and 1."""
    if pd.api.types.is_bool_dtype(values):
        return True
    return bool(
        pd.api.types.is_numeric_dtype(values) and values.isin([0, 1]).all()
    )


def validate_run_frames(
    persons: pd.DataFrame,
    households: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    """Check the publisher's contract and IDs without importing the engine."""
    person_columns = {
        "person_id",
        "household_id",
        "person_weight",
        "age",
        "ssi_countable_resources",
    } | {
        f"{name}_{scenario}"
        for scenario in SCENARIOS
        for name in ("ssi", "in_poverty", "in_deep_poverty")
    }
    household_columns = {"household_id", "household_weight"} | {
        f"{name}_{scenario}"
        for scenario in SCENARIOS
        for name in ("household_net_income", "snap", "income_tax")
    }
    diagnostic_columns = {"person_id"} | {
        f"{name}_{scenario}"
        for scenario in SCENARIOS
        for name in DIAGNOSTIC_FLAGS
    }
    for name, frame, columns, identifier in (
        ("persons", persons, person_columns, "person_id"),
        ("households", households, household_columns, "household_id"),
        ("diagnostics", diagnostics, diagnostic_columns, "person_id"),
    ):
        missing = columns - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing columns {sorted(missing)}")
        if (
            frame[identifier].isna().any()
            or frame[identifier].duplicated().any()
        ):
            raise ValueError(f"{name}: missing or duplicate {identifier}")
        numeric = frame.select_dtypes(include=["number", "bool"])
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError(f"{name}: nonfinite values")
    if set(persons.household_id) != set(households.household_id):
        raise ValueError("persons/households: orphan household_id")
    if set(persons.person_id) != set(diagnostics.person_id):
        raise ValueError("diagnostics: person_id mismatch")
    for frame, name in (
        (persons, "person_weight"),
        (households, "household_weight"),
    ):
        if (frame[name] < 0).any():
            raise ValueError(f"negative {name}")
    for column in persons.columns:
        if column.startswith(POVERTY_FLAG_PREFIXES) and not is_flag(
            persons[column]
        ):
            raise ValueError(f"persons: {column} is not a true/false flag")


def write_run_metadata(
    out_dir: Path, provenance: dict, diagnostics: dict
) -> Path:
    if set(provenance) != PROVENANCE_FIELDS:
        missing = sorted(PROVENANCE_FIELDS - set(provenance))
        extra = sorted(set(provenance) - PROVENANCE_FIELDS)
        raise ValueError(
            f"provenance fields: missing={missing}, extra={extra}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / "run_metadata.json"
    destination.write_text(
        json.dumps(
            {"provenance": provenance, "diagnostics": diagnostics},
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    return destination


def certified_provenance() -> dict:
    from policyengine.provenance.manifest import get_release_manifest

    release = get_release_manifest("us")
    artifact = release.certified_data_artifact
    if (
        importlib.metadata.version("policyengine") != "6.2.5"
        or importlib.metadata.version("policyengine-us") != "2.2.1"
        or release.bundle_id != "us-6.2.5"
        or release.default_dataset != "populace_us_2024"
        or artifact is None
        or artifact.build_id != "populace-us-2024-spm-20260915"
        or release.datasets[release.default_dataset].sha256 != DATASET_SHA256
    ):
        raise ValueError("This runner requires the certified US 6.2.5 stack")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    return {
        "analysis_year": YEAR,
        "policyengine_version": "6.2.5",
        "bundle_id": release.bundle_id,
        "model_package": "policyengine-us",
        "model_version": "2.2.1",
        "dataset": release.default_dataset,
        "dataset_build_id": artifact.build_id,
        "dataset_sha256": DATASET_SHA256,
        "generated_at": datetime.now(UTC).isoformat(),
        "code_commit": commit,
        "method_note": (
            "The population was run in household batches. Every marital, "
            "tax, SPM and family unit nests within one household, and no "
            "output published here depends on other households under this "
            "run's settings, which leave health benefits out of household "
            "income, so batching gives the same answer as one run."
        ),
    }


def prepare(
    out_dir: Path, chunk_size: int, cached_dataset: Path | None
) -> None:
    from policyengine.provenance.dataset_materialization import (
        materialize_dataset,
    )

    from .microcosm_chunks import split_household_dataset

    started = time.monotonic()
    data_dir = out_dir / "chunks" / "source"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Preseeding a verified local copy only avoids a redundant download;
    # the exact bundled materializer still selects and verifies the default.
    if cached_dataset is not None:
        if sha256_file(cached_dataset) != DATASET_SHA256:
            raise ValueError(
                "cached dataset sha256 does not match certification"
            )
        destination = data_dir / "populace_us_2024.h5"
        if not destination.exists():
            shutil.copyfile(cached_dataset, destination)
    source = materialize_dataset("us", data_dir=data_dir)
    if sha256_file(Path(source.path)) != DATASET_SHA256:
        raise ValueError("materialized dataset sha256 mismatch")
    manifest = split_household_dataset(
        Path(source.path), out_dir / "chunks" / "population", chunk_size
    )
    manifest.update(
        {
            "source_uri": source.source_uri,
            "source_sha256": DATASET_SHA256,
            "preparation_peak_rss_gib": peak_rss_gib(),
            "preparation_wall_seconds": time.monotonic() - started,
        }
    )
    (out_dir / "chunk_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


def _periods(simulation, name: str) -> list[str | int]:
    variable = simulation.tax_benefit_system.variables[name]
    if str(variable.definition_period).lower() == "month":
        return [f"{YEAR}-{month:02d}" for month in range(1, 13)]
    return [YEAR]


def _calculate(simulation, name: str, entity: str, kind="amount"):
    periods = _periods(simulation, name)
    if kind == "snapshot":
        periods = periods[:1]
    arrays = [
        np.asarray(simulation.calculate(name, period, map_to=entity))
        for period in periods
    ]
    if kind in ("snapshot", "flag"):
        return np.mean(arrays, axis=0) if len(arrays) > 1 else arrays[0]
    return np.sum(arrays, axis=0) if len(arrays) > 1 else arrays[0]


def _variant_reform(variant: str):
    import importlib

    module, name, _ = VARIANTS[variant]
    return getattr(importlib.import_module(module), name)


def run_worker(
    chunk: Path, scenario: str, destination: Path, variant: str | None = None
) -> None:
    from policyengine import us

    from .reform import create_asset_limit_reform

    started = time.monotonic()
    reforms = []
    if variant is not None:
        # The structural change goes first so the limit reform's parameters
        # are the ones its formulas read.
        reforms.append(_variant_reform(variant))
    if scenario != "baseline":
        individual, couple = (
            (10_000, 20_000) if scenario == "ten_twenty" else (1e12, 1e12)
        )
        reforms.append(
            create_asset_limit_reform(individual, couple, start_year=YEAR)
        )
    kwargs = {}
    if reforms:
        kwargs["reform"] = reforms[0] if len(reforms) == 1 else tuple(reforms)
    simulation = us.managed_microsimulation(
        dataset=str(chunk), allow_unmanaged=True, **kwargs
    )
    persons = pd.DataFrame(
        {
            "person_id": simulation.populations["person"].ids,
            "household_id": _calculate(
                simulation, "household_id", "person", "snapshot"
            ),
            "person_weight": _calculate(
                simulation, "person_weight", "person", "snapshot"
            ),
            "age": _calculate(simulation, "age", "person", "snapshot"),
            "ssi_countable_resources": _calculate(
                simulation, "ssi_countable_resources", "person", "snapshot"
            ),
            f"ssi_{scenario}": _calculate(simulation, "ssi", "person"),
            f"in_poverty_{scenario}": _calculate(
                simulation, "spm_unit_is_in_spm_poverty", "person", "flag"
            ),
            f"in_deep_poverty_{scenario}": _calculate(
                simulation, "spm_unit_is_in_deep_spm_poverty", "person", "flag"
            ),
        }
    )
    households = pd.DataFrame(
        {
            "household_id": simulation.populations["household"].ids,
            "household_weight": _calculate(
                simulation, "household_weight", "household", "snapshot"
            ),
            **{
                f"{name}_{scenario}": _calculate(simulation, name, "household")
                for name in ("household_net_income", "snap", "income_tax")
            },
        }
    )
    diagnostics = persons[["person_id", "household_id"]].copy()
    diagnostics["marital_unit_id"] = _calculate(
        simulation, "marital_unit_id", "person", "snapshot"
    )
    for name in DIAGNOSTIC_FLAGS + MARITAL_FLAGS:
        diagnostics[f"{name}_{scenario}"] = _calculate(
            simulation, name, "person", "flag"
        )
        diagnostics[f"{name}_{scenario}_january"] = _calculate(
            simulation, name, "person", "snapshot"
        )
    for name in MARITAL_AMOUNTS:
        diagnostics[f"{name}_{scenario}"] = _calculate(
            simulation, name, "person"
        )
    destination.mkdir(parents=True, exist_ok=True)
    for filename, frame in (
        ("persons", persons),
        ("households", households),
        ("persons_diagnostics", diagnostics),
    ):
        frame.to_csv(destination / f"{filename}.csv.gz", index=False)
    receipt = {
        "chunk": str(chunk),
        "chunk_sha256": sha256_file(chunk),
        "scenario": scenario,
        "variant": variant,
        "peak_rss_gib": peak_rss_gib(),
        "wall_seconds": time.monotonic() - started,
        "legacy_input_renames": simulation.policyengine_bundle.get(
            "legacy_input_renames", {}
        ),
        "spm": simulation.policyengine_bundle["spm"],
    }
    (destination / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt), flush=True)


def _merge_scenarios(workers: Path, filename: str, identifier: str):
    merged = None
    for scenario in SCENARIOS:
        frame = pd.read_csv(workers / scenario / f"{filename}.csv.gz")
        if frame[identifier].duplicated().any():
            raise ValueError(f"duplicate {identifier} in {workers}/{scenario}")
        frame = frame.set_index(identifier)
        if merged is None:
            merged = frame
            continue
        if set(merged.index) != set(frame.index):
            raise ValueError(f"scenario ID mismatch in {workers}")
        frame = frame.loc[merged.index]
        shared = set(merged.columns) & set(frame.columns)
        for column in shared:
            if not np.array_equal(merged[column], frame[column]):
                raise ValueError(f"scenario changed fixed column {column}")
        merged = merged.join(frame.drop(columns=sorted(shared)))
    return merged.reset_index()


def assemble_run(workers_dir: Path, chunk_count: int, out_dir: Path) -> None:
    tables = {}
    for filename, identifier in (
        ("persons", "person_id"),
        ("households", "household_id"),
        ("persons_diagnostics", "person_id"),
    ):
        tables[filename] = pd.concat(
            [
                _merge_scenarios(
                    workers_dir / f"chunk_{i:04d}", filename, identifier
                )
                for i in range(chunk_count)
            ],
            ignore_index=True,
        )
    validate_run_frames(
        tables["persons"], tables["households"], tables["persons_diagnostics"]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, frame in tables.items():
        frame.to_csv(out_dir / f"{filename}.csv.gz", index=False)


def _admitted(arguments: list[str]) -> None:
    command = [
        "heavy",
        "--mem",
        str(WORKER_MEM_GIB),
        "--",
        sys.executable,
        "-m",
        "ssi_asset_limits.microcosm_run",
        *arguments,
    ]
    # heavy exits 71 when its queue could not be joined and 75 when it gave
    # up waiting; neither means the worker ran, so those are retried.
    for attempt in range(ADMISSION_RETRIES):
        returncode = _run_in_group(command)
        if returncode == 0:
            return
        if returncode not in (71, 75) or attempt == ADMISSION_RETRIES - 1:
            raise subprocess.CalledProcessError(returncode, command)
        time.sleep(60 * (attempt + 1))


def _run_in_group(command: list[str]) -> int:
    # A synchronous child in a new group can be terminated on interruption;
    # no engine worker or gate process survives this coordinator.
    process = subprocess.Popen(command, start_new_session=True)
    try:
        return process.wait()
    except BaseException:
        if process.poll() is None:
            import signal

            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        raise


def _prepared(manifest_path: Path, chunk_size: int) -> bool:
    """True when an interrupted run already split the certified dataset."""
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text())
    return (
        manifest.get("source_sha256") == DATASET_SHA256
        and manifest.get("chunk_size") == chunk_size
        and all(Path(path).exists() for path in manifest["chunk_paths"])
    )


def _finished(
    destination: Path, chunk: Path, scenario: str, variant: str | None = None
) -> bool:
    """True when this worker already wrote its tables for this exact chunk."""
    receipt_path = destination / "receipt.json"
    if not receipt_path.exists():
        return False
    receipt = json.loads(receipt_path.read_text())
    return (
        receipt.get("scenario") == scenario
        and receipt.get("variant") == variant
        and receipt.get("chunk_sha256") == sha256_file(chunk)
        and all(
            (destination / f"{name}.csv.gz").exists()
            for name in ("persons", "households", "persons_diagnostics")
        )
    )


def run(
    out_dir: Path,
    chunk_size: int,
    cached_dataset: Path | None,
    variant: str | None = None,
) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if variant is not None and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    started = time.monotonic()
    provenance = certified_provenance()
    if variant is not None:
        provenance["method_note"] += (
            f" Sensitivity variant, not the certified engine: "
            f"{VARIANTS[variant][2]}."
        )
    if (out_dir / "run_metadata.json").exists():
        raise ValueError("out-dir already contains a completed run")
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = out_dir / "uv-pip-freeze.txt"
    freeze_path.write_text(
        subprocess.check_output(
            ["uv", "pip", "freeze", "--python", sys.executable], text=True
        )
    )
    manifest_path = out_dir / "chunk_manifest.json"
    if not _prepared(manifest_path, chunk_size):
        prep_args = ["_prepare", "--out-dir", str(out_dir)]
        if cached_dataset:
            prep_args += ["--cached-dataset", str(cached_dataset)]
        _admitted([*prep_args, "--chunk-size", str(chunk_size)])
    manifest = json.loads(manifest_path.read_text())
    receipts = []
    for index, chunk in enumerate(manifest["chunk_paths"]):
        for scenario in SCENARIOS:
            destination = out_dir / "workers" / f"chunk_{index:04d}" / scenario
            print(
                f"chunk {index + 1}/{manifest['chunk_count']} {scenario}",
                flush=True,
            )
            if not _finished(destination, Path(chunk), scenario, variant):
                worker_args = [
                    "_worker",
                    "--chunk",
                    chunk,
                    "--scenario",
                    scenario,
                    "--out-dir",
                    str(destination),
                ]
                if variant is not None:
                    worker_args += ["--variant", variant]
                _admitted(worker_args)
            receipt = json.loads((destination / "receipt.json").read_text())
            receipts.append(receipt)
            if receipt["peak_rss_gib"] > WORKER_MEM_GIB:
                raise RuntimeError(
                    f"Worker peak exceeds {WORKER_MEM_GIB} GiB; rerun in "
                    "a new directory with --chunk-size "
                    f"{max(1, chunk_size // 2)}"
                )
    assemble_run(out_dir / "workers", manifest["chunk_count"], out_dir)
    output_weight_totals = {
        entity: float(
            pd.read_csv(
                out_dir / f"{entity}s.csv.gz", usecols=[f"{entity}_weight"]
            )[f"{entity}_weight"].sum()
        )
        for entity in ("person", "household")
    }
    diagnostics = {
        **manifest,
        "variant": variant,
        "output_weight_totals": output_weight_totals,
        "output_weight_year": YEAR,
        "input_weight_year": 2024,
        "per_chunk_peak_rss_gib": [
            {
                "chunk_index": i,
                **{
                    s: receipts[i * len(SCENARIOS) + j]["peak_rss_gib"]
                    for j, s in enumerate(SCENARIOS)
                },
            }
            for i in range(manifest["chunk_count"])
        ],
        "workers": receipts,
        "wall_seconds": time.monotonic() - started,
        "uv_pip_freeze_path": str(freeze_path),
        "annualization": (
            "MONTH amounts sum all twelve months; MONTH flags are fractions "
            "of true months; age and resources use January; YEAR variables "
            "are calculated for 2026."
        ),
    }
    write_run_metadata(out_dir, provenance, diagnostics)
    from .microcosm_checks import write_checks

    write_checks(out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("_prepare", "_worker"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=8_000)
    parser.add_argument("--cached-dataset", type=Path)
    parser.add_argument("--chunk", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANTS),
        help="Layer a structural reform on the engine (sensitivity run).",
    )
    args = parser.parse_args()
    args.out_dir = args.out_dir.resolve()
    if args.mode == "_prepare":
        prepare(args.out_dir, args.chunk_size, args.cached_dataset)
    elif args.mode == "_worker":
        if args.chunk is None or args.scenario is None:
            parser.error("_worker requires --chunk and --scenario")
        run_worker(args.chunk, args.scenario, args.out_dir, args.variant)
    else:
        run(args.out_dir, args.chunk_size, args.cached_dataset, args.variant)


if __name__ == "__main__":
    main()
