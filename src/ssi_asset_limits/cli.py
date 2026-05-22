"""Command line interface for SSI asset limit analysis."""

from __future__ import annotations

import argparse

from .constants import (
    ANALYSIS_YEAR,
    DEFAULT_COUPLE_LIMIT,
    DEFAULT_INDIVIDUAL_LIMIT,
)
from .pipeline import generate_all_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate SSI asset limit reform dashboard data."
    )
    parser.add_argument(
        "--output-dir",
        default="public/data",
        help="Directory for generated CSV files.",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Optional dataset path or Hugging Face URL for PolicyEngine US.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=ANALYSIS_YEAR,
        help="Policy year to analyze.",
    )
    parser.add_argument(
        "--individual-limit",
        type=float,
        default=DEFAULT_INDIVIDUAL_LIMIT,
        help="Reformed SSI resource limit for unmarried individuals.",
    )
    parser.add_argument(
        "--couple-limit",
        type=float,
        default=DEFAULT_COUPLE_LIMIT,
        help="Reformed SSI resource limit for married couples.",
    )
    parser.add_argument(
        "--skip-poverty",
        action="store_true",
        help="Generate only SSI fiscal and participation metrics.",
    )
    parser.add_argument(
        "--external-benchmark-comparison",
        action="store_true",
        help=(
            "Write CBPP/OACT comparison scalars for the $10k/$20k proposal."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    generate_all_data(
        output_dir=args.output_dir,
        dataset=args.dataset,
        year=args.year,
        include_poverty=not args.skip_poverty,
        individual_limit=args.individual_limit,
        couple_limit=args.couple_limit,
        include_external_benchmark_comparison=(
            args.external_benchmark_comparison
        ),
    )


if __name__ == "__main__":
    main()
