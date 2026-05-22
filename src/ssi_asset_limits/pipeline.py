"""Data-generation pipeline for the SSI asset limit dashboard."""

from __future__ import annotations

from pathlib import Path

from .calculators import calculate_national_summary, calculate_resource_bins
from .constants import (
    ANALYSIS_YEAR,
    NATIONAL_SUMMARY_FILE,
    RESOURCE_BINS_FILE,
)
from .reform import create_asset_limit_reform


def build_simulations(dataset: str | None = None):
    """Create baseline and reformed PolicyEngine US simulations."""

    from policyengine_us import Microsimulation

    baseline = Microsimulation(dataset=dataset)
    reformed = Microsimulation(
        reform=create_asset_limit_reform(),
        dataset=dataset,
    )
    return baseline, reformed


def generate_all_data(
    output_dir: str | Path = "public/data",
    dataset: str | None = None,
    year: int = ANALYSIS_YEAR,
    include_poverty: bool = True,
) -> None:
    """Generate dashboard CSVs."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print("Loading baseline and reform simulations...")
    baseline, reformed = build_simulations(dataset=dataset)

    print("Calculating national summary...")
    national = calculate_national_summary(
        baseline, reformed, year, include_poverty=include_poverty
    )
    national.to_csv(output / NATIONAL_SUMMARY_FILE, index=False)

    print("Calculating resource-bin impacts...")
    resource_bins = calculate_resource_bins(baseline, reformed, year)
    resource_bins.to_csv(output / RESOURCE_BINS_FILE, index=False)

    print(f"Saved dashboard data to {output}")
