# Held-out checks against SSA administrative data

Written by `ssi-asset-limits-admin-checks <run> --out-dir results/admin-checks`
from the certified run (policyengine.py 6.2.5, policyengine-us 2.2.1,
Microcosm `populace_us_2024` build `populace-us-2024-spm-20260915`).
`run_fingerprint.json` records the SHA-256 of the run tables and household
chunks read; the publisher checks it against the run it publishes. The frame's claiming flags
are set so December 2024 recipients match SSA's counts for ages 18 to 64 and
65 and over (the child band is not reached); none of the comparisons below
is a target.

| File | What it compares | SSA source |
| --- | --- | --- |
| `recipients_by_fine_age.csv` | Current-law recipients by detailed age | Annual Statistical Supplement 2025, Table 7.E3 (shares of 7,423,856 federally administered recipients, December 2024) |
| `recipients_with_social_security.csv` | Share of recipients who also receive Social Security, by age | SSI Annual Statistical Report 2024, Table 9 |
| `recipients_by_marital_status.csv` | Recipients with no spouse, a spouse who also receives SSI, or a spouse who does not (compared with SSA's no spouse, eligible spouse and ineligible spouse; the model's last row counts every spouse without SSI, including any who would qualify but do not claim) | SSI Annual Statistical Report 2024, Table 12 |
| `resources_of_the_eligible.csv` | Own countable resources of people the engine would pay with no resource test, by age | (no SSA counterpart; see the SIPP table) |
| `new_recipient_decomposition.csv` | Each reform's new recipients split into the resource-excluded pool, the part the reform admits, and the take-up flag | (model accounting) |
| `new_recipients_by_reporting.csv` | Current recipients and each reform's new recipients by whether they report SSI in the CPS (a new recipient who reports SSI is kept off it under current law only by imputed savings) | (model accounting) |
| `new_recipients_by_marital_status.csv` | Each reform's new recipients by whether a spouse lives with them | (model accounting) |
| `children.csv` | Children meeting SSI's disability standard, disabled children with any savings or savings over $2,000, and current child recipients (records and weighted) | (model accounting) |
| `pool_definition_check.csv` | The pool definition reproduces the engine's own no-limit recipients exactly | (consistency check) |
| `sipp2023_liquid_assets_unmarried_income_eligible.csv` | SIPP 2023 (December 2022) liquid assets (bank + stock/mutual fund + bond) of unmarried, apparently income-eligible aged or disabled people, and SSI receipt, by asset band | Census SIPP 2023 public-use file |

The SIPP table uses the sample construction of
`tools/estimate_ssi_asset_gradient.py::prepare_sample` on PolicyEngine/microcosm
branch `ssi-584-take-up-asset-gradient` (commit 7cae3dd9b), applied to the
SHA-pinned `pu2023.csv`, with person weights `WPFINWGT`. It is unmarried
people only, so it is not directly comparable with the model's
`resources_of_the_eligible.csv`, which includes married people.
