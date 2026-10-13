import sys
from pathlib import Path

from ssi_asset_limits.microcosm_run import run_worker

chunk, out = Path(sys.argv[1]), Path(sys.argv[2])
for scenario in ("baseline", "ten_twenty", "no_limit"):
    run_worker(chunk, scenario, out / scenario)
