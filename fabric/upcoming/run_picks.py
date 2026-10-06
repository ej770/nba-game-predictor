## Score the schedule with the registered model and save the picks to NBA_Lakehouse
import mlflow
import sempy.fabric as fabric

mlflow.autolog(disable=True)
games = spark.read.table("games").toPandas()            # saved by NBA_Game_Predictor
teams = spark.read.table("teams").toPandas()
model = mlflow.sklearn.load_model("models:/nba-pregame-winner/latest")

picks = season_picks(fetch_schedule(date.today()), games, teams, model)
schema = ("game_id long, season_label string, game_date date, tipoff_utc timestamp, game_label string, "
          "home string, away string, stage string, status string, home_pts double, away_pts double, "
          "final_score string, winner string, model_prob_home double, model_pick string, "
          "model_confidence double, model_correct double, elo_prob_home double, elo_home double, "
          "elo_away double, updated_utc string")
pdf = picks.assign(game_date=picks["game_date"].dt.date, tipoff_utc=picks["tipoff_utc"].dt.tz_localize(None))
rows = [[v.to_pydatetime() if isinstance(v, pd.Timestamp) else v for v in row]   # Spark takes datetime, not pd.Timestamp
        for row in pdf.astype(object).where(pdf.notna(), None).values.tolist()]
(spark.createDataFrame(rows, schema).write.mode("overwrite").option("overwriteSchema", "true")
 .format("delta").saveAsTable("season_picks"))

graded = picks["model_correct"].notna()
record = f" ({picks.loc[graded, 'model_correct'].mean():.1%} picked right)" if graded.any() else ""
print(f"{len(picks)} games: {int(graded.sum())} played{record}, {int((~graded).sum())} upcoming")
if "NBA Game Predictor" in set(fabric.list_datasets()["Dataset Name"]):
    fabric.refresh_dataset("NBA Game Predictor")        # so the app shows today's picks
