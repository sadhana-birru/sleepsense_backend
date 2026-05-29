import joblib
import os
import sys

MODELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "Models")

try:
    scaler = joblib.load(os.path.join(MODELS_PATH, 'sleep_scaler_v3.pkl'))
    print("Scaler loaded successfully:", type(scaler))
except Exception as e:
    import traceback
    traceback.print_exc()
