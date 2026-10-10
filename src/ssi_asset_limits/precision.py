"""How much the estimates could move if the population sample were redrawn.

The certified population is small and sparse: most of its person records
carry zero weight, and a reform that reaches a narrow group can rest on a few
dozen records. This module puts a sampling range on each published count and
dollar figure and reports how many records stand behind it.

The range is a household bootstrap: households are resampled with replacement
(as Poisson(1) multiplicities, the usual large-sample form), keeping each
household's people and weights together, and the statistic is recomputed.
The 5th and 95th percentiles of 2,000 replicates give a 90 percent range. It
reflects only which households happen to be in the sample. It does not
include uncertainty in the imputed savings, the take-up flags, the weights'
calibration or the rules, so the true uncertainty is wider.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .calculators import CBPP_AGE_GROUPS

BASELINE = "baseline"
REPLICATES = 2_000
SEED = 20261010
RANGE = (5, 95)


def _age_masks(age: pd.Series) -> dict[str, pd.Series]:
    masks = {}
    for group, _, lower, upper in CBPP_AGE_GROUPS:
        mask = pd.Series(True, index=age.index)
        if lower is not None:
            mask &= age >= lower
        if upper is not None:
            mask &= age < upper
        masks[group] = mask
    masks["total_all_ages"] = pd.Series(True, index=age.index)
    return masks


def person_contributions(persons: pd.DataFrame, key: str) -> pd.DataFrame:
    """Each person's weighted contribution to each statistic of a scenario."""

    weights = persons["person_weight"]
    base = persons[f"ssi_{BASELINE}"]
    reform = persons[f"ssi_{key}"]
    new = (base <= 0) & (reform > 0)
    columns = {}
    for group, mask in _age_masks(persons["age"]).items():
        columns[("new_recipients", group)] = weights * (new & mask)
        columns[("annual_ssi_cost", group)] = weights * (reform - base) * mask
        columns[("baseline_recipients", group)] = weights * ((base > 0) & mask)
    return pd.DataFrame(columns)


def bootstrap_ranges(
    contributions: pd.DataFrame,
    household_id: pd.Series,
    replicates: int = REPLICATES,
    seed: int = SEED,
) -> pd.DataFrame:
    """Percentile range of each column's total over household resamples."""

    totals = contributions.groupby(household_id.to_numpy()).sum()
    # Households that contribute nothing to any statistic cannot change a
    # replicate, so only the others need multiplicities.
    totals = totals.loc[(totals != 0).any(axis=1)]
    rng = np.random.default_rng(seed)
    if len(totals):
        multiplicity = rng.poisson(1.0, size=(replicates, len(totals)))
        draws = multiplicity @ totals.to_numpy()
    else:
        draws = np.zeros((replicates, contributions.shape[1]))
    low, high = np.percentile(draws, RANGE, axis=0)
    return pd.DataFrame(
        {"low": low, "high": high},
        index=contributions.columns,
    )


def record_counts(
    contributions: pd.DataFrame, weights: pd.Series
) -> pd.DataFrame:
    """Records behind each statistic, and their effective number.

    The effective number is Kish's (sum w)^2 / sum w^2 over the contributing
    records: the size of an equally weighted sample with the same precision.
    """

    rows = {}
    for column in contributions.columns:
        used = weights[contributions[column] != 0]
        rows[column] = {
            "records": int(len(used)),
            "effective_records": float(used.sum() ** 2 / (used**2).sum())
            if len(used)
            else 0.0,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def scenario_precision(persons: pd.DataFrame, key: str) -> pd.DataFrame:
    """Estimate, 90 percent range and record counts for one scenario."""

    contributions = person_contributions(persons, key)
    ranges = bootstrap_ranges(contributions, persons["household_id"])
    counts = record_counts(contributions, persons["person_weight"])
    table = pd.concat(
        [contributions.sum().rename("estimate"), ranges, counts], axis=1
    )
    table.index = pd.MultiIndex.from_tuples(
        table.index, names=["statistic", "age_group"]
    )
    return table.reset_index()
