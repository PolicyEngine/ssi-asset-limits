"""Split a PolicyEngine population into exact, complete household batches.

The proof checks every person's marital, tax, SPM and family unit before any
chunk is written. Entity IDs, indexes, inputs, and ``_time_period`` are kept
unchanged: chunking never renumbers IDs or modifies the certified frame.
This module imports no simulation engine and can be tested with tiny files.
"""

from __future__ import annotations

import math
import operator
from pathlib import Path

import numpy as np
import pandas as pd

ENTITIES = (
    "person",
    "household",
    "marital_unit",
    "tax_unit",
    "spm_unit",
    "family",
)
NESTED_ENTITIES = ENTITIES[2:]


def person_entity_id_column(persons: pd.DataFrame, entity: str) -> str:
    """Resolve modern or legacy person-to-entity foreign keys explicitly."""

    modern, legacy = f"{entity}_id", f"person_{entity}_id"
    available = [name for name in (modern, legacy) if name in persons]
    if not available:
        raise ValueError(
            f"Missing person {entity} foreign key: {modern} or {legacy}"
        )
    if len(available) == 2 and not np.array_equal(
        persons[modern].to_numpy(), persons[legacy].to_numpy()
    ):
        raise ValueError(f"Conflicting person {entity} foreign keys")
    return available[0]


def assert_household_nesting(
    persons: pd.DataFrame,
    households: pd.DataFrame | None = None,
    units: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """Prove that each non-household entity's persons share one household.

    Optional entity tables also check that all references resolve and that
    every entity row is assigned to a household. Invalid input raises
    ``ValueError`` with the offending entity and IDs; checks do not disappear
    under Python's ``-O`` flag.
    """

    foreign_keys = {
        entity: person_entity_id_column(persons, entity)
        for entity in ("household", *NESTED_ENTITIES)
    }
    household_column = foreign_keys["household"]
    person_columns = ["person_id", *foreign_keys.values()]
    missing = sorted(set(person_columns) - set(persons.columns))
    if missing:
        raise ValueError(f"Missing person columns: {missing}")
    if persons[person_columns].isna().any().any():
        raise ValueError("Person entity IDs must not be missing")
    if not persons.person_id.is_unique:
        raise ValueError("person_id must be unique")
    if households is not None:
        _assert_ids(households, "household")
        unknown = set(persons[household_column]) - set(households.household_id)
        if unknown:
            raise ValueError(
                f"Persons reference unknown household IDs: {list(unknown)[:5]}"
            )
    result = {
        "all_nested": True,
        "person_count": len(persons),
        "person_foreign_key_columns": foreign_keys,
        "entities": {},
    }
    for entity in NESTED_ENTITIES:
        column = foreign_keys[entity]
        household_counts = persons.groupby(column, sort=False)[
            household_column
        ].nunique()
        offending = household_counts.index[household_counts > 1].tolist()
        if offending:
            raise ValueError(
                f"{entity} crosses household boundaries: {offending[:5]}"
            )
        if units is not None:
            if entity not in units:
                raise ValueError(f"Missing entity table: {entity}")
            _assert_ids(units[entity], entity)
            actual_ids = set(units[entity][f"{entity}_id"])
            referenced_ids = set(household_counts.index)
            if actual_ids != referenced_ids:
                unknown = list(referenced_ids - actual_ids)[:5]
                orphan = list(actual_ids - referenced_ids)[:5]
                raise ValueError(
                    f"{entity} IDs do not match person references: "
                    f"unknown={unknown}, unassigned={orphan}"
                )
        result["entities"][entity] = {
            "unit_count": len(household_counts),
            "cross_household_unit_count": 0,
        }
    return result


def _assert_ids(table: pd.DataFrame, entity: str) -> None:
    column = f"{entity}_id"
    if column not in table:
        raise ValueError(f"Missing {entity} column: {column}")
    if table[column].isna().any() or not table[column].is_unique:
        raise ValueError(f"{column} must be nonmissing and unique")


def dataset_person_weights(
    persons: pd.DataFrame, households: pd.DataFrame
) -> np.ndarray:
    """Read person weights, or map household weights for a household frame.

    The certified US model defines ``person_weight`` as the person's
    ``household_weight`` unless the dataset supplies explicit person weights.
    See policyengine-us 2.2.1's
    ``variables/household/demographic/weights/person_weight.py:10-11``.
    Mapping the IDs does not modify either source table.
    """

    if "person_weight" in persons:
        return persons.person_weight.to_numpy(dtype=float)
    household_column = person_entity_id_column(persons, "household")
    household_weights = households.set_index("household_id")[
        "household_weight"
    ]
    return (
        persons[household_column].map(household_weights).to_numpy(dtype=float)
    )


def _weight_total(
    table: pd.DataFrame,
    entity: str,
    households: pd.DataFrame | None = None,
) -> float:
    column = f"{entity}_weight"
    if entity == "person" and households is not None:
        weights = dataset_person_weights(table, households)
    elif column in table:
        weights = table[column].to_numpy(dtype=float)
    else:
        raise ValueError(f"Missing {entity} weight column: {column}")
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError(f"{column} must be finite and nonnegative")
    return float(np.sum(weights, dtype=np.float64))


def _subset_extra_table(
    value: pd.DataFrame | pd.Series,
    selected_ids: dict[str, set],
) -> pd.DataFrame | pd.Series:
    """Keep metadata, and subset any auxiliary table with entity ID columns."""

    if isinstance(value, pd.DataFrame):
        columns = [
            (f"{entity}_id", selected_ids[entity])
            for entity in ENTITIES
            if f"{entity}_id" in value
        ]
        if columns:
            mask = np.ones(len(value), dtype=bool)
            for column, ids in columns:
                mask &= value[column].isin(ids).to_numpy()
            return value.loc[mask]
    return value


def split_household_dataset(
    source: Path,
    output_dir: Path,
    chunk_size: int = 8_000,
) -> dict:
    """Write household batches and return JSON-serializable proof diagnostics.

    All HDF tables are preserved. The six entity tables are subset by their
    original IDs; auxiliary tables with entity ID columns are subset the
    same way, and global metadata tables are copied unchanged. Tables retain
    their original indexes, column order and dtypes. Run this preparation in
    an admitted process too: reading a fixed-format HDF table loads it whole.
    """

    try:
        chunk_size_int = operator.index(chunk_size)
    except TypeError as exc:
        raise ValueError("chunk_size must be a positive integer") from exc
    if isinstance(chunk_size, bool) or chunk_size_int <= 0:
        raise ValueError("chunk_size must be a positive integer")
    chunk_size = chunk_size_int
    source = Path(source)
    output_dir = Path(output_dir)
    with pd.HDFStore(source, "r") as store:
        keys = store.keys()
        required = {f"/{entity}" for entity in ENTITIES} | {"/_time_period"}
        missing = sorted(required - set(keys))
        if missing:
            raise ValueError(f"Missing HDF tables: {missing}")
        tables = {key: store[key] for key in keys}
    entities = {entity: tables[f"/{entity}"] for entity in ENTITIES}
    if not all(isinstance(value, pd.DataFrame) for value in entities.values()):
        raise ValueError("Entity tables must be pandas DataFrames")
    persons, households = entities["person"], entities["household"]
    nesting = assert_household_nesting(persons, households, entities)
    foreign_keys = nesting["person_foreign_key_columns"]
    if households.empty:
        raise ValueError("Cannot split an empty household table")
    full_weights = {
        "household": _weight_total(households, "household"),
        "person": _weight_total(persons, "person", households),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    # Original household order and original row order are deliberately kept.
    household_ids = households.household_id.to_numpy()
    person_by_household = persons.groupby(
        foreign_keys["household"], sort=False
    ).indices
    chunks = []
    for start in range(0, len(households), chunk_size):
        hh_ids = household_ids[start : start + chunk_size]
        person_positions = [
            person_by_household[hh_id]
            for hh_id in hh_ids
            if hh_id in person_by_household
        ]
        p = persons.iloc[
            np.sort(np.concatenate(person_positions))
            if person_positions
            else np.array([], dtype=int)
        ]
        selected_ids = {
            "person": set(p.person_id),
            "household": set(hh_ids),
            **{
                entity: set(p[foreign_keys[entity]])
                for entity in NESTED_ENTITIES
            },
        }
        subsets = {
            entity: value.loc[value[f"{entity}_id"].isin(selected_ids[entity])]
            for entity, value in entities.items()
        }
        path = output_dir / f"chunk_{len(chunks):04d}.h5"
        with pd.HDFStore(path, "w", complevel=1, complib="zlib") as out:
            for key, value in tables.items():
                entity = key.strip("/")
                subset = (
                    subsets[entity]
                    if entity in ENTITIES
                    else _subset_extra_table(value, selected_ids)
                )
                out.put(key, subset, format="fixed")
        chunks.append(
            {
                "path": str(path),
                "household_count": len(subsets["household"]),
                "person_count": len(subsets["person"]),
                "weight_totals": {
                    entity: _weight_total(
                        subsets[entity], entity, subsets["household"]
                    )
                    for entity in ("household", "person")
                },
            }
        )
    summed_weights = {
        entity: math.fsum(chunk["weight_totals"][entity] for chunk in chunks)
        for entity in full_weights
    }
    for entity, full in full_weights.items():
        if not math.isclose(full, summed_weights[entity], rel_tol=1e-12):
            raise ValueError(f"Chunking changed {entity} weight total")
    return {
        "chunk_paths": [chunk["path"] for chunk in chunks],
        "household_count": len(households),
        "person_count": len(persons),
        "chunk_count": len(chunks),
        "chunk_size": chunk_size,
        "nesting": nesting,
        "person_weight_source": (
            "person.person_weight"
            if "person_weight" in persons
            else "household.household_weight mapped to persons"
        ),
        "full_weight_totals": full_weights,
        "chunk_weight_totals": [chunk["weight_totals"] for chunk in chunks],
        "summed_chunk_weight_totals": summed_weights,
        "chunks": chunks,
    }
