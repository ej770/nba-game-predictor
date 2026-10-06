## Semantic model: Direct Lake on NBA_Lakehouse, with relationships, measures and formats
import sempy.fabric as fabric
from sempy_labs import directlake
from sempy_labs.lakehouse import is_schema_enabled
from sempy_labs.tom import connect_semantic_model

LAKEHOUSE = "NBA_Lakehouse"
MODEL = "NBA Game Predictor"
REPORT = "NBA Game Predictor"
TABLES = ["games", "teams", "live_win_probability", "season_accuracy", "confidence",
          "live_checkpoints", "live_by_minute", "leakage_demo", "model_scorecard",
          "season_picks"]                       # saved daily by NBA_Upcoming_Picks

TEAM_ROWS = "FILTER(games, [Selected Team Filter] = 1)"
MEASURES = {
    ("games", "Games"): ("COUNTROWS(games)", "#,0"),
    ("games", "Model Accuracy"): ("AVERAGE(games[model_correct])", "0.0%"),
    ("games", "Model Accuracy With Lines"):
        ("CALCULATE(AVERAGE(games[model_correct]), NOT ISBLANK(games[vegas_correct]))", "0.0%"),
    ("games", "Market Accuracy"): ("AVERAGE(games[vegas_correct])", "0.0%"),
    ("games", "Elo Accuracy"): ("AVERAGE(games[elo_correct])", "0.0%"),
    ("games", "Home Win Rate"): ("AVERAGE(games[home_win])", "0.0%"),
    # 1 when no team is selected, or when the game involves the selected team
    ("games", "Selected Team Filter"):
        ("VAR t = SELECTEDVALUE(teams[team]) RETURN IF(ISBLANK(t), 1, "
         "IF(SELECTEDVALUE(games[home]) = t || SELECTEDVALUE(games[away]) = t, 1, 0))", "0"),
    ("games", "Team Games"): (f"CALCULATE(COUNTROWS(games), {TEAM_ROWS})", "#,0"),
    ("games", "Team Model Accuracy"): (f"CALCULATE(AVERAGE(games[model_correct]), {TEAM_ROWS})", "0.0%"),
    ("live_win_probability", "Home Win Probability"): ("AVERAGE(live_win_probability[home_win_prob])", "0%"),
    # 2026-27 picks, e.g. "12-5 (70.6%)"
    ("season_picks", "Record"):
        ('VAR n = COUNT(season_picks[model_correct]) VAR w = SUM(season_picks[model_correct]) '
         'RETURN IF(n = 0, "No games played yet", FORMAT(w, "0") & "-" & FORMAT(n - w, "0") '
         '& " (" & FORMAT(w / n, "0.0%") & ")")', None),
    ("season_picks", "Upcoming Games"): ('COUNTROWS(FILTER(season_picks, season_picks[stage] = "Upcoming"))', "#,0"),
    ("season_picks", "Last Updated"): ('MAX(season_picks[updated_utc]) & " UTC"', None),
}
PERCENT_COLUMNS = {
    "games": ["model_prob_home", "model_confidence", "elo_prob_home", "vegas_prob_home"],
    "season_accuracy": ["model_accuracy", "elo_accuracy", "home_team_accuracy", "vegas_accuracy",
                        "model_accuracy_on_lined_games"],
    "confidence": ["min_confidence", "share_of_games", "accuracy"],
    "live_checkpoints": ["accuracy", "accuracy_score_only"],
    "live_by_minute": ["accuracy", "accuracy_score_only"],
    "leakage_demo": ["test_accuracy"],
    "live_win_probability": ["home_win_prob"],
    "model_scorecard": ["accuracy"],
    "season_picks": ["model_prob_home", "model_confidence", "elo_prob_home"],
}

schema = "dbo." if is_schema_enabled(lakehouse=LAKEHOUSE) else ""   # a lakehouse with schemas keeps tables in dbo
directlake.generate_direct_lake_semantic_model(dataset=MODEL, tables={t: schema + t for t in TABLES},
                                               source=LAKEHOUSE, overwrite=True, refresh=False)

with connect_semantic_model(dataset=MODEL, readonly=False) as tom:
    tom.add_relationship(from_table="live_win_probability", from_column="game_id",
                         to_table="games", to_column="game_id",
                         from_cardinality="Many", to_cardinality="One")
    for (table, name), (expression, fmt) in MEASURES.items():
        tom.add_measure(table_name=table, measure_name=name, expression=expression, format_string=fmt)
    for table, columns in PERCENT_COLUMNS.items():
        for column in columns:
            tom.model.Tables[table].Columns[column].FormatString = "0.0%"
    tom.model.Tables["games"].Columns["game_id"].IsHidden = True

fabric.refresh_dataset(MODEL)
print(f"Semantic model '{MODEL}' is ready: {len(TABLES)} tables, {len(MEASURES)} measures")
