"""Erzeugt kleine WAV-Töne in companion/assets/. Aufruf: python tools/gen_sounds.py"""
import math, os, struct, wave

OUT = os.path.join(os.path.dirname(__file__), "..", "companion", "assets")
RATE = 22050


def tone(path, freqs, dur, vol):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    per = int(RATE * dur)
    frames = bytearray()
    for f in freqs:                       # Sequenz kurzer Töne = Chime
        for i in range(per):
            env = min(1.0, i / 500) * min(1.0, (per - i) / 500)   # weiche Flanken
            s = int(vol * env * 32767 * math.sin(2 * math.pi * f * i / RATE))
            frames += struct.pack("<h", s)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(frames))


if __name__ == "__main__":
    tone(os.path.join(OUT, "waiting.wav"), [880, 1320, 1760], 0.16, 0.75)   # heller aufsteigender 3-Ton-Chime
    tone(os.path.join(OUT, "done.wav"), [988, 659], 0.18, 0.5)              # sanft absteigend
    tone(os.path.join(OUT, "error.wav"), [330, 247, 165], 0.15, 0.7)        # tiefer 3-Ton-Fehler
    print("wrote waiting.wav done.wav error.wav")
