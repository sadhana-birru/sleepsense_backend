import xgboost as xgb
import os
import numpy as np

MODELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "Models")

_sleep_model = xgb.XGBClassifier()
_sleep_model.load_model(os.path.join(MODELS_PATH, 'sleep_model_v3.json'))

try:
    data = np.zeros((1, 17))
    probs_sklearn = _sleep_model.predict_proba(data)
    print("Sklearn predict_proba success:", probs_sklearn)
    
    dmatrix = xgb.DMatrix(data)
    probs_booster = _sleep_model.get_booster().predict(dmatrix)
    print("Booster predict success:", probs_booster)
except Exception as e:
    import traceback
    traceback.print_exc()
