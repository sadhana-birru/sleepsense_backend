from app.api import generate_report_logic
import numpy as np
import scipy.io.wavfile

scipy.io.wavfile.write("dummy.wav", 22050, np.zeros(22050 * 3, dtype=np.int16))

user_input = {
    'age': 30, 'gender': 1, 'occupation': 0, 'work_hours': 8.0, 
    'sleep_duration': 7.0, 'sleep_latency': 20, 'wake_count': 1, 
    'bedtime_num': 1380, 'waketime_num': 420, 'stress_level_num': 1
}

res = generate_report_logic(user_input, "I am feeling okay", "dummy.wav")
print("SUCCESS", res)
