"""CLI for fitting CBPP-style SIPP participation equations."""

from __future__ import annotations

import argparse
from pathlib import Path

from .cbpp import (
    CBPP_SIPP_FORMATS,
    SIPP_FORMAT_2014_WAVE2,
    build_cbpp_adult_18_64_training_frame,
    calculate_cbpp_adult_18_64_scenario_counts,
    download_sipp_2014_wave2,
    fit_cbpp_adult_18_64_probit,
    infer_sipp_format_from_columns,
    read_sipp_2014_wave2,
)
from .constants import (
    CBPP_ADULT_SCENARIO_COUNTS_FILE,
    CBPP_FIT_DIAGNOSTICS_FILE,
    CBPP_FITTED_COEFFICIENTS_FILE,
)

SIPP_CHUNK_SIZE = 100_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit CBPP-style SSI/SSDI participation probit models."
    )
    parser.add_argument(
        "--output-dir",
        default="public/data",
        help="Directory for generated coefficient and diagnostic CSV files.",
    )
    parser.add_argument(
        "--data-dir",
        default=".cache/sipp2014w2",
        help="Directory for downloaded SIPP 2014 Wave 2 files.",
    )
    parser.add_argument(
        "--sipp-path",
        default=None,
        help="Optional path to pu2014w2.csv.gz. Skips download if supplied.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not download SIPP files when --sipp-path is omitted.",
    )
    parser.add_argument(
        "--include-imputed",
        action="store_true",
        help="Keep Census-imputed key values instead of matching CBPP's drop.",
    )
    parser.add_argument(
        "--sipp-format",
        choices=["auto", *CBPP_SIPP_FORMATS],
        default="auto",
        help=(
            "SIPP file layout. Defaults to auto for --sipp-path and "
            "2014-wave2 for downloaded data."
        ),
    )
    parser.add_argument(
        "--monthly-fbr",
        type=float,
        default=None,
        help=(
            "Monthly individual SSI FBR used by the simple income screen. "
            "Defaults to the selected SIPP format's reference year."
        ),
    )
    parser.add_argument(
        "--income-limit-multiple",
        type=float,
        default=2.0,
        help=(
            "Simple monthly FBR multiple used for the public-use income "
            "eligibility screen before full SSI deeming is implemented."
        ),
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=None,
        help="Optional row cap for quick parser/debug runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if args.sipp_path is not None:
        sipp_path = Path(args.sipp_path)
        sipp_format = _resolve_sipp_format(sipp_path, args.sipp_format)
    elif args.no_download:
        raise FileNotFoundError("--sipp-path is required with --no-download")
    else:
        print("Downloading SIPP 2014 Wave 2 if needed...", flush=True)
        sipp_path = download_sipp_2014_wave2(args.data_dir)
        sipp_format = SIPP_FORMAT_2014_WAVE2

    print(f"Reading {CBPP_SIPP_FORMATS[sipp_format].label}...", flush=True)
    training_frame, frame_diagnostics = _build_training_frame(
        sipp_path,
        observed_only=not args.include_imputed,
        sipp_format=sipp_format,
        monthly_fbr=args.monthly_fbr,
        income_limit_multiple=args.income_limit_multiple,
        nrows=args.nrows,
    )

    print("Fitting weighted probit...", flush=True)
    coefficients, fit_diagnostics = fit_cbpp_adult_18_64_probit(training_frame)
    coefficients.to_csv(output / CBPP_FITTED_COEFFICIENTS_FILE, index=False)
    scenario_counts = calculate_cbpp_adult_18_64_scenario_counts(
        training_frame,
        coefficients,
    )
    scenario_counts.to_csv(
        output / CBPP_ADULT_SCENARIO_COUNTS_FILE,
        index=False,
    )

    diagnostics = {
        **frame_diagnostics,
        **fit_diagnostics,
        "observed_only": not args.include_imputed,
        "income_limit_multiple": args.income_limit_multiple,
        "sipp_file": sipp_path.name,
        "sipp_format": sipp_format,
        "sipp_source": CBPP_SIPP_FORMATS[sipp_format].source_description,
        "sipp_source_url": CBPP_SIPP_FORMATS[sipp_format].source_url,
    }
    diagnostics_rows = [
        {"metric": metric, "value": value}
        for metric, value in diagnostics.items()
    ]
    import pandas as pd

    pd.DataFrame(diagnostics_rows).to_csv(
        output / CBPP_FIT_DIAGNOSTICS_FILE,
        index=False,
    )
    print(f"Saved fitted CBPP equation outputs to {output}", flush=True)


def _build_training_frame(
    sipp_path: Path,
    *,
    observed_only: bool,
    sipp_format: str,
    monthly_fbr: float | None,
    income_limit_multiple: float,
    nrows: int | None,
):
    required_columns = list(CBPP_SIPP_FORMATS[sipp_format].required_columns)
    if nrows is not None:
        data = read_sipp_2014_wave2(
            sipp_path,
            columns=required_columns,
            nrows=nrows,
        )
        return build_cbpp_adult_18_64_training_frame(
            data,
            observed_only=observed_only,
            sipp_format=sipp_format,
            monthly_fbr=monthly_fbr,
            income_limit_multiple=income_limit_multiple,
        )

    frames = []
    count_diagnostics = {
        "raw_rows": 0.0,
        "december_rows": 0.0,
        "adult_18_64_rows": 0.0,
        "income_eligible_rows": 0.0,
        "observed_rows": 0.0,
        "fit_rows": 0.0,
    }
    reader = read_sipp_2014_wave2(
        sipp_path,
        columns=required_columns,
        chunksize=SIPP_CHUNK_SIZE,
    )
    for chunk_number, chunk in enumerate(reader, start=1):
        frame, diagnostics = build_cbpp_adult_18_64_training_frame(
            chunk,
            observed_only=observed_only,
            sipp_format=sipp_format,
            monthly_fbr=monthly_fbr,
            income_limit_multiple=income_limit_multiple,
        )
        frames.append(frame)
        for metric in count_diagnostics:
            count_diagnostics[metric] += diagnostics[metric]
        print(
            "Processed "
            f"{count_diagnostics['raw_rows']:,.0f} SIPP rows; "
            f"{count_diagnostics['fit_rows']:,.0f} fit rows retained "
            f"after chunk {chunk_number}.",
            flush=True,
        )

    import numpy as np
    import pandas as pd

    training_frame = pd.concat(frames, ignore_index=True)
    weights = training_frame["weight"].astype(float)
    diagnostics = dict(count_diagnostics)
    diagnostics["weighted_participation_rate"] = float(
        np.average(
            training_frame["participates_ssi_or_ssdi"].astype(float),
            weights=weights,
        )
    )
    diagnostics["weighted_mean_income"] = float(
        np.average(
            training_frame["countable_income"].astype(float),
            weights=weights,
        )
    )
    diagnostics["weighted_mean_resources"] = float(
        np.average(
            training_frame["countable_assets"].astype(float),
            weights=weights,
        )
    )
    return training_frame, diagnostics


def _resolve_sipp_format(sipp_path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    columns = read_sipp_2014_wave2(sipp_path, nrows=0).columns
    return infer_sipp_format_from_columns(columns)


if __name__ == "__main__":
    main()
