"""Run-directory contract tests without importing or running the engine."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ssi_asset_limits.microcosm_run import (
    _calculate,
    assemble_run,
    validate_run_frames,
    write_run_metadata,
)
from ssi_asset_limits.publish import publish

SCENARIOS = ("baseline", "ten_twenty", "no_limit")
DIAGNOSTIC_VARIABLES = (
    "is_ssi_aged_blind_disabled",
    "meets_ssi_resource_test",
    "takes_up_ssi_if_eligible",
    "is_ssi_eligible",
    "is_disabled",
    "meets_ssi_disability_criteria",
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


class FakeSimulation:
    """Period metadata and calculation interface without an engine."""

    def __init__(self, definition_period, values):
        self.tax_benefit_system = SimpleNamespace(
            variables={
                "value": SimpleNamespace(definition_period=definition_period)
            }
        )
        self.values = values
        self.calls = []

    def calculate(self, name, period, map_to):
        self.calls.append((name, period, map_to))
        return self.values(period)


def test_monthly_benefits_sum_all_twelve_months():
    simulation = FakeSimulation(
        "month",
        lambda period: np.array([int(period[-2:]), 2 * int(period[-2:])]),
    )
    np.testing.assert_array_equal(
        _calculate(simulation, "value", "person"), [78, 156]
    )
    assert simulation.calls == [
        ("value", f"2026-{month:02d}", "person") for month in range(1, 13)
    ]


def test_monthly_flags_are_fractions_of_true_months():
    simulation = FakeSimulation(
        "month",
        lambda period: np.array([int(period[-2:]) <= 6, True]),
    )
    np.testing.assert_array_equal(
        _calculate(simulation, "value", "person", "flag"), [0.5, 1.0]
    )
    assert len(simulation.calls) == 12


def test_monthly_snapshots_use_only_january():
    simulation = FakeSimulation("month", lambda period: np.array([1, 2]))
    np.testing.assert_array_equal(
        _calculate(simulation, "value", "person", "snapshot"), [1, 2]
    )
    assert simulation.calls == [("value", "2026-01", "person")]


def test_annual_variables_are_calculated_once():
    simulation = FakeSimulation("year", lambda period: np.array([7, 11]))
    np.testing.assert_array_equal(
        _calculate(simulation, "value", "household"), [7, 11]
    )
    assert simulation.calls == [("value", 2026, "household")]


def run_frames():
    """Two people share a household; one gains SSI under both reforms."""
    persons = pd.DataFrame(
        {
            "person_id": [101, 102],
            "household_id": [10, 10],
            "person_weight": [20.0, 20.0],
            "age": [70, 30],
            "ssi_countable_resources": [5_000.0, 0.0],
        }
    )
    households = pd.DataFrame(
        {"household_id": [10], "household_weight": [20.0]}
    )
    diagnostics = persons[["person_id", "household_id"]].copy()
    for scenario in SCENARIOS:
        ssi = [0.0, 6_000.0] if scenario == "baseline" else [4_000.0, 6_000.0]
        persons[f"ssi_{scenario}"] = ssi
        persons[f"in_poverty_{scenario}"] = [scenario == "baseline", False]
        persons[f"in_deep_poverty_{scenario}"] = False
        households[f"household_net_income_{scenario}"] = sum(ssi) + 10_000
        households[f"snap_{scenario}"] = 1_000.0
        households[f"income_tax_{scenario}"] = 0.0
        for variable in DIAGNOSTIC_VARIABLES:
            diagnostics[f"{variable}_{scenario}"] = [1.0, 0.5]
    return persons, households, diagnostics


def provenance():
    return {
        "analysis_year": 2026,
        "policyengine_version": "6.2.5",
        "bundle_id": "us-6.2.5",
        "model_package": "policyengine-us",
        "model_version": "2.2.1",
        "dataset": "populace_us_2024",
        "dataset_build_id": "populace-us-2024-spm-20260915",
        "dataset_sha256": "a" * 64,
        "generated_at": "2026-10-09T00:00:00+00:00",
        "code_commit": "b" * 40,
        "method_note": "Household batches compute exact population results.",
    }


def test_run_schema_and_publisher_round_trip(tmp_path):
    persons, households, diagnostics = run_frames()
    validate_run_frames(persons, households, diagnostics)
    persons.to_csv(tmp_path / "persons.csv.gz", index=False)
    households.to_csv(tmp_path / "households.csv.gz", index=False)
    diagnostics.to_csv(tmp_path / "persons_diagnostics.csv.gz", index=False)
    metadata_path = write_run_metadata(
        tmp_path,
        provenance(),
        {"chunk_count": 1, "chunk_size": 8_000, "peak_rss_bytes": [123]},
    )
    metadata = json.loads(metadata_path.read_text())
    assert metadata_path == tmp_path / "run_metadata.json"
    assert set(metadata) == {"provenance", "diagnostics"}
    assert set(metadata["provenance"]) == PROVENANCE_FIELDS
    assert metadata["diagnostics"]["chunk_count"] == 1
    published = publish(tmp_path, tmp_path / "public")
    assert published["provenance"] == {
        key: value
        for key, value in provenance().items()
        if key != "method_note"
    }
    assert published["baseline"]["total_recipients"] == 20
    assert published["baseline"]["total_federal_ssi"] == 120_000
    for scenario in published["scenarios"]:
        metrics = {row["metric"]: row["value"] for row in scenario["summary"]}
        assert metrics["new_recipients"] == 20
        assert metrics["annual_ssi_cost"] == 80_000


@pytest.mark.parametrize(
    ("frame_index", "column"),
    [
        (0, "person_id"),
        (0, "ssi_no_limit"),
        (0, "in_deep_poverty_ten_twenty"),
        (1, "household_weight"),
        (1, "snap_baseline"),
        (2, "is_ssi_eligible_no_limit"),
    ],
)
def test_missing_run_columns_are_rejected(frame_index, column):
    frames = list(run_frames())
    frames[frame_index] = frames[frame_index].drop(columns=column)
    with pytest.raises(ValueError, match=column):
        validate_run_frames(*frames)


@pytest.mark.parametrize("frame_index", [0, 1, 2])
def test_duplicate_entity_rows_are_rejected(frame_index):
    frames = list(run_frames())
    frames[frame_index] = pd.concat(
        [frames[frame_index], frames[frame_index].iloc[:1]], ignore_index=True
    )
    with pytest.raises(ValueError):
        validate_run_frames(*frames)


def test_person_with_unknown_household_is_rejected():
    persons, households, diagnostics = run_frames()
    persons.loc[0, "household_id"] = 999
    with pytest.raises(ValueError):
        validate_run_frames(persons, households, diagnostics)


def test_household_without_any_people_is_rejected():
    persons, households, diagnostics = run_frames()
    extra = households.copy()
    extra["household_id"] = 999
    households = pd.concat([households, extra], ignore_index=True)
    with pytest.raises(ValueError):
        validate_run_frames(persons, households, diagnostics)


@pytest.mark.parametrize(
    ("frame_index", "column", "value"),
    [
        (0, "person_weight", -1.0),
        (1, "household_weight", -1.0),
        (0, "ssi_baseline", np.inf),
        (0, "age", np.nan),
        (1, "household_net_income_no_limit", -np.inf),
        (2, "is_ssi_eligible_baseline", np.nan),
    ],
)
def test_invalid_numerical_values_are_rejected(frame_index, column, value):
    frames = list(run_frames())
    frames[frame_index].loc[0, column] = value
    with pytest.raises(ValueError):
        validate_run_frames(*frames)


@pytest.mark.parametrize("value", [0.5, "False", 2])
def test_poverty_flags_must_be_true_or_false(value):
    persons, households, diagnostics = run_frames()
    persons["in_poverty_baseline"] = persons["in_poverty_baseline"].astype(
        object
    )
    persons.loc[0, "in_poverty_baseline"] = value
    with pytest.raises(ValueError, match="in_poverty_baseline"):
        validate_run_frames(persons, households, diagnostics)


def test_poverty_flags_may_be_zero_or_one():
    persons, households, diagnostics = run_frames()
    persons["in_poverty_baseline"] = persons["in_poverty_baseline"].astype(int)
    validate_run_frames(persons, households, diagnostics)


def test_diagnostics_must_identify_the_same_people():
    persons, households, diagnostics = run_frames()
    diagnostics.loc[0, "person_id"] = 999
    with pytest.raises(ValueError):
        validate_run_frames(persons, households, diagnostics)


def test_diagnostics_row_order_does_not_change_identity():
    persons, households, diagnostics = run_frames()
    validate_run_frames(persons, households, diagnostics.iloc[::-1])


def write_worker_tables(workers, index, scenario, frames):
    destination = workers / f"chunk_{index:04d}" / scenario
    destination.mkdir(parents=True)
    for filename, frame in zip(
        ("persons", "households", "persons_diagnostics"), frames
    ):
        columns = [
            column
            for column in frame.columns
            if not any(column.endswith(f"_{other}") for other in SCENARIOS)
            or column.endswith(f"_{scenario}")
        ]
        frame[columns].to_csv(destination / f"{filename}.csv.gz", index=False)


def test_assembly_joins_scenarios_by_id_and_concatenates_chunks(tmp_path):
    workers = tmp_path / "workers"
    for index in range(2):
        frames = run_frames()
        for frame in frames:
            if "person_id" in frame:
                frame["person_id"] += index * 1_000
            frame["household_id"] += index * 10
        for scenario in SCENARIOS:
            ordered = (
                frames
                if scenario == "baseline"
                else tuple(frame.iloc[::-1] for frame in frames)
            )
            write_worker_tables(workers, index, scenario, ordered)
    out_dir = tmp_path / "run"
    assemble_run(workers, 2, out_dir)
    persons = pd.read_csv(out_dir / "persons.csv.gz")
    households = pd.read_csv(out_dir / "households.csv.gz")
    diagnostics = pd.read_csv(out_dir / "persons_diagnostics.csv.gz")
    validate_run_frames(persons, households, diagnostics)
    assert persons["person_id"].tolist() == [101, 102, 1101, 1102]
    assert persons["ssi_ten_twenty"].tolist() == [4_000, 6_000, 4_000, 6_000]
    assert diagnostics["is_ssi_eligible_no_limit"].tolist() == [1, 0.5, 1, 0.5]
    assert persons["person_weight"].sum() == 80
    assert households["household_weight"].sum() == 40


@pytest.mark.parametrize("changed", ["person_id", "person_weight"])
def test_assembly_rejects_scenario_population_changes(tmp_path, changed):
    workers = tmp_path / "workers"
    for scenario in SCENARIOS:
        frames = run_frames()
        if scenario == "no_limit":
            frames[0].loc[0, changed] += 1
        write_worker_tables(workers, 0, scenario, frames)
    with pytest.raises(ValueError):
        assemble_run(workers, 1, tmp_path / "run")


@pytest.mark.parametrize("missing", sorted(PROVENANCE_FIELDS))
def test_metadata_requires_every_app_provenance_field(tmp_path, missing):
    incomplete = provenance()
    del incomplete[missing]
    with pytest.raises(ValueError, match=missing):
        write_run_metadata(tmp_path, incomplete, {})


def test_execution_diagnostics_cannot_leak_into_provenance(tmp_path):
    extra = {**provenance(), "peak_rss_bytes": 123}
    with pytest.raises(ValueError, match="peak_rss_bytes"):
        write_run_metadata(tmp_path, extra, {})


def test_admission_retries_only_gate_failures(monkeypatch):
    from ssi_asset_limits import microcosm_run

    codes = iter([71, 75, 0])
    calls = []
    monkeypatch.setattr(microcosm_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        microcosm_run,
        "_run_in_group",
        lambda command: calls.append(command) or next(codes),
    )
    microcosm_run._admitted(["_worker"])
    assert len(calls) == 3
    assert calls[0][:3] == [
        "heavy",
        "--mem",
        str(microcosm_run.WORKER_MEM_GIB),
    ]

    monkeypatch.setattr(microcosm_run, "_run_in_group", lambda command: 1)
    with pytest.raises(subprocess.CalledProcessError):
        microcosm_run._admitted(["_worker"])


def test_admission_gives_up_after_the_retry_budget(monkeypatch):
    from ssi_asset_limits import microcosm_run

    calls = []
    monkeypatch.setattr(microcosm_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        microcosm_run,
        "_run_in_group",
        lambda command: calls.append(command) or 71,
    )
    with pytest.raises(subprocess.CalledProcessError):
        microcosm_run._admitted(["_worker"])
    assert len(calls) == microcosm_run.ADMISSION_RETRIES


def test_finished_worker_is_recognised_only_for_the_same_chunk(tmp_path):
    from ssi_asset_limits import microcosm_run

    chunk = tmp_path / "chunk_0000.h5"
    chunk.write_bytes(b"first batch")
    destination = tmp_path / "workers" / "chunk_0000" / "baseline"
    destination.mkdir(parents=True)
    assert not microcosm_run._finished(destination, chunk, "baseline")
    for name in ("persons", "households", "persons_diagnostics"):
        (destination / f"{name}.csv.gz").write_bytes(b"")
    (destination / "receipt.json").write_text(
        json.dumps(
            {
                "scenario": "baseline",
                "chunk_sha256": microcosm_run.sha256_file(chunk),
            }
        )
    )
    assert microcosm_run._finished(destination, chunk, "baseline")
    assert not microcosm_run._finished(destination, chunk, "no_limit")
    chunk.write_bytes(b"a different batch")
    assert not microcosm_run._finished(destination, chunk, "baseline")
    chunk.write_bytes(b"first batch")
    (destination / "persons.csv.gz").unlink()
    assert not microcosm_run._finished(destination, chunk, "baseline")


def test_prepared_requires_the_certified_source_and_chunk_size(tmp_path):
    from ssi_asset_limits import microcosm_run

    manifest_path = tmp_path / "chunk_manifest.json"
    assert not microcosm_run._prepared(manifest_path, 8_000)
    chunk = tmp_path / "chunk_0000.h5"
    chunk.write_bytes(b"x")
    manifest = {
        "source_sha256": microcosm_run.DATASET_SHA256,
        "chunk_size": 8_000,
        "chunk_paths": [str(chunk)],
    }
    manifest_path.write_text(json.dumps(manifest))
    assert microcosm_run._prepared(manifest_path, 8_000)
    assert not microcosm_run._prepared(manifest_path, 4_000)
    manifest_path.write_text(json.dumps({**manifest, "source_sha256": "0"}))
    assert not microcosm_run._prepared(manifest_path, 8_000)
    manifest_path.write_text(json.dumps(manifest))
    chunk.unlink()
    assert not microcosm_run._prepared(manifest_path, 8_000)


def test_variant_workers_are_not_mistaken_for_certified_ones(tmp_path):
    from ssi_asset_limits import microcosm_run

    chunk = tmp_path / "chunk_0000.h5"
    chunk.write_bytes(b"batch")
    destination = tmp_path / "workers" / "chunk_0000" / "baseline"
    destination.mkdir(parents=True)
    for name in ("persons", "households", "persons_diagnostics"):
        (destination / f"{name}.csv.gz").write_bytes(b"")
    receipt = {
        "scenario": "baseline",
        "chunk_sha256": microcosm_run.sha256_file(chunk),
    }
    (destination / "receipt.json").write_text(json.dumps(receipt))
    assert microcosm_run._finished(destination, chunk, "baseline")
    assert not microcosm_run._finished(
        destination, chunk, "baseline", "resource_deeming"
    )
    receipt["variant"] = "resource_deeming"
    (destination / "receipt.json").write_text(json.dumps(receipt))
    # A variant receipt must also name the reform source it ran.
    assert not microcosm_run._finished(
        destination, chunk, "baseline", "resource_deeming"
    )
    receipt["variant_source_sha256"] = microcosm_run.variant_source_sha256(
        "resource_deeming"
    )
    (destination / "receipt.json").write_text(json.dumps(receipt))
    assert microcosm_run._finished(
        destination, chunk, "baseline", "resource_deeming"
    )
    assert not microcosm_run._finished(destination, chunk, "baseline")
    receipt["variant_source_sha256"] = "0" * 64
    (destination / "receipt.json").write_text(json.dumps(receipt))
    assert not microcosm_run._finished(
        destination, chunk, "baseline", "resource_deeming"
    )


def test_variant_source_hash_is_the_reform_module():
    from ssi_asset_limits import microcosm_run
    from ssi_asset_limits.microcosm_run import sha256_file

    source = (
        Path(microcosm_run.__file__).parent
        / "sensitivity"
        / "ssi_resource_deeming_reform.py"
    )
    assert microcosm_run.variant_source_sha256(
        "resource_deeming"
    ) == sha256_file(source)
    assert microcosm_run.variant_source_sha256(None) is None


def test_unknown_variant_is_refused_before_anything_runs(tmp_path):
    from ssi_asset_limits import microcosm_run

    with pytest.raises(ValueError, match="unknown variant"):
        microcosm_run.run(tmp_path, 8_000, None, "not_a_variant")
