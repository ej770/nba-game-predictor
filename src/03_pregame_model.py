"""Step 3 - Pre-game winner model, graded against simple baselines and the betting market.

* Model choice: candidates are fit on 2007-08 .. 2019-20 and compared on 2020-21 and 2021-22.
* Walk-forward predictions: every season from 2010-11 on is predicted by a model trained only
  on earlier seasons, the way it would run for real. The test seasons 2022-23 .. 2025-26
  play no part in choosing or fitting the model that predicts them.
* The 99% trap: the same kind of model fed the final box score (shooting, rebounds,
  turnovers) looks brilliant, but those numbers only exist after the final buzzer.

Outputs (outputs/tables/): pregame_validation.csv, pregame_models.csv, pregame_by_season.csv,
pregame_confidence.csv, pregame_calibration.csv, leakage_demo.csv
and data/processed/pregame_predictions.csv.gz
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config as C

FEATURES = ["elo_diff", "rest_days_home", "rest_days_away", "b2b_home", "b2b_away",
            "season_diff_home", "season_diff_away", "last10_diff_home", "last10_diff_away",
            "games_played_home", "games_played_away", "league_home_rate"]


def candidates():
    return {
        "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)),
        "Gradient boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                                            l2_regularization=1.0,
                                                            random_state=C.RANDOM_STATE),
    }


def choose(val: pd.DataFrame, simple: str, margin: float = 0.002) -> str:
    """Keep the simpler model unless another one lowers validation log loss by more than
    `margin`. Near-ties then can't flip the choice between machines or library versions."""
    best = val.loc[val["log_loss"].idxmin()]
    simple_loss = val.loc[val["model"] == simple, "log_loss"].iloc[0]
    return best["model"] if best["log_loss"] < simple_loss - margin else simple


def scores(y, p) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    return {"games": len(y), "accuracy": accuracy_score(y, p > 0.5), "log_loss": log_loss(y, p, labels=[0, 1]),
            "brier": brier_score_loss(y, p), "auc": roc_auc_score(y, p)}


def main() -> None:
    df = pd.read_csv(C.PROCESSED / "features.csv.gz", parse_dates=["date"])
    df = df[df["season"] >= C.FIRST_MODEL_SEASON].reset_index(drop=True)
    y = df["home_win"].values
    train = df["season"].isin(C.TRAIN_SEASONS).values
    valid = df["season"].isin(C.VALID_SEASONS).values

    # ---- Model choice on the validation seasons ---------------------------------------------
    rows = []
    for name, m in candidates().items():
        m.fit(df.loc[train, FEATURES], y[train])
        rows.append({"model": name, **scores(y[valid], m.predict_proba(df.loc[valid, FEATURES])[:, 1])})
    val = pd.DataFrame(rows)
    val.round(4).to_csv(C.TABLES / "pregame_validation.csv", index=False)
    choice = choose(val, simple="Logistic regression")
    print(val.round(4).to_string(index=False), f"\nChosen: {choice}")

    # ---- Walk-forward predictions -------------------------------------------------------------
    preds = []
    for season in range(2010, C.LAST_SEASON + 1):
        fit_on = (df["season"] < season).values
        m = candidates()[choice].fit(df.loc[fit_on, FEATURES], y[fit_on])
        part = df[df["season"] == season]
        preds.append(part[["game_id"]].assign(model_prob_home=m.predict_proba(part[FEATURES])[:, 1]))
    wf = df.merge(pd.concat(preds), on="game_id")
    wf[["game_id", "season", "date", "home", "away", "home_pts", "away_pts", "home_win",
        "elo_home", "elo_away", "elo_prob_home", "vegas_prob_home", "vegas_spread_home",
        "model_prob_home"]].to_csv(C.PROCESSED / "pregame_predictions.csv.gz", index=False)

    # ---- Test seasons: model vs. baselines vs. the betting market --------------------------
    t = wf[wf["season"].isin(C.TEST_SEASONS)]
    lined = t.dropna(subset=["vegas_prob_home"])
    table = pd.DataFrame([
        {"model": "Our pre-game model", "games": "all", **scores(t["home_win"], t["model_prob_home"])},
        {"model": "Elo rating alone", "games": "all", **scores(t["home_win"], t["elo_prob_home"])},
        # constant 0.5 + tiny edge = "home team wins"; its log loss is that of a coin flip
        {"model": "Always pick the home team", "games": "all", **scores(t["home_win"], np.full(len(t), 0.501))},
        {"model": "Our pre-game model", "games": "with betting lines", **scores(lined["home_win"], lined["model_prob_home"])},
        {"model": "Betting market favourite (closing moneyline)", "games": "with betting lines",
         **scores(lined["home_win"], lined["vegas_prob_home"])},
    ])
    table.round(4).to_csv(C.TABLES / "pregame_models.csv", index=False)
    print(table.round(3).to_string(index=False))
    agree = (lined["model_prob_home"] > 0.5) == (lined["vegas_prob_home"] > 0.5)
    print(f"Same pick as the betting market in {agree.mean():.1%} of test games with lines")

    # ---- Confidence and calibration on the test seasons -----------------------------------
    conf = np.maximum(t["model_prob_home"], 1 - t["model_prob_home"])
    right = (t["model_prob_home"] > 0.5) == (t["home_win"] == 1)
    cov = pd.DataFrame([{"min_confidence": c, "share_of_games": (conf >= c).mean(),
                         "accuracy": right[conf >= c].mean(), "games": int((conf >= c).sum())}
                        for c in np.round(np.arange(0.50, 0.91, 0.05), 2)])
    cov.round(4).to_csv(C.TABLES / "pregame_confidence.csv", index=False)
    print(cov.round(3).to_string(index=False))
    bins = pd.cut(t["model_prob_home"], np.linspace(0, 1, 11))
    cal = (t.groupby(bins, observed=True)
             .agg(games=("home_win", "size"), predicted=("model_prob_home", "mean"), actual=("home_win", "mean"))
             .reset_index(drop=True))
    cal.round(4).to_csv(C.TABLES / "pregame_calibration.csv", index=False)

    # ---- Season by season ---------------------------------------------------------------------
    rows = []
    for season, g in wf.groupby("season"):
        l = g.dropna(subset=["vegas_prob_home"])
        rows.append({
            "season": season, "season_label": C.season_label(season), "games": len(g),
            "model_accuracy": accuracy_score(g["home_win"], g["model_prob_home"] > 0.5),
            "elo_accuracy": accuracy_score(g["home_win"], g["elo_prob_home"] > 0.5),
            "home_team_accuracy": g["home_win"].mean(),
            "games_with_lines": len(l),
            "vegas_accuracy": accuracy_score(l["home_win"], l["vegas_prob_home"] > 0.5),
            "model_accuracy_on_lined_games": accuracy_score(l["home_win"], l["model_prob_home"] > 0.5),
        })
    by_season = pd.DataFrame(rows)
    by_season["split"] = np.where(by_season["season"].isin(C.TEST_SEASONS), "test", "earlier")
    by_season.round(4).to_csv(C.TABLES / "pregame_by_season.csv", index=False)
    print(by_season.round(3).to_string(index=False))

    # ---- The 99% trap: a "model" that reads the final box score ------------------------------
    box = pd.read_csv(C.PROCESSED / "box.csv.gz")
    wide = box.pivot(index="game_id", columns="side")
    wide.columns = [f"{c}_{s}" for c, s in wide.columns]
    stats = pd.DataFrame(index=wide.index)
    for s in ("h", "v"):
        stats[f"fg_pct_{s}"] = wide[f"fgm_{s}"] / wide[f"fga_{s}"]
        for c in ("fg3m", "ftm", "reb", "tov"):
            stats[f"{c}_{s}"] = wide[f"{c}_{s}"]
    leak = df[["game_id", "season", "home_win", "home_pts", "away_pts"]].merge(stats, left_on="game_id", right_index=True)
    fit_on = leak["season"] < min(C.TEST_SEASONS)
    test_on = leak["season"].isin(C.TEST_SEASONS)
    rows = [{"model": "Pre-game model (honest)", "test_accuracy": accuracy_score(t["home_win"], t["model_prob_home"] > 0.5),
             "known_before_tipoff": True}]
    for label, cols in [("Final box score: shooting, rebounds, turnovers", list(stats.columns)),
                        ("Final score", ["home_pts", "away_pts"])]:
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(leak.loc[fit_on, cols], leak.loc[fit_on, "home_win"])
        rows.append({"model": label, "test_accuracy": accuracy_score(leak.loc[test_on, "home_win"], m.predict(leak.loc[test_on, cols])),
                     "known_before_tipoff": False})
    leak_tbl = pd.DataFrame(rows)
    leak_tbl.round(4).to_csv(C.TABLES / "leakage_demo.csv", index=False)
    print(leak_tbl.round(3).to_string(index=False))

    # The model to use next season: same recipe, fit on every season so far
    deployed = candidates()[choice].fit(df[FEATURES], y)
    ours, vegas = table.iloc[0], table.iloc[4]
    return {"model": deployed, "name": choice, "input_example": df[FEATURES].tail(1000),
            "metrics": {"test_accuracy": ours["accuracy"], "test_log_loss": ours["log_loss"],
                        "test_brier": ours["brier"], "test_auc": ours["auc"],
                        "test_accuracy_same_games_as_market": table.iloc[3]["accuracy"],
                        "market_accuracy": vegas["accuracy"]}}


if __name__ == "__main__":
    main()
