import xgboost as xgb
import os

MODELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "Models")

try:
    clf = xgb.XGBClassifier()
    clf._estimator_type = "classifier"  # HACK
    clf.load_model(os.path.join(MODELS_PATH, 'sleep_model_v3.json'))
    print("XGBClassifier model loaded successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
