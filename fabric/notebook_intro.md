# NBA Game Predictor

Pre-game winner picks and a live win-probability model for NBA games, built from 35,527 regular-season games (1996-97 to 2025-26) of play-by-play data.

**What this notebook does**

1. Downloads the raw data, pinned to fixed commits and checked against SHA-256 checksums: play-by-play and shot charts from [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data), and closing betting lines from the Sportsbook Review archive in [kyleskom/NBA-Machine-Learning-Sports-Betting](https://github.com/kyleskom/NBA-Machine-Learning-Sports-Betting).
2. Builds game results and pre-game features: Elo ratings, rest and back-to-backs, season and last-10 form, league-wide home-court edge.
3. Trains the pre-game model and grades it on the four most recent seasons (2022-23 to 2025-26), against Elo, the home team and the betting market.
4. Trains the live win-probability model (score, clock and the pre-game view, every 15 seconds of every game).
5. Registers both models in Fabric (MLflow) and saves the report tables to the `NBA_Lakehouse` Lakehouse.

Every season is predicted by a model trained only on earlier seasons, so the reported accuracy is what the model would have achieved in real time. Runs in about 10 minutes on a starter pool.

*Emmanuel Jibiri · Data Analyst · Houston, TX*
