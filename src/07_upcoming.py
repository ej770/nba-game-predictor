"""Step 7 - Picks for the 2026-27 season, refreshed every day.

Pulls the 2026-27 schedule and results from ESPN's public scoreboard, carries each team's Elo
rating forward from the end of 2025-26, and rebuilds the step 2 features one game at a time,
using only what is known before each tip-off. The registered pre-game model then scores
every game: games already played are graded, games still to come get a pick.

Output: fabric/tables/season_picks.csv (one row per 2026-27 regular-season game played so far
or scheduled in the next 14 days). In Fabric the NBA_Upcoming_Picks notebook runs this daily.
"""
import json
import urllib.request
from bisect import bisect_left
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config as C

SEASON = 2026                       # 2026-27
SEASON_START = date(2026, 10, 1)    # preseason games in October are skipped
OPENING_NIGHT = date(2026, 10, 20)
DAYS_AHEAD = 14                     # picks for the next two weeks (the first two before the season)
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={:%Y%m%d}"
ESPN_CODES = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}
TEAM_CODES = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC",
              "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC",
              "SAS", "TOR", "UTA", "WAS"}
PICK_FEATURES = ["elo_diff", "rest_days_home", "rest_days_away", "b2b_home", "b2b_away",
                 "season_diff_home", "season_diff_away", "last10_diff_home", "last10_diff_away",
                 "games_played_home", "games_played_away", "league_home_rate"]   # same as step 3
ELO_K, ELO_HOME = 20.0, 100.0                                                   # same as step 2


def fetch_day(day: date) -> list:
    req = urllib.request.Request(SCOREBOARD.format(day), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        events = json.load(r).get("events", [])
    rows = []
    for e in events:
        if e["season"]["type"] != 2:                  # regular season only
            continue
        comp = e["competitions"][0]
        side = {c["homeAway"]: c for c in comp["competitors"]}
        code = lambda c: ESPN_CODES.get(c["team"]["abbreviation"], c["team"]["abbreviation"])
        tip = datetime.fromisoformat(comp["date"].replace("Z", "+00:00"))
        status = comp["status"]["type"]
        final = bool(status["completed"])
        rows.append({"game_id": int(e["id"]), "tipoff_utc": tip,
                     "date": pd.Timestamp(tip.astimezone(ZoneInfo("America/New_York")).date()),
                     "home_f": code(side["home"]), "away_f": code(side["away"]), "final": final,
                     "status": "Final" if final else status["description"],
                     "home_pts": float(side["home"]["score"]) if final else np.nan,
                     "away_pts": float(side["away"]["score"]) if final else np.nan})
    return rows


def fetch_schedule(today: date) -> pd.DataFrame:
    last = max(today, OPENING_NIGHT) + timedelta(DAYS_AHEAD)
    days = [SEASON_START + timedelta(d) for d in range((last - SEASON_START).days + 1)]
    with ThreadPoolExecutor(8) as pool:
        rows = [r for day_rows in pool.map(fetch_day, days) for r in day_rows]
    sched = pd.DataFrame(rows).drop_duplicates("game_id")
    unknown = set(sched["home_f"]) | set(sched["away_f"])
    assert unknown <= TEAM_CODES, unknown - TEAM_CODES
    return sched.sort_values(["tipoff_utc", "game_id"], kind="stable").reset_index(drop=True)


def season_features(sched: pd.DataFrame, start_elo: dict, history: pd.DataFrame) -> pd.DataFrame:
    """Step 2's features for each game, from state built only on games finished before it.

    sched: date, home_f, away_f, final, home_pts, away_pts, in tip-off order.
    start_elo: each team's rating going into the season (after the summer reversion).
    history: date and home_win of earlier games, for the league-wide home win rate."""
    elo = dict(start_elo)
    diffs = defaultdict(list)                 # point differentials of finished games this season
    last_game = {}                            # date of each team's previous game on the schedule
    past = history.sort_values("date", kind="stable")
    days = [d.toordinal() for d in past["date"]]      # finished games, in date order
    wins = [0, *np.cumsum(past["home_win"]).tolist()]  # running count of home wins
    rows = []
    for g in sched.itertuples(index=False):
        row = {}
        for side, team in (("home", g.home_f), ("away", g.away_f)):
            d = diffs[team]
            row[f"games_played_{side}"] = float(len(d))
            row[f"season_diff_{side}"] = sum(d) / (len(d) + 5)
            row[f"last10_diff_{side}"] = float(np.mean(d[-10:])) if d else 0.0
            rest = min((g.date - last_game[team]).days, 5) if team in last_game else 5
            row[f"rest_days_{side}"], row[f"b2b_{side}"] = float(rest), float(rest == 1)
            last_game[team] = g.date
        row["elo_home"], row["elo_away"] = elo[g.home_f], elo[g.away_f]
        row["elo_diff"] = row["elo_home"] - row["elo_away"]
        row["elo_prob_home"] = 1 / (1 + 10 ** (-(row["elo_diff"] + ELO_HOME) / 400))
        lo, hi = bisect_left(days, g.date.toordinal() - 365), bisect_left(days, g.date.toordinal())
        row["league_home_rate"] = (wins[hi] - wins[lo]) / (hi - lo) if hi > lo else 0.6
        rows.append(row)
        if g.final:                           # update the state with the result
            margin = g.home_pts - g.away_pts
            diff = row["elo_diff"] + ELO_HOME
            p_home = row["elo_prob_home"]
            winner_diff = diff if margin > 0 else -diff
            shift = ELO_K * (abs(margin) + 3) ** 0.8 / (7.5 + 0.006 * winner_diff) * ((margin > 0) - p_home)
            elo[g.home_f] += shift
            elo[g.away_f] -= shift
            diffs[g.home_f].append(margin)
            diffs[g.away_f].append(-margin)
            days.append(g.date.toordinal())
            wins.append(wins[-1] + int(margin > 0))
    return pd.DataFrame(rows, index=sched.index)


def season_picks(sched: pd.DataFrame, games: pd.DataFrame, teams: pd.DataFrame, model) -> pd.DataFrame:
    """sched from fetch_schedule; games and teams are the report tables saved by step 5."""
    start = teams.dropna(subset=["elo_start_2026_27"]).set_index("franchise")["elo_start_2026_27"].to_dict()
    history = games.rename(columns={"game_date": "date"})[["date", "home_win"]].assign(
        date=lambda d: pd.to_datetime(d["date"]))
    out = sched.join(season_features(sched, start, history))
    out["model_prob_home"] = model.predict_proba(out[PICK_FEATURES])[:, 1].round(4)
    out["model_pick"] = np.where(out["model_prob_home"] > 0.5, out["home_f"], out["away_f"])
    out["model_confidence"] = np.maximum(out["model_prob_home"], 1 - out["model_prob_home"]).round(4)
    out["winner"] = np.where(~out["final"], None, np.where(out["home_pts"] > out["away_pts"], out["home_f"], out["away_f"]))
    out["model_correct"] = np.where(out["final"], (out["model_pick"] == out["winner"]).astype(float), np.nan)
    out["stage"] = np.where(out["final"], "Played", "Upcoming")
    out["elo_prob_home"] = out["elo_prob_home"].round(4)
    out["season_label"] = C.season_label(SEASON)
    out["game_label"] = out["date"].dt.strftime("%Y-%m-%d") + "  " + out["away_f"] + " @ " + out["home_f"]
    out["final_score"] = np.where(out["final"], out["away_f"] + " " + out["away_pts"].astype("Int64").astype(str)
                                  + " @ " + out["home_f"] + " " + out["home_pts"].astype("Int64").astype(str), None)
    out["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    cols = ["game_id", "season_label", "date", "tipoff_utc", "game_label", "home_f", "away_f", "stage", "status",
            "home_pts", "away_pts", "final_score", "winner", "model_prob_home", "model_pick",
            "model_confidence", "model_correct", "elo_prob_home", "elo_home", "elo_away", "updated_utc"]
    return out[cols].rename(columns={"date": "game_date", "home_f": "home", "away_f": "away"})


def main() -> None:
    import importlib
    tables = C.FABRIC / "tables"
    games, teams = pd.read_csv(tables / "games.csv"), pd.read_csv(tables / "teams.csv")
    model = importlib.import_module("03_pregame_model").main()["model"]   # refit locally
    picks = season_picks(fetch_schedule(date.today()), games, teams, model)
    picks.to_csv(tables / "season_picks.csv", index=False)
    print(f"{len(picks)} games, {int(picks['model_correct'].notna().sum())} graded")


if __name__ == "__main__":
    main()
