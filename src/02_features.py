"""Step 2 - Pre-game features and betting lines for every game.

Everything here is known before tip-off:
* Elo ratings (FiveThirtyEight's NBA method: K=20, home court worth 100 Elo points,
  margin-of-victory multiplier, 25% reversion to the mean between seasons)
* rest days and back-to-backs
* season-to-date point differential and last-10-games form, shrunk toward zero early on
* the league-wide home win rate over the previous 365 days (home court has shrunk since 2000)
* the closing moneyline and spread, used only as a benchmark, never as a model input

Output: data/processed/features.csv.gz (one row per game)
"""
import sqlite3

import numpy as np
import pandas as pd

import config as C

# Franchise continuity for ratings: relocated teams keep their rating.
FRANCHISE = {"SEA": "OKC", "NJN": "BKN", "VAN": "MEM", "NOH": "NOP", "NOK": "NOP", "CHH": "NOP"}
EXPANSION = {("CHA", 2004)}            # Charlotte Bobcats started in 2004-05

ODDS_NAMES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "New Jersey Nets": "BKN",
    "Charlotte Bobcats": "CHA", "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU",
    "Indiana Pacers": "IND", "LA Clippers": "LAC", "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New Orleans Hornets": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Seattle SuperSonics": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

ELO_K, ELO_HOME, ELO_MEAN, ELO_CARRY = 20.0, 100.0, 1505.0, 0.75


def elo_ratings(games: pd.DataFrame) -> pd.DataFrame:
    """Pre-game Elo for both teams, updated game by game in date order."""
    rating, last_season = {}, {}
    pre_h, pre_a = np.empty(len(games)), np.empty(len(games))
    for i, g in enumerate(games.itertuples(index=False)):
        for team in (g.home_f, g.away_f):
            if team not in rating:
                rating[team] = 1300.0 if (team, g.season) in EXPANSION else 1500.0
            elif last_season[team] != g.season:          # new season: revert toward the mean
                rating[team] = ELO_CARRY * rating[team] + (1 - ELO_CARRY) * ELO_MEAN
            last_season[team] = g.season
        rh, ra = rating[g.home_f], rating[g.away_f]
        pre_h[i], pre_a[i] = rh, ra
        diff = rh + ELO_HOME - ra
        p_home = 1 / (1 + 10 ** (-diff / 400))
        margin = g.home_pts - g.away_pts
        winner_diff = diff if margin > 0 else -diff
        mult = (abs(margin) + 3) ** 0.8 / (7.5 + 0.006 * winner_diff)
        shift = ELO_K * mult * ((margin > 0) - p_home)
        rating[g.home_f] = rh + shift
        rating[g.away_f] = ra - shift
    return pd.DataFrame({"elo_home": pre_h, "elo_away": pre_a}, index=games.index)


def team_form(games: pd.DataFrame) -> pd.DataFrame:
    """Rest, season-to-date and last-10 point differential for each side, before the game."""
    long = pd.concat([
        pd.DataFrame({"game_id": games["game_id"], "date": games["date"], "season": games["season"],
                      "team": games["home_f"], "side": "home",
                      "diff": games["home_pts"] - games["away_pts"]}),
        pd.DataFrame({"game_id": games["game_id"], "date": games["date"], "season": games["season"],
                      "team": games["away_f"], "side": "away",
                      "diff": games["away_pts"] - games["home_pts"]}),
    ]).sort_values(["team", "date", "game_id"], kind="stable")
    grp = long.groupby(["team", "season"], sort=False)
    long["games_played"] = grp.cumcount()
    long["std_diff_sum"] = grp["diff"].cumsum() - long["diff"]
    # Shrink early-season averages toward 0 (as if the team had 5 average games already)
    long["season_diff"] = long["std_diff_sum"] / (long["games_played"] + 5)
    long["last10_diff"] = grp["diff"].transform(lambda s: s.shift().rolling(10, min_periods=1).mean()).fillna(0)
    prev_date = long.groupby("team", sort=False)["date"].shift()
    long["rest_days"] = (long["date"] - prev_date).dt.days.clip(upper=5).fillna(5)
    long["b2b"] = (long["rest_days"] == 1).astype(int)
    cols = ["games_played", "season_diff", "last10_diff", "rest_days", "b2b"]
    wide = long.pivot(index="game_id", columns="side", values=cols)
    wide.columns = [f"{c}_{s}" for c, s in wide.columns]
    return wide


def league_home_rate(games: pd.DataFrame) -> pd.Series:
    """Share of home wins in the 365 days before each game day (excludes that day)."""
    daily = games.groupby("date")["home_win"].agg(["sum", "count"])
    roll = daily.rolling("365D", closed="left").sum()
    rate = (roll["sum"] / roll["count"]).reindex(games["date"]).values
    return pd.Series(rate, index=games.index).fillna(0.6)


def ml_to_prob(ml: pd.Series) -> pd.Series:
    """American moneyline -> implied probability ('NL' = no line -> NaN)."""
    ml = pd.to_numeric(ml, errors="coerce")
    return pd.Series(np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100)), index=ml.index)


def load_odds() -> pd.DataFrame:
    con = sqlite3.connect(C.RAW / "OddsData.sqlite")
    tables = pd.read_sql("select name from sqlite_master where type='table'", con)["name"]
    frames = []
    for season in range(C.FIRST_MODEL_SEASON, C.LAST_SEASON + 1):
        label = C.season_label(season)
        for name in (f"odds_{label}_new", label, f"odds_{label}"):
            if name in set(tables):
                d = pd.read_sql(f'select * from "{name}"', con)
                d["season"] = season
                frames.append(d)
                break
    odds = pd.concat(frames, ignore_index=True)
    odds["date"] = pd.to_datetime(odds["Date"])
    odds["home_f"] = odds["Home"].map(ODDS_NAMES)
    odds["away_f"] = odds["Away"].map(ODDS_NAMES)
    assert odds[["home_f", "away_f"]].notna().all().all(), set(odds["Home"]) - set(ODDS_NAMES)
    ph, pa = ml_to_prob(odds["ML_Home"]), ml_to_prob(odds["ML_Away"])
    odds["vegas_prob_home"] = ph / (ph + pa)                   # remove the bookmaker's margin
    odds["vegas_spread_home"] = pd.to_numeric(odds["Spread"], errors="coerce")   # expected home margin
    malformed = (pd.to_numeric(odds["ML_Home"], errors="coerce").abs() < 100) | \
                (pd.to_numeric(odds["ML_Away"], errors="coerce").abs() < 100)
    odds.loc[malformed, "vegas_prob_home"] = np.nan
    odds["odds_margin"] = odds["Win_Margin"]
    odds["odds_points"] = odds["Points"]
    return odds[["date", "home_f", "away_f", "vegas_prob_home", "vegas_spread_home",
                 "odds_margin", "odds_points"]]


def main() -> None:
    games = pd.read_csv(C.PROCESSED / "games.csv.gz", parse_dates=["date"])
    games["home_f"] = games["home"].replace(FRANCHISE)
    games["away_f"] = games["away"].replace(FRANCHISE)
    games = games.sort_values(["date", "game_id"], kind="stable").reset_index(drop=True)

    games = games.join(elo_ratings(games))
    games["elo_diff"] = games["elo_home"] - games["elo_away"]
    games["elo_prob_home"] = 1 / (1 + 10 ** (-(games["elo_diff"] + ELO_HOME) / 400))
    games = games.merge(team_form(games), left_on="game_id", right_index=True, how="left")
    games["league_home_rate"] = league_home_rate(games)

    # Betting lines: match on date and teams (allow the listing to be one day off)
    odds = load_odds()
    merged = games.merge(odds, on=["date", "home_f", "away_f"], how="left")
    miss = merged["vegas_prob_home"].isna() & (merged["season"] >= C.FIRST_MODEL_SEASON)
    for shift in (-1, 1):
        alt = odds.assign(date=odds["date"] + pd.Timedelta(days=shift))
        fill = games[miss.values].merge(alt, on=["date", "home_f", "away_f"], how="left")
        for col in ["vegas_prob_home", "vegas_spread_home", "odds_margin", "odds_points"]:
            merged.loc[miss.values, col] = merged.loc[miss.values, col].fillna(pd.Series(fill[col].values, index=merged.index[miss.values]))
        miss = merged["vegas_prob_home"].isna() & (merged["season"] >= C.FIRST_MODEL_SEASON)
    merged = merged.drop_duplicates("game_id")

    # Cross-check our final scores against the odds archive's results
    chk = merged.dropna(subset=["odds_margin"])
    agree = ((chk["home_pts"] - chk["away_pts"]) == chk["odds_margin"]).mean()
    model_games = merged[merged["season"] >= C.FIRST_MODEL_SEASON]
    print(f"Betting lines matched for {model_games['vegas_prob_home'].notna().mean():.1%} of games since 2007-08; "
          f"final margins agree with the odds archive in {agree:.2%} of matched games")

    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    merged.drop(columns=["odds_margin", "odds_points"]).to_csv(C.PROCESSED / "features.csv.gz", index=False)
    print(merged.groupby("season")[["vegas_prob_home"]].count().T.to_string())


if __name__ == "__main__":
    main()
