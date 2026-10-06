# NBA Game Predictor: 2026-27 picks

Runs every day. It pulls the 2026-27 schedule and results from ESPN's public scoreboard, carries every team's Elo rating forward from the end of 2025-26, rebuilds the pre-game features one game at a time from games already finished, and scores each game with the registered `nba-pregame-winner` model. Played games are graded and the next two weeks get a pick. The result is the `season_picks` table in `NBA_Lakehouse`, shown on the first page of the app.

Run `NBA_Game_Predictor` once first: this notebook reads its `games` and `teams` tables and its registered model.
