"""Write a household subset of the certified frame for a runtime differential.

Selection (seed 20261013): every household with a new SSI recipient under
either reform in the certified run, 500 households with a current-law SSI
recipient, and 1,500 other households drawn at random. Tables are subset the
way ssi_asset_limits.microcosm_chunks.split_household_dataset subsets a chunk.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ssi_asset_limits.microcosm_chunks import (
    ENTITIES,
    NESTED_ENTITIES,
    _subset_extra_table,
    person_entity_id_column,
)

source, run_persons, out = (
    Path(sys.argv[1]),
    Path(sys.argv[2]),
    Path(sys.argv[3]),
)
p = pd.read_csv(
    run_persons,
    usecols=["household_id", "ssi_baseline", "ssi_ten_twenty", "ssi_no_limit"],
)
new = p[
    (p.ssi_baseline <= 0) & ((p.ssi_ten_twenty > 0) | (p.ssi_no_limit > 0))
].household_id.unique()
rng = np.random.default_rng(20261013)
cur = np.setdiff1d(p[p.ssi_baseline > 0].household_id.unique(), new)
cur_s = rng.choice(cur, size=min(500, len(cur)), replace=False)
rest = np.setdiff1d(p.household_id.unique(), np.union1d(new, cur))
rest_s = rng.choice(rest, size=1500, replace=False)
chosen = set(np.concatenate([new, cur_s, rest_s]).tolist())
with pd.HDFStore(source, "r") as store:
    tables = {key: store[key] for key in store.keys()}
persons, households = tables["/person"], tables["/household"]
hh_key = person_entity_id_column(persons, "household")
pp = persons[persons[hh_key].isin(chosen)]
selected = {
    "person": set(pp.person_id),
    "household": chosen,
    **{
        e: set(pp[person_entity_id_column(persons, e)])
        for e in NESTED_ENTITIES
    },
}
with pd.HDFStore(out, "w", complevel=1, complib="zlib") as store:
    for key, value in tables.items():
        entity = key.strip("/")
        if entity in ENTITIES:
            value = value.loc[value[f"{entity}_id"].isin(selected[entity])]
        else:
            value = _subset_extra_table(value, selected)
        store.put(key, value, format="fixed")
print(
    json.dumps(
        {
            "new_recipient_households": len(new),
            "current_sample": len(cur_s),
            "random_sample": len(rest_s),
            "households": len(chosen),
            "persons": len(pp),
        }
    )
)
