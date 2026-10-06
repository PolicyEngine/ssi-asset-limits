"""Data-generation pipeline for the SSI asset limit dashboard."""

from __future__ import annotations

from pathlib import Path

from .benchmarks import calculate_external_benchmark_comparison
from .calculators import (
    calculate_cbpp_age_group_impacts,
    calculate_national_summary,
    calculate_resource_bins,
)
from .cbpp import (
    calculate_cbpp_age_bridge,
    cbpp_adult_18_64_coefficients,
    cbpp_public_targets,
    infer_cbpp_scenario_key,
)
from .constants import (
    ANALYSIS_YEAR,
    CBPP_AGE_BRIDGE_FILE,
    CBPP_METHOD_COEFFICIENTS_FILE,
    CBPP_TARGETS_FILE,
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
    reform_start_year: int = ANALYSIS_YEAR,
):
    """Create baseline and reformed PolicyEngine US simulations."""

    from policyengine_us import Microsimulation

    baseline = Microsimulation(dataset=dataset)
    reformed = Microsimulation(
        reform=create_asset_limit_reform(
            individual_limit=individual_limit,
            couple_limit=couple_limit,
            start_year=reform_start_year,
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
    include_cbpp_replication: bool = False,
    cbpp_excludes_retirement_accounts: bool = False,
    reform_start_year: int | None = None,
) -> None:
    """Generate dashboard CSVs."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print("Loading baseline and reform simulations...")
    if reform_start_year is None:
        reform_start_year = year
    baseline, reformed = build_simulations(
        dataset=dataset,
        individual_limit=individual_limit,
        couple_limit=couple_limit,
        reform_start_year=reform_start_year,
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

    if include_cbpp_replication:
        print("Writing CBPP public-method replication tables...")
        cbpp_public_targets().to_csv(output / CBPP_TARGETS_FILE, index=False)
        cbpp_adult_18_64_coefficients().to_csv(
            output / CBPP_METHOD_COEFFICIENTS_FILE,
            index=False,
        )
        scenario_key = infer_cbpp_scenario_key(
            individual_limit=individual_limit,
            couple_limit=couple_limit,
            excludes_retirement_accounts=cbpp_excludes_retirement_accounts,
        )
        age_impacts = calculate_cbpp_age_group_impacts(
            baseline, reformed, year
        )
        cbpp_age_bridge = calculate_cbpp_age_bridge(
            age_impacts,
            scenario_key=scenario_key,
        )
        cbpp_age_bridge.to_csv(output / CBPP_AGE_BRIDGE_FILE, index=False)

    print("Calculating resource-bin impacts...")
    resource_bins = calculate_resource_bins(baseline, reformed, year)
    resource_bins.to_csv(output / RESOURCE_BINS_FILE, index=False)

    print(f"Saved dashboard data to {output}")
