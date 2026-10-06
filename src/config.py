"""Shared paths and settings for the NBA Game Predictor project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"
FABRIC = ROOT / "fabric"

# Play-by-play source: https://github.com/shufinskiy/nba_data (stats.nba.com play-by-play v3
# and shot charts, one archive per season). Betting lines: OddsData.sqlite from
# https://github.com/kyleskom/NBA-Machine-Learning-Sports-Betting (Sportsbook Review archive).
# Both are pinned to a commit, and every file is checked against src/checksums.json.
PBP_URL = "https://raw.githubusercontent.com/shufinskiy/nba_data/e829d4678be1e075f99e5d41a1c5f97089be446b/datasets/{name}"
ODDS_URL = ("https://raw.githubusercontent.com/kyleskom/NBA-Machine-Learning-Sports-Betting/"
            "8e36b0b72ecc5082aa8976dff742cdf910b3aa36/Data/OddsData.sqlite")
CHECKSUMS = Path(__file__).resolve().parent / "checksums.json"

FIRST_SEASON = 1996          # 1996-97: Elo ratings need a few seasons to settle
LAST_SEASON = 2025           # 2025-26
FIRST_MODEL_SEASON = 2007    # 2007-08: first season with betting lines to compare against

# Time-based evaluation: fit on older seasons, choose settings on validation seasons, report
# on the most recent seasons, which the model never sees while it is being built.
TRAIN_SEASONS = range(2007, 2020)     # 2007-08 .. 2019-20
VALID_SEASONS = range(2020, 2022)     # 2020-21, 2021-22
TEST_SEASONS = range(2022, 2026)      # 2022-23 .. 2025-26

RANDOM_STATE = 42


def season_label(season: int) -> str:
    return f"{season}-{(season + 1) % 100:02d}"
