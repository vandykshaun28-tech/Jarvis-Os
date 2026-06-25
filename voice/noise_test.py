import sounddevice as sd
import numpy as np

print("Stay quiet for 3 seconds...")
audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype="int16")
sd.wait()
level = float(abs(audio).mean())
print(f"Noise level: {level:.1f}")
print(f"Recommended threshold: {level * 3:.1f}")