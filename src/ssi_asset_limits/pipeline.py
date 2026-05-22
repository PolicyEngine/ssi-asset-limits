"""Data-generation pipeline for the SSI asset limit dashboard."""

from __future__ import annotations

from pathlib import Path

from .benchmarks import calculate_external_benchmark_comparison
from .calculators import calculate_national_summary, calculate_resource_bins
from .constants import (
    ANALYSIS_YEAR,
    DEFAULT_COUPLE_LIMIT,
    DEFAULT_INDIVIDUAL_LIMIT,
    EXTERNAL_BENCHMARK_COMPARISON_FILE,
    NATIONAL_SUMMARY_FILE,
    RESOURCE_BINS_FILE,
)
from .reform import create_asset_limit_reform


def build_simulations(
    dataset: str | None = None,
    individual_limit: float = DEFAULT_INDIVIDUAL_LIMIT,
    couple_limit: float = DEFAULT_COUPLE_LIMIT,
):
    """Create baseline and reformed PolicyEngine US simulations."""

    from policyengine_us import Microsimulation

    baseline = Microsimulation(dataset=dataset)
    reformed = Microsimulation(
        reform=create_asset_limit_reform(
            individual_limit=individual_limit,
            couple_limit=couple_limit,
        ),
        dataset=dataset,
    )
    return baseline, reformed


def generate_all_data(
    output_dir: str | Path = "public/data",
    dataset: str | None = None,
    year: int = ANALYSIS_YEAR,
    include_poverty: bool = True,
    individual_limit: float = DEFAULT_INDIVIDUAL_LIMIT,
    couple_limit: float = DEFAULT_COUPLE_LIMIT,
    include_external_benchmark_comparison: bool = False,
) -> None:
    """Generate dashboard CSVs."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print("Loading baseline and reform simulations...")
    baseline, reformed = build_simulations(
        dataset=dataset,
        individual_limit=individual_limit,
        couple_limit=couple_limit,
    )

    print("Calculating national summary...")
    national = calculate_national_summary(
        baseline, reformed, year, include_poverty=include_poverty
    )
    national.to_csv(output / NATIONAL_SUMMARY_FILE, index=False)

    if include_external_benchmark_comparison:
        print("Calculating external benchmark comparison...")
        comparison = calculate_external_benchmark_comparison(national)
        comparison.to_csv(
            output / EXTERNAL_BENCHMARK_COMPARISON_FILE, index=False
        )

    print("Calculating resource-bin impacts...")
    resource_bins = calculate_resource_bins(baseline, reformed, year)
    resource_bins.to_csv(output / RESOURCE_BINS_FILE, index=False)

    print(f"Saved dashboard data to {output}")
