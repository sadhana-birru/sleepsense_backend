import os
import torch
import joblib
import pandas as pd
import numpy as np
import librosa
import xgboost as xgb
from tensorflow.keras.models import load_model
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_PATH = os.path.join(BASE_DIR, "Models")

# Global model variables
feature_names = None
sleep_scaler = None
sleep_model = None
tokenizer = None
text_model = None
voice_model = None

def load_models():
    """Load all ML models into memory."""
    global feature_names, sleep_scaler, sleep_model, tokenizer, text_model, voice_model
    print("Initializing SleepSense AI Triple-Fusion Engine...")
    
    # Load Physical Assets
    try:
        feature_names = joblib.load(os.path.join(MODELS_PATH, 'feature_list_v3.pkl'))
        sleep_scaler = joblib.load(os.path.join(MODELS_PATH, 'sleep_scaler_v3.pkl'))
        sleep_model = xgb.XGBClassifier()
        sleep_model.load_model(os.path.join(MODELS_PATH, 'sleep_model_v3.json'))
        print("Physical Model Loaded (XGBoost)")
    except Exception as e:
        print(f"Error loading Physical Model: {e}")

    # Load Mental Assets
    try:
        tokenizer = AutoTokenizer.from_pretrained(os.path.join(MODELS_PATH, "mental_bert_model"))
        text_model = AutoModelForSequenceClassification.from_pretrained(os.path.join(MODELS_PATH, "mental_bert_model"))
        print("Mental Model Loaded (MentalBERT)")
    except Exception as e:
        print(f"Error loading Mental Model: {e}")

    # Load Vocal Assets
    try:
        # Check if voice_model.h5 exists
        voice_model_path = os.path.join(MODELS_PATH, 'voice_model.h5')
        if os.path.exists(voice_model_path):
            voice_model = load_model(voice_model_path)
            print("Vocal Model Loaded (1D-CNN)")
        else:
            print("Vocal Model file not found, skipping...")
    except Exception as e:
        print(f"Error loading Vocal Model: {e}")

def get_voice_features(file_path_or_bytes):
    """Extracts MFCC features for the CNN model."""
    X, sr = librosa.load(file_path_or_bytes, res_type='kaiser_fast', duration=2.5, sr=22050, offset=0.5)
    mfccs = np.mean(librosa.feature.mfcc(y=X, sr=sr, n_mfcc=40).T, axis=0)
    return np.expand_dims(np.expand_dims(mfccs, axis=0), axis=2)

def hybrid_fusion_logic(p_risk, t_risk, v_risk):
    """Combines model outputs with clinical red-flag overrides."""
    # Clinical Overrides: If any single factor is extremely high, override the weighted average
    if t_risk > 0.85 or p_risk > 0.85 or v_risk > 0.90:
        return max(p_risk, t_risk, v_risk), "CRITICAL RISK", "URGENT: Extreme distress detected in one or more indicators."
    
    # Weights: Physical/Sleep (50%), Mental (30%), Vocal (20%)
    total_score = (p_risk * 0.50) + (t_risk * 0.30) + (v_risk * 0.20)
    
    # Adjusted Thresholds for higher sensitivity
    if total_score > 0.70:
        status, advice = "CRITICAL RISK", "High cumulative load. Urgent rest and consultation advised."
    elif total_score > 0.40:
        status = "MODERATE RISK"
        if t_risk > p_risk and t_risk > v_risk: 
            advice = "Mental fatigue is dominant. Consider cognitive breaks."
        elif p_risk > t_risk and p_risk > v_risk:
            advice = "Physical burnout detected. Prioritize sleep hygiene."
        else:
            advice = "Emotional stress detected. Practice mindfulness or relaxation."
    else:
        status, advice = "STABLE", "All indicators are within normal safety ranges."
        
    return total_score, status, advice

def generate_report_logic(user_input: dict, text_msg: str, audio_file_path: str = None):
    """
    Processes user data, runs inferences, and generates the final report data.
    """
    # 1. Extract Demographics & Biometrics
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

    # Smartwatch data (Auto-fill if missing or not provided)
    deep = user_input.get('deep_sleep_percent')
    if deep is None: deep = 20.0
    rem = user_input.get('rem_sleep_percent')
    if rem is None: rem = 22.0
    
    # Auto-calculate Efficiency if missing
    eff = user_input.get('sleep_efficiency')
    if eff is None:
        in_bed_mins = (wak_m - bed_m) % 1440
        if in_bed_mins == 0: in_bed_mins = 480
        calculated_eff = (dur / (in_bed_mins / 60)) * 100
        eff = min(calculated_eff, 98.0)

    # 2. Advanced Feature Engineering
    deficit = 8.0 - dur
    intensity = work / (dur + 0.5)
    restless = wake * lat
    drift = min(abs(bed_m - 1380), 1440 - abs(bed_m - 1380))
    
    p_risk = 0.0
    t_risk = 0.0
    v_risk = 0.0

    # 3. Physical Prediction
    if sleep_model is not None and sleep_scaler is not None and feature_names is not None:
        p_features = [age, gen, occ, work, dur, lat, eff, wake, bed_m, wak_m, 
                    deep, rem, stress, deficit, intensity, restless, drift]
        # Ensure the order matches feature_names
        p_df = pd.DataFrame([p_features], columns=feature_names)
        p_risk = float(sleep_model.predict_proba(sleep_scaler.transform(p_df[feature_names]))[0][1])

        # Heuristic Boosts: Ensure physical risk triggers for extreme values
        if dur < 4.0: p_risk = max(p_risk, 0.95)   # Extreme danger zone (3h or less)
        elif dur < 5.0: p_risk = max(p_risk, 0.85) # Severe sleep deprivation
        elif dur < 6.0: p_risk = max(p_risk, 0.60) # Moderate sleep deprivation
        
        if wake > 4: p_risk = max(p_risk, 0.70)   # High sleep fragmentation
        if work > 12: p_risk = max(p_risk, 0.65)  # Severe overwork
        elif work > 10: p_risk = max(p_risk, 0.50) # Moderate overwork

    # 4. Mental Prediction (MentalBERT)
    # Classes: ['Anxiety', 'Depression', 'Normal', 'Suicidal']
    if text_model is not None and tokenizer is not None and text_msg.strip():
        print(f"DEBUG | Analyzing Text: '{text_msg[:30]}...'")
        t_inputs = tokenizer(text_msg, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            t_outputs = text_model(**t_inputs)
            t_probs = torch.nn.functional.softmax(t_outputs.logits, dim=-1).numpy()[0]
        
        # Risk = 1.0 - Probability of "Normal" (Index 2)
        if len(t_probs) >= 3:
            t_risk = float(1.0 - t_probs[2])
        else:
            t_risk = float(t_probs.max())
            
        # Keyword Emotional Booster (Red Flags)
        anger_keywords = ['angry', 'irritated', 'annoyed', 'pissed', 'frustrated', 'mad']
        distress_keywords = ['depressed', 'sad', 'help', 'hopeless', 'suicide', 'kill', 'end']
        
        text_lower = text_msg.lower()
        if any(w in text_lower for w in distress_keywords):
            t_risk = max(t_risk, 0.85)
        elif any(w in text_lower for w in anger_keywords):
            t_risk = max(t_risk, 0.65)
    else:
        if not text_msg.strip():
            print("DEBUG | No text message provided for analysis.")

    # 5. Vocal Prediction (CNN on RAVDESS)
    # Classes: 0:Neutral, 1:Calm, 2:Happy, 3:Sad, 4:Angry, 5:Fear, 6:Disgust, 7:Surprise
    if voice_model is not None and audio_file_path:
        try:
            v_input = get_voice_features(audio_file_path)
            v_probs = voice_model.predict(v_input, verbose=0)[0]
            # Sum the distress-related probabilities: Sad, Angry, Fear, Disgust
            if len(v_probs) >= 7:
                v_risk = float(v_probs[3] + v_probs[4] + v_probs[5] + v_probs[6])
            else:
                v_risk = float(v_probs.max())
        except Exception as e:
            print(f"Error processing audio: {e}")
            v_risk = 0.0 

    # 6. Fusion & Output
    final_score, status, advice = hybrid_fusion_logic(p_risk, t_risk, v_risk)

    print(f"DEBUG | P: {p_risk:.2f} | T: {t_risk:.2f} | V: {v_risk:.2f} | Final: {final_score:.2f} | {status}")

    return {
        "physical_score": p_risk,
        "mental_score": t_risk,
        "vocal_score": v_risk,
        "overall_score": final_score,
        "status": status,
        "advice": advice
    }
