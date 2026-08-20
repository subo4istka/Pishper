import winsound
import io
import wave
import math
import struct
import time

def _tone(freq, ms, vol=0.25, fade=10, sr=44100):
    n = int(sr * ms / 1000)
    fd = int(sr * fade / 1000)
    out = []
    for i in range(n):
        v = math.sin(2 * math.pi * freq * i / sr) * vol
        if i < fd: v *= i / fd
        elif i > n - fd: v *= (n - i) / fd
        out.append(int(v * 32767))
    return out

def _wav(samples, sr=44100):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()

def test_sound():
    print("Generating sound data...")
    # Ascending tones like 'spring' theme
    samples = _tone(1047, 70, 0.2) + _tone(1319, 90, 0.25)
    data = _wav(samples)
    
    print("Playing sound synchronously (SND_MEMORY)...")
    try:
        winsound.PlaySound(data, winsound.SND_MEMORY)
        print("Done playing (sync).")
    except Exception as e:
        print(f"Error (sync): {e}")

    time.sleep(1)
    
    print("Playing sound synchronously with SND_NODEFAULT...")
    try:
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        print("Done playing (sync + nodefault).")
    except Exception as e:
        print(f"Error (sync + nodefault): {e}")

if __name__ == "__main__":
    test_sound()
