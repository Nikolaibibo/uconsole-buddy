"""Erzeugt kleine WAV-Töne in companion/assets/. Aufruf: python tools/gen_sounds.py"""
import math, os, struct, wave

OUT = os.path.join(os.path.dirname(__file__), "..", "companion", "assets")
RATE = 22050


def tone(path, freqs, dur=0.18, vol=0.4):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = bytearray()
    per = int(RATE * dur)
    for f in freqs:                       # Sequenz kurzer Töne = Chime
        for i in range(per):
            env = min(1.0, i / 400) * min(1.0, (per - i) / 400)   # weiche Flanken
            s = int(vol * env * 32767 * math.sin(2 * math.pi * f * i / RATE))
            frames += struct.pack("<h", s)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(frames))


if __name__ == "__main__":
    tone(os.path.join(OUT, "waiting.wav"), [880, 1175])   # deutlicher Zwei-Ton-Chime
    tone(os.path.join(OUT, "done.wav"), [660], dur=0.15, vol=0.25)  # sanft
    tone(os.path.join(OUT, "error.wav"), [300, 220], dur=0.14)      # tiefer Fehlerton
    print("wrote waiting.wav done.wav error.wav")
