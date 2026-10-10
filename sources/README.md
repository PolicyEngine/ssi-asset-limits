# Sources

| File | Source | Retrieved |
| --- | --- | --- |
| `BCassidy_20260807.pdf` | SSA Office of the Chief Actuary, letter to Sen. Cassidy, August 7, 2026, https://www.ssa.gov/oact/solvency/BCassidy_20260807.pdf | 2026-10-09 |
| `BrownCassidy_20240129.pdf` | SSA Office of the Chief Actuary, letter to Sens. Brown and Cassidy on S. 2767, January 29, 2024, https://www.ssa.gov/OACT/solvency/BrownCassidy_20240129.pdf | 2026-10-09 |
| `BCassidy_20260807.txt`, `BrownCassidy_20240129.txt` | `pdftotext -layout` output of the two letters above (poppler); `tests/test_comparators.py` checks every OACT figure in `comparators.py` against these and that they regenerate from the PDFs | 2026-10-10 |
| `ssa_ssi_monthly_2024-12_table01.txt` | SSA, SSI Monthly Statistics, December 2024, Table 1, https://www.ssa.gov/policy/docs/statcomps/ssi_monthly/2024-12/table01.html (figures transcribed) | 2026-10-09 |
| `cbpp_2023_table1.csv` | Romig, Nuñez and Sherman, "The Case for Updating SSI Asset Limits," CBPP, updated September 20, 2023, Table 1, https://www.cbpp.org/research/social-security/the-case-for-updating-ssi-asset-limits (figures transcribed; read via the Wayback Machine capture of 2026-09-11) | 2026-10-09 |

SHA-256 of the PDFs is in `SHA256SUMS`. SSA and OACT documents are US
government works.
