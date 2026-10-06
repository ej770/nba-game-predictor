"""Step 1 - Turn NBA play-by-play into game results, scoring timelines and box scores.

Input  : data/raw/nbastatsv3_<season>.tar.xz (play-by-play) and shotdetail_<season>.tar.xz
         (game dates, home/away teams) from github.com/shufinskiy/nba_data
Output : data/processed/games.csv.gz      one row per regular-season game
         data/processed/scoring.csv.gz    every scoring play: game, second of play, score
         data/processed/box.csv.gz        full-game team box score (used only for the
                                          leakage demonstration in step 3)
"""
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config as C

PBP_COLS = ["gameId", "actionNumber", "clock", "period", "teamTricode", "location",
            "scoreHome", "scoreAway", "actionType", "subType", "isFieldGoal", "shotResult",
            "description"]


def read_tar_csv(path, usecols=None):
    with tarfile.open(path, "r:xz") as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith(".csv"))
        return pd.read_csv(tar.extractfile(member), usecols=usecols, low_memory=False)


def clock_seconds(clock: pd.Series) -> pd.Series:
    """'PT11M36.00S' -> seconds left in the period."""
    parts = clock.str.extract(r"PT(\d+)M([\d.]+)S").astype(float)
    return parts[0] * 60 + parts[1]


def elapsed_seconds(period: pd.Series, left: pd.Series) -> pd.Series:
    """Seconds of game time played so far (4 x 12-minute quarters, then 5-minute overtimes)."""
    regulation = (period.clip(upper=4) - 1) * 720 + np.where(period <= 4, 720 - left, 720)
    overtime = np.where(period > 4, (period - 5) * 300 + (300 - left), 0)
    return regulation + overtime


def parse_season(season: int):
    pbp = read_tar_csv(C.RAW / f"nbastatsv3_{season}.tar.xz", usecols=PBP_COLS)
    shots = read_tar_csv(C.RAW / f"shotdetail_{season}.tar.xz",
                         usecols=["GAME_ID", "GAME_DATE", "HTM", "VTM"])
    pbp = pbp[pbp["gameId"].astype(str).str.startswith("2")]          # regular season only
    pbp = pbp.sort_values(["gameId", "period", "actionNumber"], kind="stable")
    pbp["sec"] = elapsed_seconds(pbp["period"], clock_seconds(pbp["clock"]))

    # Scoring timeline: rows where the score changed
    sc = pbp.dropna(subset=["scoreHome", "scoreAway"])[["gameId", "sec", "period", "scoreHome", "scoreAway"]]
    sc = sc.astype({"scoreHome": int, "scoreAway": int})
    sc = sc[(sc[["scoreHome", "scoreAway"]].diff().abs().sum(axis=1) > 0)
            | (sc["gameId"] != sc["gameId"].shift())]
    sc = sc[(sc["scoreHome"] + sc["scoreAway"]) > 0]

    # Teams and final score
    side = (pbp.dropna(subset=["teamTricode", "location"])
               .groupby(["gameId", "location"])["teamTricode"].agg(lambda s: s.mode().iloc[0])
               .unstack())
    final = sc.groupby("gameId").agg(home_pts=("scoreHome", "last"), away_pts=("scoreAway", "last"),
                                     periods=("period", "max"))
    dates = shots.drop_duplicates("GAME_ID").set_index("GAME_ID")
    games = final.join(side.rename(columns={"h": "home", "v": "away"})).join(dates, how="left")
    games["season"] = season
    games = games.reset_index().rename(columns={"gameId": "game_id", "GAME_DATE": "date"})

    # Full-game box score per team (only for the leakage demo: it is known after the game)
    p = pbp[pbp["location"].isin(["h", "v"])]
    fg = p["isFieldGoal"] == 1
    made = p["shotResult"] == "Made"
    three = p["description"].fillna("").str.contains("3PT")
    box = pd.DataFrame({
        "game_id": p["gameId"], "side": p["location"],
        "fga": fg, "fgm": fg & made,
        "fg3a": fg & three, "fg3m": fg & made & three,
        "fta": p["actionType"] == "Free Throw",
        "ftm": (p["actionType"] == "Free Throw") & ~p["description"].fillna("").str.contains("MISS"),
        "reb": p["actionType"] == "Rebound",
        "tov": p["actionType"] == "Turnover",
        "fouls": p["actionType"] == "Foul",
    }).groupby(["game_id", "side"]).sum().reset_index()
    box["season"] = season
    sc = sc.rename(columns={"gameId": "game_id", "scoreHome": "home", "scoreAway": "away"})
    return games, sc[["game_id", "sec", "home", "away"]], box


def main() -> None:
    seasons = range(C.FIRST_SEASON, C.LAST_SEASON + 1)
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(parse_season, seasons))
    games = pd.concat([r[0] for r in results], ignore_index=True)
    scoring = pd.concat([r[1] for r in results], ignore_index=True)
    box = pd.concat([r[2] for r in results], ignore_index=True)

    # Basic integrity checks
    games["date"] = pd.to_datetime(games["date"].astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    bad = games[games[["home", "away", "date"]].isna().any(axis=1) | (games["home_pts"] == games["away_pts"])]
    if len(bad):
        print(f"Dropping {len(bad)} games with missing teams/dates or tied final scores")
    games = games.drop(bad.index)
    games["home_win"] = (games["home_pts"] > games["away_pts"]).astype(int)
    games = games.sort_values(["date", "game_id"]).reset_index(drop=True)

    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    games.to_csv(C.PROCESSED / "games.csv.gz", index=False)
    scoring[scoring["game_id"].isin(games["game_id"])].to_csv(C.PROCESSED / "scoring.csv.gz", index=False)
    box[box["game_id"].isin(games["game_id"])].to_csv(C.PROCESSED / "box.csv.gz", index=False)
    per_season = games.groupby("season").agg(games=("game_id", "size"), home_win=("home_win", "mean"))
    print(per_season.round(3).to_string())
    print(f"{len(games):,} games, {len(scoring):,} scoring plays")


if __name__ == "__main__":
    sys.exit(main())
