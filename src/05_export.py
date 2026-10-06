"""Step 5 - Report-ready tables for the Fabric Lakehouse and Power BI.

Output: fabric/tables/*.csv
  games.csv              one row per game since 2010-11: teams, score, the three pre-game
                         probabilities (our model, Elo, betting market) and whether each pick was right
  teams.csv              team names, conference and Elo rating going into 2026-27
  live_win_probability.csv  home win probability every 15 seconds for the 4,920 test games
  model_scorecard.csv, season_accuracy.csv, confidence.csv, live_checkpoints.csv,
  live_by_minute.csv, leakage_demo.csv   summary tables behind the report's charts
"""
import numpy as np
import pandas as pd

import config as C

TEAMS = {
    "ATL": ("Atlanta Hawks", "East"), "BOS": ("Boston Celtics", "East"), "BKN": ("Brooklyn Nets", "East"),
    "NJN": ("New Jersey Nets", "East"), "CHA": ("Charlotte Hornets", "East"), "CHI": ("Chicago Bulls", "East"),
    "CLE": ("Cleveland Cavaliers", "East"), "DAL": ("Dallas Mavericks", "West"), "DEN": ("Denver Nuggets", "West"),
    "DET": ("Detroit Pistons", "East"), "GSW": ("Golden State Warriors", "West"), "HOU": ("Houston Rockets", "West"),
    "IND": ("Indiana Pacers", "East"), "LAC": ("LA Clippers", "West"), "LAL": ("Los Angeles Lakers", "West"),
    "MEM": ("Memphis Grizzlies", "West"), "MIA": ("Miami Heat", "East"), "MIL": ("Milwaukee Bucks", "East"),
    "MIN": ("Minnesota Timberwolves", "West"), "NOP": ("New Orleans Pelicans", "West"),
    "NOH": ("New Orleans Hornets", "West"), "NYK": ("New York Knicks", "East"),
    "OKC": ("Oklahoma City Thunder", "West"), "ORL": ("Orlando Magic", "East"),
    "PHI": ("Philadelphia 76ers", "East"), "PHX": ("Phoenix Suns", "West"),
    "POR": ("Portland Trail Blazers", "West"), "SAC": ("Sacramento Kings", "West"),
    "SAS": ("San Antonio Spurs", "West"), "TOR": ("Toronto Raptors", "East"), "UTA": ("Utah Jazz", "West"),
    "WAS": ("Washington Wizards", "East"),
}
REPORT_FRANCHISE = {"NJN": "BKN", "NOH": "NOP"}


def clock_label(t: pd.Series, is_ot: pd.Series) -> pd.Series:
    period = np.where(is_ot == 1, 5 + (t - 2880) // 300, t // 720 + 1).astype(int)
    left = np.where(is_ot == 1, 300 - (t - 2880) % 300, 720 - t % 720).astype(int)
    name = [f"Q{p}" if p <= 4 else f"OT{p - 4}" for p in period]
    return pd.Series(name, index=t.index), pd.Series(period, index=t.index), \
        pd.Series([f"{s // 60}:{s % 60:02d}" for s in left], index=t.index)


def main() -> None:
    out = C.FABRIC / "tables"
    out.mkdir(parents=True, exist_ok=True)

    g = pd.read_csv(C.PROCESSED / "pregame_predictions.csv.gz", parse_dates=["date"])
    g["season_label"] = g["season"].map(C.season_label)
    g["split"] = np.where(g["season"].isin(C.TEST_SEASONS), "Test seasons", "Earlier seasons")
    g["winner"] = np.where(g["home_win"] == 1, g["home"], g["away"])
    for src in ("model", "elo", "vegas"):
        p = g[f"{src}_prob_home"]
        g[f"{src}_pick"] = np.where(p.isna(), None, np.where(p > 0.5, g["home"], g["away"]))
        g[f"{src}_correct"] = np.where(p.isna(), np.nan, ((p > 0.5).astype(int) == g["home_win"]).astype(float))
    g["model_confidence"] = np.maximum(g["model_prob_home"], 1 - g["model_prob_home"]).round(4)
    g["upset"] = ((g["model_prob_home"] > 0.5).astype(int) != g["home_win"]).astype(int)
    g["final_score"] = g["away"] + " " + g["away_pts"].astype(str) + " @ " + g["home"] + " " + g["home_pts"].astype(str)
    g["game_label"] = g["date"].dt.strftime("%Y-%m-%d") + "  " + g["away"] + " @ " + g["home"]
    cols = ["game_id", "season", "season_label", "split", "date", "game_label", "home", "away", "home_pts", "away_pts",
            "final_score", "home_win", "winner", "model_prob_home", "model_pick", "model_confidence",
            "model_correct", "elo_prob_home", "elo_pick", "elo_correct", "vegas_prob_home",
            "vegas_spread_home", "vegas_pick", "vegas_correct", "upset"]
    g = g[cols].rename(columns={"date": "game_date"})
    for c in ("model_prob_home", "elo_prob_home", "vegas_prob_home"):
        g[c] = g[c].round(4)
    g.to_csv(out / "games.csv", index=False)

    # Teams with the rating they carry into 2026-27 (end-of-season Elo, 25% back to the mean)
    feats = pd.read_csv(C.PROCESSED / "features.csv.gz", parse_dates=["date"])
    last = feats[feats["season"] == C.LAST_SEASON].sort_values("date")
    long = pd.concat([last[["date", "home_f", "elo_home"]].set_axis(["date", "team", "elo"], axis=1),
                      last[["date", "away_f", "elo_away"]].set_axis(["date", "team", "elo"], axis=1)])
    end_elo = long.sort_values("date").groupby("team")["elo"].last()
    teams = pd.DataFrame([{"team": k, "team_name": v[0], "conference": v[1],
                           "franchise": REPORT_FRANCHISE.get(k, k)} for k, v in TEAMS.items()])
    teams["elo_end_2025_26"] = teams["franchise"].map(end_elo).round(1)
    teams["elo_start_2026_27"] = (0.75 * teams["elo_end_2025_26"] + 0.25 * 1505).round(1)
    teams.loc[teams["team"] != teams["franchise"], ["elo_end_2025_26", "elo_start_2026_27"]] = np.nan
    teams.to_csv(out / "teams.csv", index=False)

    live = pd.read_csv(C.PROCESSED / "live_wp.csv.gz")
    period_name, period, clock = clock_label(live["t"], live["is_ot"])
    live = pd.DataFrame({
        "game_id": live["game_id"], "seconds_played": live["t"].astype(int),
        "minutes_played": (live["t"] / 60).round(2), "period": period, "period_name": period_name,
        "clock": clock, "home_score": live["home"].astype(int), "away_score": live["away"].astype(int),
        "home_lead": live["margin"].astype(int), "home_win_prob": live["wp"],
    })
    live.to_csv(out / "live_win_probability.csv", index=False)

    T = lambda n: pd.read_csv(C.TABLES / f"{n}.csv")
    T("pregame_models").to_csv(out / "model_scorecard.csv", index=False)
    T("pregame_by_season").to_csv(out / "season_accuracy.csv", index=False)
    T("pregame_confidence").to_csv(out / "confidence.csv", index=False)
    T("live_checkpoints").to_csv(out / "live_checkpoints.csv", index=False)
    T("live_by_minute").to_csv(out / "live_by_minute.csv", index=False)
    T("leakage_demo").to_csv(out / "leakage_demo.csv", index=False)
    for f in sorted(out.glob("*.csv")):
        print(f"{f.name:28s} {sum(1 for _ in open(f)) - 1:>9,} rows  {f.stat().st_size / 1e6:6.2f} MB")


if __name__ == "__main__":
    main()
