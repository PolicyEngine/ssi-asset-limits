# SSI Asset Limits

Analysis of removing the Supplemental Security Income resource test using
PolicyEngine US microsimulation.

The repository has two pieces:

- A Python package, `ssi_asset_limits`, that defines the reform and generates
  CSV outputs.
- A Next.js dashboard that reads the generated CSVs from `public/data`.

## Setup

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
bun install
```

## Generate Data

Use the published default PolicyEngine dataset:

```bash
uv run ssi-asset-limits-data --output-dir public/data
```

Use a locally rebuilt Enhanced CPS H5:

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
  --skip-poverty
```

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
