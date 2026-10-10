# Which reform this run used

`run_metadata.json` records `code_commit` efb535b, but the reform module the
workers imported was the working-tree copy that was committed minutes later
as 371a965 (`src/ssi_asset_limits/sensitivity/ssi_resource_deeming_reform.py`,
SHA-256 `e48082fa937f95eccf5e9105829a4d4786cbab3c1c298a75f5cc6947b3f07056`
at that commit): the 2.2.1 companion of PolicyEngine/policyengine-us#10040 at
51d64d4904. During the run only the module's docstring changed.

This run's person, household and diagnostic tables are identical, value for
value, to those of the earlier run with the pre-review reform (482467511a),
so the fixes in 51d64d4904 change nothing in this population.

The environment followed `uv.lock`, so supporting packages (numpy, pandas and
others) differ from the certified run's `uv-pip-freeze.txt`; policyengine
6.2.5, policyengine-core 3.32.10 and policyengine-us 2.2.1 are the same.

Runs from later commits record `variant_source_sha256` in each worker receipt
and in `run_metadata.json`, and the runner will not reuse a worker whose
reform source differs.
