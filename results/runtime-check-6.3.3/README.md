# Runtime check: policyengine.py 6.2.5 against 6.3.3

The published run used policyengine.py 6.2.5 (policyengine-core 3.32.10).
policyengine.py 6.3.3, the latest release on 2026-10-13, certifies the same
US model (policyengine-us 2.2.1) and population file
(`populace-us-2024-spm-20260915`, SHA-256 `6496cc43…`) but moves
policyengine-core to 3.33.0. This check runs the published runner on both.

- `make_subset.py` writes a household subset of the certified file with seed
  20261013: every household with a new SSI recipient under either reform in
  the published run (231), 500 households with a current-law recipient, and
  1,500 other households. That is 2,231 households and 6,509 people;
  `subset.h5` SHA-256 `c1fe5216c884a5fc829c5705f2e58409e32017b7498c3a218a244ce2f97c1607`.
- `drive.py` calls `ssi_asset_limits.microcosm_run.run_worker` for current
  law and both reforms.
- The two environments differ only in policyengine and policyengine-core
  (`base-freeze.txt` and `633-freeze.txt`).
- `compare.py` compares every output column; `compare_report.json` is its
  result.

Result: every person-level output (SSI, countable resources, poverty flags
and the eligibility diagnostics) is identical in all three scenarios, and so
is every reform-minus-current-law change in household income, SNAP and income
tax. The only difference is one household's income tax (household 1163404,
weight 0.0017), $84.39 lower under policyengine-core 3.33.0 in every
scenario. It does not affect any published figure.

Reproduce from the repository root, with `$CERTIFIED_H5` the certified file and
`$RUN` the published run directory (with its `persons.csv.gz`):

```bash
uv run python results/runtime-check-6.3.3/make_subset.py "$CERTIFIED_H5" "$RUN/persons.csv.gz" subset.h5
```

Then run `drive.py` on a copy of `subset.h5` under each environment and
`compare.py` on the two output folders (`r625/out`, `r633/out`).
