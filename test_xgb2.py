import xgboost as xgb
import os
import numpy as np

MODELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "Models")

_sleep_model = xgb.XGBClassifier()
_sleep_model.load_model(os.path.join(MODELS_PATH, 'sleep_model_v3.json'))

try:
    data = np.zeros((1, 17))
    probs = _sleep_model.predict_proba(data)
    print("predict_proba success:", probs)
except Exception as e:
    import traceback
    traceback.print_exc()
