from pathlib import Path

import pandas as pd
import pytest

from ssi_asset_limits.microcosm_chunks import (
    ENTITIES,
    NESTED_ENTITIES,
    assert_household_nesting,
    person_entity_id_column,
    split_household_dataset,
)


def synthetic_tables():
    """Nonconsecutive IDs and indexes make accidental renumbering visible."""

    persons = pd.DataFrame(
        {
            "person_id": [41, 45, 90, 101, 102],
            "person_household_id": [30, 30, 10, 90, 90],
            "person_marital_unit_id": [71, 71, 10, 81, 82],
            "person_tax_unit_id": [72, 72, 12, 83, 83],
            "person_spm_unit_id": [73, 73, 13, 84, 84],
            "person_family_id": [74, 74, 14, 85, 85],
            "person_weight": [2.0, 2.0, 7.0, 1.25, 1.25],
            "age": pd.Series([70, 68, 25, 42, 8], dtype="int16"),
            "legacy_input": [True, False, True, False, False],
        }
    )
    persons.index = pd.Index([20, 21, 25, 60, 61], name="original_row")
    households = pd.DataFrame(
        {
            "household_id": [90, 30, 10],
            "household_weight": [1.25, 2.0, 7.0],
            "state_code": ["CA", "NY", "OH"],
        },
        index=pd.Index([42, 18, 3], name="original_row"),
    )
    tables = {
        "/person": persons,
        "/household": households,
        "/_time_period": pd.Series([2024], name="time_period"),
        "/metadata": pd.DataFrame({"certification": ["synthetic"]}),
        "/person_diagnostics": persons[["person_id", "legacy_input"]],
    }
    for entity in NESTED_ENTITIES:
        ids = persons[f"person_{entity}_id"].unique()
        tables[f"/{entity}"] = pd.DataFrame(
            {f"{entity}_id": ids, "an_input": range(len(ids))},
            index=pd.Index(range(100, 100 + len(ids)), name="original_row"),
        )
    return tables


def write_source(path: Path, tables: dict):
    with pd.HDFStore(path, "w") as store:
        for key, value in tables.items():
            store.put(key, value)


@pytest.mark.parametrize("modern_foreign_keys", [False, True])
@pytest.mark.parametrize("explicit_person_weights", [False, True])
def test_split_preserves_every_table_period_ids_indexes_and_values(
    tmp_path, modern_foreign_keys, explicit_person_weights
):
    tables = synthetic_tables()
    if not explicit_person_weights:
        tables["/person"] = tables["/person"].drop(columns="person_weight")
    if modern_foreign_keys:
        tables["/person"] = tables["/person"].rename(
            columns={
                f"person_{entity}_id": f"{entity}_id"
                for entity in ("household", *NESTED_ENTITIES)
            }
        )
    source = tmp_path / "source.h5"
    write_source(source, tables)
    result = split_household_dataset(source, tmp_path / "chunks", 2)
    assert result["chunk_count"] == 2
    assert result["household_count"] == 3
    assert result["person_count"] == 5
    assert result["nesting"]["all_nested"] is True
    assert result["full_weight_totals"] == {"household": 10.25, "person": 13.5}
    assert result["summed_chunk_weight_totals"] == result["full_weight_totals"]
    assert [c["household_count"] for c in result["chunks"]] == [2, 1]
    reconstructed = {key: [] for key in tables}
    for path in result["chunk_paths"]:
        with pd.HDFStore(path, "r") as chunk:
            assert set(chunk.keys()) == set(tables)
            pd.testing.assert_series_equal(
                chunk["/_time_period"], tables["/_time_period"]
            )
            pd.testing.assert_frame_equal(
                chunk["/metadata"], tables["/metadata"]
            )
            hids = set(chunk["/household"].household_id)
            people = chunk["/person"]
            household_column = person_entity_id_column(people, "household")
            assert set(people[household_column]) <= hids
            for key in tables:
                reconstructed[key].append(chunk[key])
    for key in [*(f"/{entity}" for entity in ENTITIES), "/person_diagnostics"]:
        pd.testing.assert_frame_equal(
            pd.concat(reconstructed[key]).sort_index(),
            tables[key].sort_index(),
        )
    # Splitting did not touch any source values either.
    with pd.HDFStore(source, "r") as original:
        for key, value in tables.items():
            if isinstance(value, pd.Series):
                pd.testing.assert_series_equal(original[key], value)
            else:
                pd.testing.assert_frame_equal(original[key], value)


@pytest.mark.parametrize("entity", NESTED_ENTITIES)
def test_nesting_rejects_a_cross_household_unit_before_writing(
    tmp_path, entity
):
    tables = synthetic_tables()
    # A unit containing person 41 and person 90 spans households 30 and 10.
    column = f"person_{entity}_id"
    persons = tables["/person"]
    persons.loc[25, column] = persons.loc[20, column]
    source = tmp_path / "source.h5"
    write_source(source, tables)
    output = tmp_path / "chunks"
    with pytest.raises(ValueError, match=f"{entity} crosses household"):
        split_household_dataset(source, output, 1)
    assert not output.exists()


def test_nesting_rejects_unassigned_units_and_unknown_households():
    tables = synthetic_tables()
    persons = tables["/person"]
    entities = {entity: tables[f"/{entity}"] for entity in NESTED_ENTITIES}
    entities["family"] = pd.concat(
        [entities["family"], pd.DataFrame({"family_id": [999]})]
    )
    with pytest.raises(ValueError, match="family IDs.*unassigned"):
        assert_household_nesting(persons, tables["/household"], entities)
    persons = persons.copy()
    persons.loc[20, "person_household_id"] = 999
    with pytest.raises(ValueError, match="unknown household"):
        assert_household_nesting(persons, tables["/household"])


def test_conflicting_foreign_key_aliases_fail():
    people = synthetic_tables()["/person"].copy()
    people["household_id"] = people.person_household_id
    assert person_entity_id_column(people, "household") == "household_id"
    people.loc[20, "household_id"] = 999
    with pytest.raises(ValueError, match="Conflicting person household"):
        assert_household_nesting(people)


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5])
def test_invalid_chunk_size_fails(tmp_path, chunk_size):
    with pytest.raises(ValueError, match="positive integer"):
        split_household_dataset(
            tmp_path / "source.h5", tmp_path / "chunks", chunk_size
        )
