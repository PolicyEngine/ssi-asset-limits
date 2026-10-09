"""CLI for SSI asset-limit decomposition experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

from .decomposition import (
    DecompositionConfig,
    run_decomposition,
    write_decomposition_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run sequential SSI asset-limit prediction experiments across "
            "CBPP-style SIPP models, PolicyEngine-style SIPP models, and "
            "optional eCPS microsimulation outputs."
        )
    )
    parser.add_argument(
        "--sipp-2024-path",
        required=True,
        help="Path to the 2024 SIPP public-use pipe CSV.",
    )
    parser.add_argument(
        "--sipp-2014-path",
        default=None,
        help=(
            "Optional path to pu2014w2.csv.gz. If omitted, the 2014 file is "
            "downloaded unless --skip-2014 is set."
        ),
    )
    parser.add_argument(
        "--sipp-2014-data-dir",
        default=".cache/sipp2014w2",
        help="Directory for downloaded 2014 SIPP files.",
    )
    parser.add_argument(
        "--output-dir",
        default=".local-results/sipp-decomposition",
        help="Directory for decomposition CSV outputs.",
    )
    parser.add_argument(
        "--ecps-results-dir",
        default=None,
        help=(
            "Optional completed eCPS output directory with "
            "national_summary.csv and optionally cbpp_age_bridge.csv "
            "for step e."
        ),
    )
    parser.add_argument(
        "--individual-limit",
        type=float,
        default=10_000,
        help="Reform individual resource limit.",
    )
    parser.add_argument(
        "--couple-limit",
        type=float,
        default=20_000,
        help="Reform couple resource limit.",
    )
    parser.add_argument(
        "--sipp-2024-monthly-fbr",
        type=float,
        default=914.0,
        help=(
            "Monthly individual FBR for the 2024 SIPP release's reference "
            "year, used in the CBPP-style simple income screen."
        ),
    )
    parser.add_argument(
        "--sipp-2024-time-period",
        type=int,
        default=2024,
        help="Policy parameter year for the PE-style SIPP screen.",
    )
    parser.add_argument(
        "--income-limit-multiple",
        type=float,
        default=2.0,
        help="Monthly FBR multiple for CBPP-style income eligibility.",
    )
    parser.add_argument(
        "--rf-estimators",
        type=int,
        default=500,
        help="Random-forest tree count.",
    )
    parser.add_argument(
        "--rf-min-samples-leaf",
        type=int,
        default=25,
        help="Random-forest minimum leaf size.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=271828,
        help="Random seed for random-forest experiments.",
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=None,
        help="Optional row cap for quick parser/debug runs.",
    )
    parser.add_argument(
        "--skip-2014",
        action="store_true",
        help="Skip the 2014 CBPP-reconstruction step.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = DecompositionConfig(
        sipp_2024_path=Path(args.sipp_2024_path),
        sipp_2014_path=(
            Path(args.sipp_2014_path) if args.sipp_2014_path else None
        ),
        sipp_2014_data_dir=Path(args.sipp_2014_data_dir),
        output_dir=Path(args.output_dir),
        ecps_results_dir=(
            Path(args.ecps_results_dir) if args.ecps_results_dir else None
        ),
        individual_limit=args.individual_limit,
        couple_limit=args.couple_limit,
        sipp_2024_monthly_fbr=args.sipp_2024_monthly_fbr,
        sipp_2024_time_period=args.sipp_2024_time_period,
        income_limit_multiple=args.income_limit_multiple,
        rf_estimators=args.rf_estimators,
        rf_min_samples_leaf=args.rf_min_samples_leaf,
        random_state=args.random_state,
        nrows=args.nrows,
        run_2014=not args.skip_2014,
    )
    print("Running SSI asset-limit decomposition...", flush=True)
    results, diagnostics = run_decomposition(config)
    write_decomposition_outputs(results, diagnostics, config.output_dir)
    print(f"Saved decomposition outputs to {config.output_dir}", flush=True)


if __name__ == "__main__":
    main()
