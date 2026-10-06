"""Step 4 - Live win probability: who wins, given the score, the clock and the pre-game odds?

Every game is sampled every 15 seconds of game time. Each moment's features are the home
team's lead, the time left and the pre-game model's probability (whose weight fades as the
game goes on). Fit on 2010-11 .. 2021-22, reported on 2022-23 .. 2025-26.

Outputs (outputs/tables/): live_validation.csv, live_by_minute.csv, live_checkpoints.csv
and data/processed/live_wp.csv.gz (win probability every 15 seconds for the test seasons)
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config as C

STEP = 15                    # seconds between snapshots
REGULATION = 48 * 60
FIT_SEASONS = range(2010, 2020)        # fit candidates ...
CHOOSE_SEASONS = range(2020, 2022)     # ... and choose on these, then refit on both
CHECKPOINTS = [("Tip-off", 0), ("End of 1st quarter", 720), ("Halftime", 1440),
               ("End of 3rd quarter", 2160), ("5 minutes left", 2580), ("2 minutes left", 2760),
               ("1 minute left", 2820), ("30 seconds left", 2850), ("15 seconds left", 2865)]


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def snapshots(games: pd.DataFrame, scoring: pd.DataFrame) -> pd.DataFrame:
    """One row per game every STEP seconds: lead, time left, pre-game probability."""
    end = REGULATION + 300 * (games["periods"].clip(lower=4) - 4)
    n = (end // STEP).astype(int)
    grid = pd.DataFrame({"game_id": np.repeat(games["game_id"].values, n),
                         "t": np.concatenate([np.arange(k) * STEP for k in n]).astype(float)})
    grid = grid.merge(games[["game_id", "season", "home_win", "model_prob_home"]], on="game_id")
    sc = scoring.sort_values("sec")
    grid = pd.merge_asof(grid.sort_values("t"), sc.rename(columns={"sec": "t"}), on="t", by="game_id",
                         direction="backward")
    grid[["home", "away"]] = grid[["home", "away"]].fillna(0)
    grid["margin"] = grid["home"] - grid["away"]
    ot = grid["t"] >= REGULATION
    grid["remaining"] = np.where(ot, 300 - (grid["t"] - REGULATION) % 300, REGULATION - grid["t"])
    grid["is_ot"] = ot.astype(int)
    grid["prior_logit"] = logit(grid["model_prob_home"])
    return grid.sort_values(["game_id", "t"]).reset_index(drop=True)


def design(d: pd.DataFrame) -> pd.DataFrame:
    """Features for the logistic model: the lead measured against the time left, and the
    pre-game view, which counts for less as the game goes on."""
    rem_min = d["remaining"] / 60
    frac = np.where(d["is_ot"] == 1, 0.0, d["remaining"] / REGULATION)
    return pd.DataFrame({
        "lead_vs_time": d["margin"] / np.sqrt(rem_min + 0.5),
        "lead": d["margin"],
        "prior_x_time": d["prior_logit"] * np.sqrt(frac),
        "prior": d["prior_logit"],
        "is_ot": d["is_ot"],
    })


def live_candidates():
    return {
        "Logistic regression (engineered)": ("design", make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))),
        "Gradient boosting (monotone)": ("raw", HistGradientBoostingClassifier(
            max_depth=6, learning_rate=0.1, max_iter=300, monotonic_cst=[1, 0, 1, 0],
            random_state=C.RANDOM_STATE)),
    }


def live_features(kind, d):
    return design(d) if kind == "design" else d[["margin", "remaining", "prior_logit", "is_ot"]]


def main() -> None:
    games = pd.read_csv(C.PROCESSED / "pregame_predictions.csv.gz")
    games = games.merge(pd.read_csv(C.PROCESSED / "games.csv.gz", usecols=["game_id", "periods"]), on="game_id")
    scoring = pd.read_csv(C.PROCESSED / "scoring.csv.gz")
    scoring = scoring[scoring["game_id"].isin(games["game_id"])]
    snap = snapshots(games, scoring)
    print(f"{len(snap):,} snapshots from {snap['game_id'].nunique():,} games")
    y = snap["home_win"].values

    fit = snap["season"].isin(FIT_SEASONS).values
    choose = snap["season"].isin(CHOOSE_SEASONS).values
    test = snap["season"].isin(C.TEST_SEASONS).values

    rows = []
    for name, (kind, m) in live_candidates().items():
        m.fit(live_features(kind, snap[fit]), y[fit])
        p = m.predict_proba(live_features(kind, snap[choose]))[:, 1]
        rows.append({"model": name, "log_loss": log_loss(y[choose], p), "brier": brier_score_loss(y[choose], p),
                     "accuracy": accuracy_score(y[choose], p > 0.5)})
    val = pd.DataFrame(rows)
    val.round(4).to_csv(C.TABLES / "live_validation.csv", index=False)
    best = val.loc[val["log_loss"].idxmin()]
    simple = "Logistic regression (engineered)"
    simple_loss = val.loc[val["model"] == simple, "log_loss"].iloc[0]
    choice = best["model"] if best["log_loss"] < simple_loss - 0.002 else simple   # keep it simple on near-ties
    print(val.round(4).to_string(index=False), f"\nChosen: {choice}")

    kind, model = live_candidates()[choice]
    model.fit(live_features(kind, snap[fit | choose]), y[fit | choose])
    t = snap[test].copy()
    t["wp"] = model.predict_proba(live_features(kind, t))[:, 1]
    # Baseline without the pre-game view: the score and clock alone
    base = live_candidates()["Logistic regression (engineered)"][1]
    cols = ["lead_vs_time", "lead", "is_ot"]
    base.fit(design(snap[fit | choose])[cols], y[fit | choose])
    t["wp_score_only"] = base.predict_proba(design(t)[cols])[:, 1]

    reg = t[t["is_ot"] == 0].copy()
    reg["minute"] = (reg["t"] // 60).astype(int)          # minutes played so far, 0..47
    by_min = pd.DataFrame([{
        "minute": minute, "minutes_left": 48 - minute, "snapshots": len(g),
        "accuracy": accuracy_score(g["home_win"], g["wp"] > 0.5),
        "accuracy_score_only": accuracy_score(g["home_win"], g["wp_score_only"] > 0.5),
        "brier": brier_score_loss(g["home_win"], g["wp"]),
    } for minute, g in reg.groupby("minute")])
    by_min.round(4).to_csv(C.TABLES / "live_by_minute.csv", index=False)

    cps = []
    for label, sec in CHECKPOINTS:
        g = reg[reg["t"] == sec]
        cps.append({"moment": label, "seconds_played": sec, "games": len(g),
                    "accuracy": accuracy_score(g["home_win"], g["wp"] > 0.5),
                    "accuracy_score_only": accuracy_score(g["home_win"], g["wp_score_only"] > 0.5),
                    "log_loss": log_loss(g["home_win"], g["wp"], labels=[0, 1])})
    cps = pd.DataFrame(cps)
    cps.round(4).to_csv(C.TABLES / "live_checkpoints.csv", index=False)
    print(cps.round(3).to_string(index=False))

    out = t[["game_id", "t", "remaining", "is_ot", "home", "away", "margin", "wp"]]
    out.assign(wp=out["wp"].round(4)).to_csv(C.PROCESSED / "live_wp.csv.gz", index=False)
    print(f"Saved {len(out):,} live snapshots for {out['game_id'].nunique():,} test games")
    sample = t.sample(1000, random_state=C.RANDOM_STATE)
    return {"model": model, "name": choice, "input_example": live_features(kind, sample),
            "metrics": {f"accuracy_{r.moment.lower().replace(' ', '_')}": r.accuracy for r in cps.itertuples()}}


if __name__ == "__main__":
    main()
