from ssi_asset_limits.cli import build_parser


def test_cli_parses_dataset_and_output_dir():
    args = build_parser().parse_args(
        [
            "--dataset",
            "/tmp/enhanced_cps_2024.h5",
            "--output-dir",
            "public/data",
            "--year",
            "2026",
            "--individual-limit",
            "10000",
            "--couple-limit",
            "20000",
            "--reform-start-year",
            "2025",
            "--skip-poverty",
            "--external-benchmark-comparison",
            "--cbpp-replication",
            "--cbpp-excludes-retirement-accounts",
        ]
    )

    assert args.dataset == "/tmp/enhanced_cps_2024.h5"
    assert args.output_dir == "public/data"
    assert args.year == 2026
    assert args.individual_limit == 10_000
    assert args.couple_limit == 20_000
    assert args.reform_start_year == 2025
    assert args.skip_poverty is True
    assert args.external_benchmark_comparison is True
    assert args.cbpp_replication is True
    assert args.cbpp_excludes_retirement_accounts is True
