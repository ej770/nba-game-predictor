"""Step 6 - README figures (outputs/figures/*.png)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as C

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def pct_axis(ax, lo, hi):
    ax.set_ylim(lo, hi)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def title(ax, text, sub):
    ax.set_title(text, loc="left", fontsize=13, fontweight="bold", pad=24)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom")


def by_season():
    d = pd.read_csv(C.TABLES / "pregame_by_season.csv")
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = range(len(d))
    test = d.index[d["split"] == "test"]
    ax.axvspan(test.min() - 0.5, test.max() + 0.5, color="#f0efec", zorder=0)
    ax.text(test.min() - 0.35, 0.735, "Test seasons", color=INK2, fontsize=9)
    series = [("model_accuracy", "Our model", BLUE), ("vegas_accuracy", "Las Vegas favourite", ORANGE),
              ("elo_accuracy", "Elo alone", AQUA), ("home_team_accuracy", "Home team", YELLOW)]
    for col, label, color in series:
        ax.plot(x, d[col], color=color, linewidth=2, marker="o", markersize=4, label=label)
        ax.text(len(d) - 0.6, d[col].iloc[-1], f"{label} {d[col].iloc[-1]:.0%}", color=INK, fontsize=8.5, va="center")
    ax.set_xticks(list(x), d["season_label"], rotation=45, ha="right")
    ax.set_xlim(-0.5, len(d) + 2.6)
    pct_axis(ax, 0.5, 0.75)
    ax.legend(loc="lower left", frameon=False, ncol=4, fontsize=9)
    title(ax, "Share of games picked correctly, by season",
          "Each season predicted by a model trained only on earlier seasons. 2025-26 betting lines cover 553 games.")
    fig.tight_layout()
    fig.savefig(C.FIGURES / "accuracy_by_season.png", dpi=150)


def live():
    d = pd.read_csv(C.TABLES / "live_by_minute.csv")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.plot(d["minute"], d["accuracy"], color=BLUE, linewidth=2, label="Score, clock and pre-game view")
    ax.plot(d["minute"], d["accuracy_score_only"], color=ORANGE, linewidth=2, label="Score and clock only")
    for m in (12, 24, 36):
        ax.axvline(m, color=GRID, linewidth=1, zorder=0)
    cp = pd.read_csv(C.TABLES / "live_checkpoints.csv").set_index("moment")
    for label, minute in [("Tip-off", 0), ("Halftime", 24), ("End of 3rd quarter", 36)]:
        v = cp.loc[label, "accuracy"]
        ax.annotate(f"{label}: {v:.0%}", (minute, v), xytext=(4, 10), textcoords="offset points", fontsize=8.5)
    last = cp.loc["15 seconds left", "accuracy"]
    ax.annotate(f"15 s left: {last:.0%}", (47.75, last), xytext=(-70, -18), textcoords="offset points", fontsize=8.5)
    ax.set_xlim(0, 48)
    ax.set_xticks([0, 12, 24, 36, 48], ["Tip-off", "Q2", "Q3", "Q4", "End"])
    pct_axis(ax, 0.5, 1.0)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    title(ax, "Live win probability: how often the favoured side wins",
          "4,920 games from 2022-23 to 2025-26, checked every 15 seconds")
    fig.tight_layout()
    fig.savefig(C.FIGURES / "live_accuracy.png", dpi=150)


def confidence_and_leakage():
    d = pd.read_csv(C.TABLES / "pregame_confidence.csv")
    lk = pd.read_csv(C.TABLES / "leakage_demo.csv")
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.2, 1]})
    a.bar(range(len(d)), d["accuracy"], color=BLUE, width=0.7)
    for i, r in d.iterrows():
        a.text(i, r["accuracy"] + 0.01, f"{r['accuracy']:.0%}", ha="center", fontsize=8.5)
    a.set_xticks(range(len(d)), [f"{c:.0%}+\n{s:.0%}" for c, s in zip(d["min_confidence"], d["share_of_games"])],
                 fontsize=8.5)
    a.set_xlabel("Model is at least this sure (top) · share of games (bottom)")
    pct_axis(a, 0.5, 1.0)
    title(a, "Surer picks are right more often", "Pre-game model, test seasons")
    colors = [BLUE if k else "#b4b2aa" for k in lk["known_before_tipoff"]]
    names = ["Pre-game features\n(usable)", "Final box score\n(after the game)", "Final score\n(after the game)"]
    b.barh(range(len(lk)), lk["test_accuracy"], color=colors, height=0.6)
    for i, v in enumerate(lk["test_accuracy"]):
        b.text(v - 0.01, i, f"{v:.0%}", ha="right", va="center", color="white", fontsize=10, fontweight="bold")
    b.set_yticks(range(len(lk)), names)
    b.invert_yaxis()
    b.set_xlim(0.5, 1.0)
    b.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    b.grid(axis="x", color=GRID, linewidth=0.8)
    b.set_axisbelow(True)
    title(b, "The 99% trap", "Same model type, fed data from after the game")
    fig.tight_layout()
    fig.savefig(C.FIGURES / "confidence_and_leakage.png", dpi=150)


def main() -> None:
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    by_season()
    live()
    confidence_and_leakage()
    print("Figures ->", C.FIGURES)


if __name__ == "__main__":
    main()
