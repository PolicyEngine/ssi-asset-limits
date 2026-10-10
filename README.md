# SSI asset limits

What raising Supplemental Security Income's asset limits from $2,000 and
$3,000 to $10,000 and $20,000, or removing them, would cost in 2026 and who
would gain, estimated with PolicyEngine's microsimulation on Microcosm's
population of US households.

The repository has two parts:

- `ssi_asset_limits`, a Python package that runs the scenarios and writes the
  result tables.
- A Next.js page (mounted at `/us/ssi-asset-limits`) that reads
  `public/data/results.json`.

## Reproduce the published numbers

Each step writes into a fresh directory; the runner refuses a directory that
already holds a finished run (`results/microcosm-625-spm0915` keeps the
published run's metadata and checks, so do not reuse it).

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
RUN=.local-results/reproduce
uv run ssi-asset-limits-run --out-dir $RUN/certified
uv run ssi-asset-limits-admin-checks $RUN/certified --out-dir $RUN/admin-checks
uv run python scripts/ss_restore_sensitivity.py $RUN/certified $RUN/ss-restored
uv run ssi-asset-limits-run --variant resource_deeming --out-dir $RUN/resource-deeming
uv run ssi-asset-limits-publish $RUN/certified --out-dir public/data \
  --checks-dir $RUN/admin-checks \
  --sensitivity $RUN/ss-restored --sensitivity $RUN/resource-deeming
```

`ssi-asset-limits-run` uses the certified PolicyEngine bundle pinned in
`pyproject.toml` (policyengine.py, policyengine-us and the Microcosm dataset
it certifies), runs current law and both reforms for 2026, and writes person
and household tables plus `run_metadata.json`. It runs the population in
household batches, one process per batch. Every unit PolicyEngine computes
(marital unit, tax unit, SPM unit, family) sits inside one household, and no
published output depends on other households under the run's settings, which
leave health benefits out of household income; so batching gives the same
answer as a single run. Each batch is admitted with 18 GB of memory.

`ssi-asset-limits-admin-checks` compares the run's current-law caseload with
SSA tables it is not targeted to, and records the hashes of the run tables it
read; `ssi-asset-limits-publish` refuses check tables whose hashes do not
match the run it publishes. The two sensitivity runs are shown beside the
estimate and are never published as it: the publisher refuses a variant run
as its main input.

`ssi-asset-limits-publish` turns the run into the app's data; every figure is
a weighted sum over that run, with nothing scaled from other runs.

## Comparisons

`src/ssi_asset_limits/comparators.py` holds the published figures the page
shows next to ours, each with its source:

- SSA, SSI Monthly Statistics, December 2024, Table 1: people with a federal
  SSI payment by age (the current-law check).
- CBPP, "The Case for Updating SSI Asset Limits" (2023), Table 1: new
  beneficiaries by age under each scenario, from 2014 SIPP data.
- SSA Office of the Chief Actuary letters of January 29, 2024 (S. 2767) and
  August 7, 2026 (a proposal similar to S. 1234): annual cost of $10,000 and
  $20,000 limits indexed to inflation.

Copies of the SSA and OACT sources are in `sources/` with SHA-256 hashes.

## Known gaps

The page's "How to read these numbers" section explains these in plain
language:

- Claiming: each person's take-up flag is drawn at one rate per age group and
  does not fall with savings (PolicyEngine/microcosm#584).
- Children: the population has almost no children under 15 who meet SSI's
  disability standard (PolicyEngine/microcosm#453), and PolicyEngine does not
  yet deem a parent's resources to a child (PolicyEngine/policyengine-us#3557).
- Couples: PolicyEngine does not yet deem an ineligible spouse's resources,
  and the population records each household's savings on one person.
- Savings: imputed from SIPP 2023 and SCF 2022, not calibrated; only bank
  accounts, stocks and bonds count.

## CBPP replication tools

The package also carries the tools used to replicate CBPP's method:

- `ssi-asset-limits-fit-cbpp` fits CBPP's published adult (18–64)
  participation equation on SIPP 2014 Wave 2 or SIPP 2023 and writes the
  fitted coefficients beside CBPP's (`results/cbpp-method-fit/`).
- `ssi-asset-limits-holdout` compares a linear probit with a random forest on
  a SIPP 2023 SSI disability frame.
- `ssi-asset-limits-decomposition` decomposes SIPP SSI receipt.

## Verify

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
bun install --frozen-lockfile
bun run build
```

Run the page locally with `bun run dev`.
