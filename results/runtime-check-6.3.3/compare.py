import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

E = Path(sys.argv[1])
report = {}
for scenario in ("baseline", "ten_twenty", "no_limit"):
    for name in ("persons", "households", "persons_diagnostics"):
        a = pd.read_csv(E / "r625/out" / scenario / f"{name}.csv.gz")
        b = pd.read_csv(E / "r633/out" / scenario / f"{name}.csv.gz")
        same_shape = a.shape == b.shape and list(a.columns) == list(b.columns)
        diffs = {}
        if same_shape:
            for c in a.columns:
                x, y = a[c].to_numpy(), b[c].to_numpy()
                if x.dtype.kind in "fc" or y.dtype.kind in "fc":
                    eq = np.array_equal(
                        x.astype(float), y.astype(float), equal_nan=True
                    )
                else:
                    eq = bool((a[c] == b[c]).all())
                if not eq:
                    diffs[c] = (
                        float(
                            np.nanmax(
                                np.abs(x.astype(float) - y.astype(float))
                            )
                        )
                        if x.dtype.kind in "fcib"
                        else "non-numeric"
                    )
        report[f"{scenario}/{name}"] = {
            "rows": int(len(a)),
            "columns": int(a.shape[1]),
            "same_shape": same_shape,
            "differing_columns": diffs,
        }
print(json.dumps(report, indent=1))
p = {
    s: pd.read_csv(E / f"r{v}/out/{s}/persons.csv.gz")
    for v in ("625",)
    for s in ("baseline",)
}
print("ssi columns:", [c for c in p["baseline"].columns if "ssi" in c])
(E / "compare_report.json").write_text(json.dumps(report, indent=1))
