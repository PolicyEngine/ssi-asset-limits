# SSI Asset Limits

Analysis of removing the Supplemental Security Income resource test using
PolicyEngine US microsimulation.

The repository has two pieces:

- A Python package, `ssi_asset_limits`, that defines the reforms and scores
  them on the certified US population.
- A Next.js dashboard that reads `public/data/results.json`.

## Setup

```bash
uv venv --python 3.13 .venv
uv pip install -e ".[dev]"
bun install
```

## Generate Data

Score current law, $10,000 individual / $20,000 couple resource limits, and
removal of the resource test for 2026, then publish the dashboard data:

```bash
uv run ssi-asset-limits-run --out-dir results/microcosm-625-spm0915
uv run ssi-asset-limits-publish results/microcosm-625-spm0915 --out-dir public/data
```

The runner pins `policyengine[us]==6.2.5`, bundle `us-6.2.5`, and
`policyengine-us==2.2.1`. It materializes the certified `populace_us_2024`
build `populace-us-2024-spm-20260915` through PolicyEngine's dataset loader
and verifies SHA-256
`6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84`.
Each chunk uses `managed_microsimulation(dataset=<local chunk>,
allow_unmanaged=True)`, retaining the managed bundle's legacy input renames
and SPM poverty selection.

The population is run in household batches, which is exact because every
person, marital unit, tax unit, SPM unit, and family nests within one
household. The runner proves that nesting before splitting and checks that
person and household weights sum to the full population's totals. It
preserves all HDF tables, IDs, and `_time_period` data. Each scenario and
chunk runs sequentially in a fresh process through `heavy --mem 16`; the
initial batch size is 8,000 households. The machine's `heavy` admission gate
must be on `PATH` and able to inspect process information.

The partition proof compares the unchanged 2024 source-file weights. If the
file has no person-weight column, each person inherits their household's
weight. Scored outputs use the model's 2026 weights, including population
uprating, so their totals can differ from the source-file totals.

Annual SSI is the sum of all twelve 2026 monthly values. The person
diagnostics store annual monthly boolean means, so a value of `0.5` means
the condition held in six months; positive annual SSI identifies a
recipient. Age and countable resources use January snapshots when defined
monthly, and diagnostics also retain January flags for marital-unit
checks. Poverty and household income outputs use annual 2026 values.

The run directory contains `persons.csv.gz`, `households.csv.gz`,
`persons_diagnostics.csv.gz`, and `run_metadata.json`. Metadata separates
the app's provenance fields from execution diagnostics, including batch
sizes, peak resident memory, elapsed time, and the installed package
freeze. Large row-level files stay outside version control; published
summaries can be regenerated with the second command above. Engine runs
are separate from the unit tests.

For older analysis workflows, use a locally rebuilt Enhanced CPS H5:

```bash
uv run ssi-asset-limits-data \
  --dataset /path/to/enhanced_cps_2024.h5 \
  --output-dir public/data
```

For faster local comparisons that only need SSI fiscal and participation
metrics:

```bash
uv run ssi-asset-limits-data \
  --dataset /path/to/enhanced_cps_2024.h5 \
  --output-dir public/data \
  --skip-poverty
```

Model the $10,000 individual / $20,000 couple limit proposal:

```bash
uv run ssi-asset-limits-data \
  --dataset /path/to/enhanced_cps_2024.h5 \
  --output-dir public/data \
  --individual-limit 10000 \
  --couple-limit 20000 \
  --skip-poverty \
  --external-benchmark-comparison
```

The external benchmark comparison starts from PolicyEngine's post-take-up
estimate, scales the new-recipient count to CBPP's 224,000 new-beneficiary
estimate, then reports the additional benefit-amount scale needed to match
OACT's $1.0 billion 2026 cost estimate.

Write CBPP replication tables for the public $10,000 / $20,000 benchmark:

```bash
uv run ssi-asset-limits-data \
  --dataset /path/to/enhanced_cps_2024.h5 \
  --output-dir public/data \
  --individual-limit 10000 \
  --couple-limit 20000 \
  --skip-poverty \
  --cbpp-replication
```

This writes:

- `cbpp_targets.csv`: CBPP's rounded public Table 1 targets.
- `cbpp_method_coefficients.csv`: CBPP's published adult 18-64 equation
  coefficients and an explicit marker that the child and 65+ equations were
  not published.
- `cbpp_age_bridge.csv`: PolicyEngine age-group impacts scaled to CBPP's
  public age targets. For the $10,000 / $20,000 scenario, CBPP suppresses the
  65+ row; the bridge infers the residual from the published all-age total
  minus the published child and adult rows.

Fit the published adult 18-64 CBPP equation from SIPP 2014 Wave 2:

```bash
uv run ssi-asset-limits-fit-cbpp --output-dir results/cbpp-method-fit
```

This downloads the Census SIPP 2014 Wave 2 public-use pipe file if needed and
writes:

- `cbpp_fitted_coefficients.csv`: weighted-probit coefficients from the
  public-use SIPP file, with CBPP's published adult coefficients shown beside
  the fitted estimates.
- `cbpp_fit_diagnostics.csv`: row counts and fit diagnostics.

The first fitter uses the published adult 18-64 specification and excludes
records with Census-imputed key income, asset, disability, and program
participation values. Census SIPP status flags 2-8 are treated as imputed;
flags 0-1 and recode flag 9 are retained. It uses a simple public-use income
screen pending full SSI deeming on SIPP.

Run the same adult 18-64 CBPP-style equation on the newer 2023 SIPP release:

```bash
uv run ssi-asset-limits-fit-cbpp \
  --sipp-path /path/to/pu2023.csv \
  --sipp-format 2023-calendar \
  --output-dir results/cbpp-method-fit
```

When `--sipp-format` is omitted, the fitter infers 2014 vs 2023 from the
SSI receipt column names. The 2023 format defaults to the 2022 individual
monthly federal benefit rate for the simple income screen because the 2023
SIPP release covers reference year 2022.

Run a reproducible holdout test of model form on the PE-style SIPP 2023 SSI
disability frame:

```bash
uv run ssi-asset-limits-holdout \
  --sipp-path /path/to/pu2023.csv \
  --output-dir public/data
```

This writes:

- `ssi_disability_holdout_metrics.csv`: weighted holdout AUC, average
  precision, Brier score, log loss, and mean predicted probability for a
  linear-probit model and a random forest using the same predictors.
- `ssi_disability_holdout_diagnostics.csv`: frame row counts, weighted target
  rates, split settings, random-forest settings, and the predictor list.

The holdout isolates model form. It uses the same SIPP target, candidate
screen, predictors, train/test split, and weights for both methods.

## Verify

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
bun run build
```

## App

```bash
bun run dev
```

The app is mounted at `/us/ssi-asset-limits`.
