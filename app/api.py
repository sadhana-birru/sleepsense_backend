# import os
# import traceback

# # Paths
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# MODELS_PATH = os.path.join(BASE_DIR, "Models")

# # ---------------------------------------------------------------------------
# # PROPER LAZY-LOADING: No ML libraries loaded at startup!
# # To prevent "No open ports detected" on Render, all heavy libraries
# # (TensorFlow, PyTorch, Transformers, XGBoost, Pandas, Numpy) are imported 
# # inside the functions that use them.
# # ---------------------------------------------------------------------------

# _feature_names = None
# _sleep_scaler = None
# _sleep_model = None
# _tokenizer = None
# _text_model = None
# _voice_model = None

# # Sentinel to distinguish "not yet loaded" from "loaded but is None"
# _NOT_LOADED = object()
# _physical_loaded = _NOT_LOADED
# _mental_loaded = _NOT_LOADED
# _vocal_loaded = _NOT_LOADED

# def get_physical_models():
#     """Lazy-load Physical/Sleep model assets (XGBoost + scaler + feature list).
#     Returns (feature_names, sleep_scaler, sleep_model) — any may be None on error.
#     """
#     global _feature_names, _sleep_scaler, _sleep_model, _physical_loaded

#     if _physical_loaded is not _NOT_LOADED:
#         return _feature_names, _sleep_scaler, _sleep_model

#     print("[LAZY] Loading Physical Model assets (XGBoost)...")
#     try:
#         # Import inside the function so it doesn't block FastAPI startup
#         import joblib
#         import xgboost as xgb
        
#         _feature_names = joblib.load(os.path.join(MODELS_PATH, 'feature_list_v3.pkl'))
#         _sleep_scaler = joblib.load(os.path.join(MODELS_PATH, 'sleep_scaler_v3.pkl'))
#         _sleep_model = xgb.XGBClassifier()
        
#         # Fix for XGBoost/Scikit-learn version mismatch causing TypeError
#         _sleep_model._estimator_type = "classifier"
        
#         _sleep_model.load_model(os.path.join(MODELS_PATH, 'sleep_model_v3.json'))
        
#         # Inject missing scikit-learn wrapper attributes
#         import numpy as np
#         _sleep_model.n_classes_ = 2
        
#         print("[LAZY] Physical Model Loaded (XGBoost)")
#     except Exception as e:
#         print(f"[LAZY] Error loading Physical Model: {e}")

#     _physical_loaded = True
#     return _feature_names, _sleep_scaler, _sleep_model


# def get_mental_models():
#     """Lazy-load Mental/Text model assets (MentalBERT tokenizer + model).
#     Returns (tokenizer, text_model) — either may be None on error.
#     """
#     global _tokenizer, _text_model, _mental_loaded

#     if _mental_loaded is not _NOT_LOADED:
#         return _tokenizer, _text_model

#     print("[LAZY] Loading Mental Model assets (MentalBERT)...")
#     try:
#         # Import inside the function so it doesn't block FastAPI startup
#         from transformers import AutoTokenizer, AutoModelForSequenceClassification
        
#         _tokenizer = AutoTokenizer.from_pretrained(
#             os.path.join(MODELS_PATH, "mental_bert_model")
#         )
#         _text_model = AutoModelForSequenceClassification.from_pretrained(
#             os.path.join(MODELS_PATH, "mental_bert_model")
#         )
#         print("[LAZY] Mental Model Loaded (MentalBERT)")
#     except Exception as e:
#         print(f"[LAZY] Error loading Mental Model: {e}")

#     _mental_loaded = True
#     return _tokenizer, _text_model


# def get_voice_model():
#     """Lazy-load Vocal model (Keras 1D-CNN).
#     Returns the loaded Keras model or None on error.
#     """
#     global _voice_model, _vocal_loaded

#     if _vocal_loaded is not _NOT_LOADED:
#         return _voice_model

#     print("[LAZY] Loading Vocal Model assets (1D-CNN)...")
#     try:
#         # Import inside the function so it doesn't block FastAPI startup
#         from tensorflow.keras.models import load_model
        
#         # Try .keras format first (modern Keras 3.x), fall back to .h5
#         voice_keras_path = os.path.join(MODELS_PATH, 'voice_model.keras')
#         voice_h5_path = os.path.join(MODELS_PATH, 'voice_model.h5')
#         if os.path.exists(voice_keras_path):
#             _voice_model = load_model(voice_keras_path)
#             print("[LAZY] Vocal Model Loaded (1D-CNN, .keras format)")
#         elif os.path.exists(voice_h5_path):
#             _voice_model = load_model(voice_h5_path)
#             print("[LAZY] Vocal Model Loaded (1D-CNN, .h5 format)")
#         else:
#             print("[LAZY] Vocal Model file not found, skipping...")
#     except Exception as e:
#         print(f"[LAZY] Error loading Vocal Model: {e}")

#     _vocal_loaded = True
#     return _voice_model


# # ---------------------------------------------------------------------------
# # BACKWARD-COMPAT: keep load_models() so existing callers don't break,
# # but it is now a no-op (models load lazily on first use).
# # ---------------------------------------------------------------------------

# def load_models():
#     """No-op stub kept for backward compatibility.
#     Models are now lazy-loaded on first API call to avoid blocking startup.
#     """
#     print("SleepSense AI Triple-Fusion Engine ready (proper lazy-loading enabled).")


# # ---------------------------------------------------------------------------
# # FEATURE EXTRACTION
# # ---------------------------------------------------------------------------

# def get_voice_features(file_path_or_bytes):
#     """Extracts MFCC features for the CNN model."""
#     import librosa
#     import numpy as np

#     # Get audio duration first to handle short recordings
#     total_duration = librosa.get_duration(path=file_path_or_bytes)
#     print(f"DEBUG | Audio duration: {total_duration:.2f}s")

#     # Adjust offset for short recordings (offset=0.5 would skip entire audio if < 0.5s)
#     offset = min(0.5, max(0.0, total_duration - 0.5))
#     duration = min(2.5, total_duration - offset)

#     if duration <= 0.05:
#         print(f"DEBUG | Audio too short ({total_duration:.2f}s) for analysis")
#         raise ValueError(f"Audio too short ({total_duration:.2f}s), need at least 0.5s")

#     X, sr = librosa.load(file_path_or_bytes, res_type='kaiser_fast', duration=duration, sr=22050, offset=offset)

#     if len(X) == 0:
#         raise ValueError("Loaded audio is empty after resampling")

#     mfccs = np.mean(librosa.feature.mfcc(y=X, sr=sr, n_mfcc=40).T, axis=0)
#     return np.expand_dims(np.expand_dims(mfccs, axis=0), axis=2)


# # ---------------------------------------------------------------------------
# # FUSION LOGIC
# # ---------------------------------------------------------------------------

# def hybrid_fusion_logic(p_risk, t_risk, v_risk):
#     """Combines model outputs with clinical red-flag overrides."""
#     # Clinical Overrides: If any single factor is extremely high, override the weighted average
#     if t_risk > 0.85 or p_risk > 0.85 or v_risk > 0.90:
#         return max(p_risk, t_risk, v_risk), "CRITICAL RISK", "URGENT: Extreme distress detected in one or more indicators."

#     # Weights: Physical/Sleep (50%), Mental (30%), Vocal (20%)
#     total_score = (p_risk * 0.50) + (t_risk * 0.30) + (v_risk * 0.20)

#     # Adjusted Thresholds for higher sensitivity
#     if total_score > 0.70:
#         status, advice = "CRITICAL RISK", "High cumulative load. Urgent rest and consultation advised."
#     elif total_score > 0.40:
#         status = "MODERATE RISK"
#         if t_risk > p_risk and t_risk > v_risk: 
#             advice = "Mental fatigue is dominant. Consider cognitive breaks."
#         elif p_risk > t_risk and p_risk > v_risk:
#             advice = "Physical burnout detected. Prioritize sleep hygiene."
#         else:
#             advice = "Emotional stress detected. Practice mindfulness or relaxation."
#     else:
#         status, advice = "STABLE", "All indicators are within normal safety ranges."

#     return total_score, status, advice


# # ---------------------------------------------------------------------------
# # MAIN INFERENCE PIPELINE
# # ---------------------------------------------------------------------------

# def generate_report_logic(user_input: dict, text_msg: str, audio_file_path: str = None):
#     """
#     Processes user data, runs inferences, and generates the final report data.
#     Models are lazy-loaded on the first call to this function.
#     """
#     # Import heavy libraries here so they don't load at startup
#     import pandas as pd
#     import torch
#     import numpy as np

#     # 1. Extract Demographics & Biometrics
#     age = user_input.get('age', 30)
#     gen = user_input.get('gender', 1)
#     occ = user_input.get('occupation', 0)
#     work = user_input.get('work_hours', 8.0)
#     dur = user_input.get('sleep_duration', 7.0)
#     lat = user_input.get('sleep_latency', 20)
#     wake = user_input.get('wake_count', 1)
#     bed_m = user_input.get('bedtime_num', 1380)
#     wak_m = user_input.get('waketime_num', 420)
#     stress = user_input.get('stress_level_num', 1)

#     # Smartwatch data (Auto-fill if missing or not provided)
#     deep = user_input.get('deep_sleep_percent')
#     if deep is None: deep = 20.0
#     rem = user_input.get('rem_sleep_percent')
#     if rem is None: rem = 22.0

#     # Auto-calculate Efficiency if missing
#     eff = user_input.get('sleep_efficiency')
#     if eff is None:
#         in_bed_mins = (wak_m - bed_m) % 1440
#         if in_bed_mins == 0: in_bed_mins = 480
#         calculated_eff = (dur / (in_bed_mins / 60)) * 100
#         eff = min(calculated_eff, 98.0)

#     # 2. Advanced Feature Engineering
#     deficit = 8.0 - dur
#     intensity = work / (dur + 0.5)
#     restless = wake * lat
#     drift = min(abs(bed_m - 1380), 1440 - abs(bed_m - 1380))

#     p_risk = 0.0
#     t_risk = 0.0
#     v_risk = 0.0

#     # 3. Physical Prediction — lazy-load models on first call
#     feature_names, sleep_scaler, sleep_model = get_physical_models()

#     if sleep_model is not None and sleep_scaler is not None and feature_names is not None:
#         p_features = [age, gen, occ, work, dur, lat, eff, wake, bed_m, wak_m, 
#                     deep, rem, stress, deficit, intensity, restless, drift]
#         # Ensure the order matches feature_names
#         p_df = pd.DataFrame([p_features], columns=feature_names)
#         p_risk = float(sleep_model.predict_proba(sleep_scaler.transform(p_df[feature_names]))[0][1])

#         # Heuristic Boosts: Ensure physical risk triggers for extreme values
#         if dur < 4.0: p_risk = max(p_risk, 0.95)   # Extreme danger zone (3h or less)
#         elif dur < 5.0: p_risk = max(p_risk, 0.85) # Severe sleep deprivation
#         elif dur < 6.0: p_risk = max(p_risk, 0.60) # Moderate sleep deprivation

#         if wake > 4: p_risk = max(p_risk, 0.70)   # High sleep fragmentation
#         if work > 12: p_risk = max(p_risk, 0.65)  # Severe overwork
#         elif work > 10: p_risk = max(p_risk, 0.50) # Moderate overwork

#     # 4. Mental Prediction (MentalBERT) — lazy-load models on first call
#     tokenizer, text_model = get_mental_models()

#     # Classes: ['Anxiety', 'Depression', 'Normal', 'Suicidal']
#     if text_model is not None and tokenizer is not None and text_msg.strip():
#         print(f"DEBUG | Analyzing Text: '{text_msg[:30]}...'")
#         t_inputs = tokenizer(text_msg, return_tensors="pt", padding=True, truncation=True)
#         with torch.no_grad():
#             t_outputs = text_model(**t_inputs)
#             t_probs = torch.nn.functional.softmax(t_outputs.logits, dim=-1).numpy()[0]

#         # Risk = 1.0 - Probability of "Normal" (Index 2)
#         if len(t_probs) >= 3:
#             t_risk = float(1.0 - t_probs[2])
#         else:
#             t_risk = float(t_probs.max())

#         # Keyword Emotional Booster (Red Flags)
#         anger_keywords = ['angry', 'irritated', 'annoyed', 'pissed', 'frustrated', 'mad']
#         distress_keywords = ['depressed', 'sad', 'help', 'hopeless', 'suicide', 'kill', 'end']

#         text_lower = text_msg.lower()
#         if any(w in text_lower for w in distress_keywords):
#             t_risk = max(t_risk, 0.85)
#         elif any(w in text_lower for w in anger_keywords):
#             t_risk = max(t_risk, 0.65)
#     else:
#         if not text_msg.strip():
#             print("DEBUG | No text message provided for analysis.")

#     # 5. Vocal Prediction (CNN on RAVDESS) — lazy-load model on first call
#     voice_model = get_voice_model()

#     # Classes: 0:Neutral, 1:Calm, 2:Happy, 3:Sad, 4:Angry, 5:Fear, 6:Disgust, 7:Surprise
#     if voice_model is not None and audio_file_path:
#         try:
#             v_input = get_voice_features(audio_file_path)
#             print(f"DEBUG | Voice features shape: {v_input.shape}, range: [{v_input.min():.4f}, {v_input.max():.4f}]")

#             # Use direct model call instead of model.predict() to avoid
#             # TF 2.21/Keras 3.x XLA Autotuner crash on Softmax layer
#             v_output = voice_model(v_input, training=False)
#             v_probs = v_output.numpy()[0] if hasattr(v_output, 'numpy') else np.array(v_output[0])

#             print(f"DEBUG | Voice raw probs: {v_probs}")
#             # Sum the distress-related probabilities: Sad, Angry, Fear, Disgust
#             if len(v_probs) >= 7:
#                 v_risk = float(v_probs[3] + v_probs[4] + v_probs[5] + v_probs[6])
#             else:
#                 v_risk = float(v_probs.max())
#             print(f"DEBUG | Voice risk computed: {v_risk:.4f}")
#         except Exception as e:
#             print(f"Error processing audio: {e}")
#             traceback.print_exc()
#             v_risk = 0.0 

#     # 6. Fusion & Output
#     final_score, status, advice = hybrid_fusion_logic(p_risk, t_risk, v_risk)

#     print(f"DEBUG | P: {p_risk:.2f} | T: {t_risk:.2f} | V: {v_risk:.2f} | Final: {final_score:.2f} | {status}")

#     return {
#         "physical_score": p_risk,
#         "mental_score": t_risk,
#         "vocal_score": v_risk,
#         "overall_score": final_score,
#         "status": status,
#         "advice": advice
#     }
import os
import traceback
import requests

# -------------------------------------------------------------------
# ENV VARIABLES (Render)
# -------------------------------------------------------------------

HF_TOKEN = os.getenv("HF_TOKEN")

MENTAL_MODEL = "AYUSHPATIL02/sleepsense-mentalbert"
VOICE_MODEL = "AYUSHPATIL02/sleepsense-voice-model"
BOOST_MODEL = "AYUSHPATIL02/sleepsense-boost-model"

HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

# -------------------------------------------------------------------
# HF API CALL HELPERS
# -------------------------------------------------------------------

def call_hf_model(model_name, payload):
    """
    Generic HuggingFace inference API caller
    """
    url = f"https://api-inference.huggingface.co/models/{model_name}"

    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=60)
        return response.json()
    except Exception as e:
        print("HF API Error:", e)
        return {"error": str(e)}


# -------------------------------------------------------------------
# VOICE FEATURES (kept local - preprocessing only)
# -------------------------------------------------------------------

def get_voice_features(file_path):
    import librosa
    import numpy as np

    total_duration = librosa.get_duration(path=file_path)

    offset = min(0.5, max(0.0, total_duration - 0.5))
    duration = min(2.5, total_duration - offset)

    if duration <= 0.05:
        raise ValueError("Audio too short for analysis")

    X, sr = librosa.load(
        file_path,
        sr=22050,
        duration=duration,
        offset=offset
    )

    mfccs = np.mean(librosa.feature.mfcc(y=X, sr=sr, n_mfcc=40).T, axis=0)

    return mfccs.reshape(1, 40).tolist()  # convert for HF JSON


# -------------------------------------------------------------------
# FUSION LOGIC
# -------------------------------------------------------------------

def hybrid_fusion_logic(p_risk, t_risk, v_risk):

    if t_risk > 0.85 or p_risk > 0.85 or v_risk > 0.90:
        return max(p_risk, t_risk, v_risk), "CRITICAL RISK", \
               "URGENT: Extreme distress detected in one or more indicators."

    total_score = (p_risk * 0.50) + (t_risk * 0.30) + (v_risk * 0.20)

    if total_score > 0.70:
        status = "CRITICAL RISK"
        advice = "High cumulative load. Urgent rest and consultation advised."
    elif total_score > 0.40:
        status = "MODERATE RISK"
        advice = "Take breaks, manage stress, and monitor sleep quality."
    else:
        status = "STABLE"
        advice = "All indicators are within normal range."

    return total_score, status, advice



def generate_report_logic(user_input: dict, text_msg: str, audio_file_path: str = None):

    # -----------------------------
    # 1. INPUT FEATURES
    # -----------------------------
    age = user_input.get('age', 30)
    gen = user_input.get('gender', 1)
    occ = user_input.get('occupation', 0)
    work = user_input.get('work_hours', 8.0)
    dur = user_input.get('sleep_duration', 7.0)
    lat = user_input.get('sleep_latency', 20)
    wake = user_input.get('wake_count', 1)
    bed_m = user_input.get('bedtime_num', 1380)
    wak_m = user_input.get('waketime_num', 420)
    stress = user_input.get('stress_level_num', 1)

    deep = user_input.get('deep_sleep_percent', 20.0)
    rem = user_input.get('rem_sleep_percent', 22.0)

    eff = user_input.get('sleep_efficiency')
    if eff is None:
        in_bed = (wak_m - bed_m) % 1440
        if in_bed == 0:
            in_bed = 480
        eff = min((dur / (in_bed / 60)) * 100, 98.0)

    deficit = 8.0 - dur
    intensity = work / (dur + 0.5)
    restless = wake * lat
    drift = min(abs(bed_m - 1380), 1440 - abs(bed_m - 1380))

    p_features = [
        age, gen, occ, work, dur, lat, eff, wake,
        bed_m, wak_m, deep, rem, stress,
        deficit, intensity, restless, drift
    ]

    # -----------------------------
    # 2. PHYSICAL MODEL
    # -----------------------------
    try:
        p_result = call_hf_model(BOOST_MODEL, {"inputs": p_features})
        p_risk = float(p_result[0]) if isinstance(p_result, list) else 0.5
    except:
        p_risk = 0.5

    # safety boosts
    if dur < 4:
        p_risk = max(p_risk, 0.95)
    elif dur < 5:
        p_risk = max(p_risk, 0.85)
    elif dur < 6:
        p_risk = max(p_risk, 0.60)

    if wake > 4:
        p_risk = max(p_risk, 0.70)

    # -----------------------------
    # 3. MENTAL MODEL (FIXED)
    # -----------------------------
    t_risk = 0.0

    if text_msg and text_msg.strip():
        try:
            m_result = call_hf_model(
                MENTAL_MODEL,
                {"inputs": text_msg}
            )

            if isinstance(m_result, list) and len(m_result) > 0:
                scores = m_result[0]
                best = max(scores, key=lambda x: x["score"])
                t_risk = best["score"]
            else:
                t_risk = 0.5

        except Exception as e:
            print("Mental model error:", e)
            t_risk = 0.5

    # -----------------------------
    # 4. VOICE MODEL (FIXED)
    # -----------------------------
    v_risk = 0.0

    if audio_file_path and str(audio_file_path).lower() not in ["none", "", "null"]:
        try:
            v_features = get_voice_features(audio_file_path)

            v_result = call_hf_model(
                VOICE_MODEL,
                {"inputs": v_features}
            )

            if isinstance(v_result, list) and len(v_result) > 0:
                v_probs = v_result[0]
                v_risk = sum(v_probs[3:7]) if isinstance(v_probs, list) else 0.0

        except Exception as e:
            print("Voice model error:", e)
            v_risk = 0.0

    # -----------------------------
    # 5. FUSION
    # -----------------------------
    final_score, status, advice = hybrid_fusion_logic(p_risk, t_risk, v_risk)

    print(f"DEBUG | P:{p_risk:.2f} T:{t_risk:.2f} V:{v_risk:.2f} FINAL:{final_score:.2f}")

    return {
        "physical_score": p_risk,
        "mental_score": t_risk,
        "vocal_score": v_risk,
        "overall_score": final_score,
        "status": status,
        "advice": advice
    }