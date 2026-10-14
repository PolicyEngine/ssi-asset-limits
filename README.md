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
SSA tables it is not targeted to, and records the hashes of the run tables
and household chunks it read; `ssi-asset-limits-publish` refuses check tables
whose hashes do not match the run it publishes. The two sensitivity runs are
shown beside the estimate and are never published as it: the publisher
refuses a variant run as its main input, and refuses a sensitivity run whose
dataset, model, people or per-person weights differ from the published run's,
or a spliced rerun that changes more households than it reran.

`ssi-asset-limits-publish` turns the run into the app's data; every figure is
a weighted sum over that run, with nothing scaled from other runs.

### Current certified bundle

The published run used policyengine.py 6.2.5 (policyengine-core 3.32.10).
As of 2026-10-13 the latest release, policyengine.py 6.3.3, certifies the
same US model and population file: policyengine-us 2.2.1 (wheel SHA-256
`0993a6c7…`) and Microcosm `populace-us-2024-spm-20260915`
(`populace_us_2024.h5`, SHA-256 `6496cc43…`). It also moves policyengine-core
to 3.33.0. Running the published runner on both, over every household with a
new recipient and 2,000 sampled others, gives identical SSI, poverty and
reform changes; one household's income tax differs by $84 in every scenario
(`results/runtime-check-6.3.3/`). Microcosm has published no newer release to
`latest.json` since 2026-09-15.

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
language, with every figure computed from the published data:

- Claiming: everyone who reported SSI in the CPS keeps a yes; everyone else
  is drawn at one rate per age group that does not fall with savings
  (PolicyEngine/microcosm#584). Some new recipients aged 18 to 64 report SSI
  in the CPS but are kept off it by imputed savings
  (`results/admin-checks/new_recipients_by_reporting.csv`).
- Social Security: the population file zeroes CPS-reported Social Security
  for many people (PolicyEngine/microcosm#1178); a spliced rerun with it
  restored is shown as a sensitivity. Microcosm fixed the build code in
  PolicyEngine/microcosm#1186 (merged 2026-10-12). The certified file still
  has the defect; the fix reaches this estimate only when a file rebuilt
  with the corrected code (a fiscal-only refresh of an old base does not
  repair it) is certified and the analysis is rerun.
- Children: the population has almost no children under 15 who meet SSI's
  disability standard (PolicyEngine/microcosm#509, not merged), and
  policyengine-us 2.2.1 does not deem a parent's resources to a child.
  PolicyEngine/policyengine-us#10040 added deeming in policyengine-us
  2.38.14 (2026-10-11), which the certified bundle predates. The PR's 2.2.1
  companion runs as a sensitivity; its policy classes are the merged code's,
  except that 2.2.1 has no parent links, so it finds parents through the tax
  unit and household.
- Couples and households: policyengine-us 2.2.1 does not deem an ineligible
  spouse's resources (same PR). The population records each household's
  savings on one person, the lowest line number on the CPS roster
  (PolicyEngine/microcosm#1215), so everyone else in the household holds $0
  of their own; and it has far more married people aged 65 and over, and far fewer
  living alone, than the CPS and ACS (PolicyEngine/microcosm#1212).
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
bun run test
bun run build
```

Run the page locally with `bun run dev`.
