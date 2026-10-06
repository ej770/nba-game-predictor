## Register both models in Fabric
import mlflow
from mlflow.models.signature import infer_signature

mlflow.autolog(disable=True)                 # the walk-forward loop fits many models; log only these
mlflow.set_experiment("nba-game-predictor")


def register(result, run_name, model_name, params):
    X, model = result["input_example"], result["model"]
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params(params)
        mlflow.log_metrics({k: float(v) for k, v in result["metrics"].items()})
        signature = infer_signature(X, model.predict_proba(X)[:, 1])
        mlflow.sklearn.log_model(model, artifact_path="model", signature=signature,
                                 input_example=X.head(5), registered_model_name=model_name)
    print(f"Registered {model_name} ({result['name']})")


register(pregame, "pregame-winner", "nba-pregame-winner",
         {"algorithm": pregame["name"], "fit_on": "2007-08 to 2025-26", "features": ", ".join(FEATURES)})
register(live, "live-win-probability", "nba-live-win-probability",
         {"algorithm": live["name"], "fit_on": "2010-11 to 2021-22", "snapshot_seconds": STEP})
