"""CLI for reproducible SSI disability prediction holdout tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from .holdout import (
    HoldoutConfig,
    evaluate_policyengine_sipp_2023_holdout,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate linear-probit and random-forest SSI disability "
            "prediction models on a SIPP holdout sample."
        )
    )
    parser.add_argument(
        "--sipp-path",
        required=True,
        help="Path to the SIPP 2023 public-use pipe CSV, e.g. pu2023.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default="public/data",
        help="Directory for generated holdout metric CSV files.",
    )
    parser.add_argument(
        "--time-period",
        type=int,
        default=2024,
        help=(
            "Policy parameter year used for the SSI training-candidate screen."
        ),
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.30,
        help="Share of retained SIPP rows assigned to the holdout sample.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=271828,
        help="Random seed for the train/test split and random forest.",
    )
    parser.add_argument(
        "--rf-estimators",
        type=int,
        default=500,
        help="Number of trees in the random forest.",
    )
    parser.add_argument(
        "--rf-min-samples-leaf",
        type=int,
        default=25,
        help="Minimum leaf size for the random forest.",
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=None,
        help="Optional input row cap for quick parser/debug runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    config = HoldoutConfig(
        test_size=args.test_size,
        random_state=args.random_state,
        rf_estimators=args.rf_estimators,
        rf_min_samples_leaf=args.rf_min_samples_leaf,
    )
    print("Evaluating PE-style SIPP SSI disability holdout...", flush=True)
    evaluate_policyengine_sipp_2023_holdout(
        args.sipp_path,
        output_dir=output,
        time_period=args.time_period,
        nrows=args.nrows,
        config=config,
    )
    print(f"Saved SSI disability holdout outputs to {output}", flush=True)


if __name__ == "__main__":
    main()
