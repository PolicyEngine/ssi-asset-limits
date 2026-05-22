"""Microsimulation aggregations for the SSI asset limit reform."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ResourceBin:
    label: str
    lower: float
    upper: float | None = None

    def mask(self, resources):
        lower_mask = resources >= self.lower
        if self.upper is None:
            return lower_mask
        return lower_mask & (resources < self.upper)


RESOURCE_BINS = [
    ResourceBin("Under $2,000", 0, 2_000),
    ResourceBin("$2,000 to $2,999", 2_000, 3_000),
    ResourceBin("$3,000 to $9,999", 3_000, 10_000),
    ResourceBin("$10,000 to $24,999", 10_000, 25_000),
    ResourceBin("$25,000 or more", 25_000, None),
]


def _calc(simulation, variable: str, year: int, map_to: str | None = None):
    kwargs = {"period": year}
    if map_to is not None:
        kwargs["map_to"] = map_to
    return simulation.calc(variable, **kwargs)


def _scalar(value) -> float:
    return float(value)


def _mean_or_zero(series) -> float:
    if len(series) == 0:
        return 0.0
    value = series.mean()
    if pd.isna(value):
        return 0.0
    return _scalar(value)


def calculate_core_summary(baseline, reformed, year: int) -> pd.DataFrame:
    """Calculate core SSI fiscal and participation metrics.

    `calc()` returns MicroSeries in real runs, so `.sum()` and `.mean()` are
    weighted automatically. Do not fetch or manually apply weight variables.
    """

    baseline_ssi = _calc(baseline, "ssi", year)
    reformed_ssi = _calc(reformed, "ssi", year)
    ssi_change = reformed_ssi - baseline_ssi
    gains = ssi_change > 0

    baseline_recipients = baseline_ssi > 0
    reformed_recipients = reformed_ssi > 0

    return pd.DataFrame(
        [
            {
                "metric": "annual_ssi_cost",
                "label": "Annual SSI cost",
                "value": _scalar(ssi_change.sum()),
                "unit": "currency",
            },
            {
                "metric": "baseline_recipients",
                "label": "Baseline SSI recipients",
                "value": _scalar(baseline_recipients.sum()),
                "unit": "people",
            },
            {
                "metric": "reform_recipients",
                "label": "Recipients after reform",
                "value": _scalar(reformed_recipients.sum()),
                "unit": "people",
            },
            {
                "metric": "new_recipients",
                "label": "New SSI recipients",
                "value": _scalar(
                    (~baseline_recipients & reformed_recipients).sum()
                ),
                "unit": "people",
            },
            {
                "metric": "average_gain",
                "label": "Average gain among winners",
                "value": _mean_or_zero(ssi_change[gains]),
                "unit": "currency",
            },
        ]
    )


def calculate_poverty_summary(baseline, reformed, year: int) -> pd.DataFrame:
    """Calculate person-level poverty impacts."""

    baseline_poverty = _calc(
        baseline, "person_in_poverty", year, map_to="person"
    )
    reformed_poverty = _calc(
        reformed, "person_in_poverty", year, map_to="person"
    )
    baseline_deep_poverty = _calc(
        baseline, "in_deep_poverty", year, map_to="person"
    )
    reformed_deep_poverty = _calc(
        reformed, "in_deep_poverty", year, map_to="person"
    )

    return pd.DataFrame(
        [
            {
                "metric": "poverty_rate_reduction",
                "label": "SPM poverty rate reduction",
                "value": _scalar(
                    baseline_poverty.mean() - reformed_poverty.mean()
                ),
                "unit": "rate",
            },
            {
                "metric": "people_lifted_from_poverty",
                "label": "People lifted from poverty",
                "value": _scalar((baseline_poverty & ~reformed_poverty).sum()),
                "unit": "people",
            },
            {
                "metric": "deep_poverty_rate_reduction",
                "label": "Deep poverty rate reduction",
                "value": _scalar(
                    baseline_deep_poverty.mean() - reformed_deep_poverty.mean()
                ),
                "unit": "rate",
            },
        ]
    )


def calculate_national_summary(
    baseline, reformed, year: int, include_poverty: bool = True
) -> pd.DataFrame:
    """Calculate headline national metrics."""

    rows = [calculate_core_summary(baseline, reformed, year)]
    if include_poverty:
        rows.append(calculate_poverty_summary(baseline, reformed, year))

    return pd.concat(rows, ignore_index=True)


def calculate_resource_bins(baseline, reformed, year: int) -> pd.DataFrame:
    """Calculate impacts by baseline SSI countable-resource bin."""

    resources = _calc(baseline, "ssi_countable_resources", year)
    baseline_ssi = _calc(baseline, "ssi", year)
    reformed_ssi = _calc(reformed, "ssi", year)
    ssi_change = reformed_ssi - baseline_ssi

    rows = []
    for resource_bin in RESOURCE_BINS:
        mask = resource_bin.mask(resources)
        people = _scalar(mask.sum())
        total_gain = _scalar(ssi_change[mask].sum())
        rows.append(
            {
                "resource_bin": resource_bin.label,
                "people": people,
                "ssi_increase": total_gain,
                "average_gain": (
                    0 if people == 0 else _mean_or_zero(ssi_change[mask])
                ),
            }
        )
    return pd.DataFrame(rows)
