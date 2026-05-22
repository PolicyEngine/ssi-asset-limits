"""Command line interface for SSI asset limit analysis."""

from __future__ import annotations

import argparse

from .constants import ANALYSIS_YEAR
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
        "--skip-poverty",
        action="store_true",
        help="Generate only SSI fiscal and participation metrics.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    generate_all_data(
        output_dir=args.output_dir,
        dataset=args.dataset,
        year=args.year,
        include_poverty=not args.skip_poverty,
    )


if __name__ == "__main__":
    main()
