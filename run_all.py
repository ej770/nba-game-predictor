"""Run the full pipeline end to end: python run_all.py  (about 10 minutes)."""
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
STEPS = ["00_download.py", "01_parse_pbp.py", "02_features.py", "03_pregame_model.py",
         "04_live_model.py", "05_export.py", "06_figures.py"]

for step in STEPS:
    start = time.time()
    print(f"\n>>> {step}", flush=True)
    subprocess.run([sys.executable, step], cwd=SRC, check=True)
    print(f"<<< {step} finished in {time.time() - start:.0f}s", flush=True)
