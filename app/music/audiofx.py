# musicalist – Klang: Equalizer-Presets und der mpv-Filter dazu (reine Logik, ohne GTK – gut testbar).
# mpv bekommt den Equalizer als Audiofilter: lavfi=[volume=…dB,equalizer=f=…:t=o:w=1:g=…dB,…,alimiter].
BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
LABELS = ["31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]
GAIN_MAX = 12                  # ±12 dB je Band

# Name → 10 Werte in dB (Anzeigereihenfolge = Reihenfolge hier)
PRESETS = {
    "flach":    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "bass+":    [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "höhen+":   [0, 0, 0, 0, 0, 1, 3, 4, 5, 6],
    "stimme":   [-2, -1, 0, 2, 4, 4, 3, 1, 0, -1],
    "loudness": [5, 3, 0, -1, -1, 0, -1, 0, 3, 4],
    "rock":     [4, 3, 1, -1, -2, 0, 2, 3, 4, 4],
    "elektro":  [5, 4, 1, 0, -2, 2, 1, 1, 4, 5],
    "akustik":  [3, 3, 2, 1, 1, 1, 2, 3, 3, 2],
}
DEFAULT = {"on": False, "preset": "flach", "gains": [0] * 10, "pre": 0}


def normalize(eq):
    """Gespeicherte/fremde Eingabe → gültiges Eq-Dict (zehn Werte im Bereich, Vorverstärkung ±12)."""
    out = dict(DEFAULT)
    if isinstance(eq, dict):
        out.update({k: eq[k] for k in DEFAULT if k in eq})
    g = out["gains"] if isinstance(out["gains"], (list, tuple)) else []
    g = [max(-GAIN_MAX, min(GAIN_MAX, float(x))) if isinstance(x, (int, float)) else 0.0 for x in g][:10]
    out["gains"] = g + [0.0] * (10 - len(g))
    pre = out["pre"] if isinstance(out["pre"], (int, float)) else 0
    out["pre"] = max(-GAIN_MAX, min(GAIN_MAX, float(pre)))
    out["on"] = bool(out["on"])
    out["preset"] = out["preset"] if isinstance(out["preset"], str) else "eigene"
    return out


def preset_name(gains):
    """Name des Presets, dessen Werte genau passen – sonst „eigene“."""
    for name, vals in PRESETS.items():
        if all(abs(a - b) < 0.05 for a, b in zip(gains, vals)):
            return name
    return "eigene"


def build_af(eq):
    """mpv-Audiofilter für das Eq-Dict; "" = aus (kein Eingriff in den Klang)."""
    eq = normalize(eq)
    if not eq["on"]:
        return ""
    gains = eq["gains"]
    if all(abs(g) < 0.05 for g in gains) and abs(eq["pre"]) < 0.05:
        return ""
    # Anheben macht lauter bis zum Übersteuern: halbe Anhebung gleich wieder abziehen, dann bleibt der Limiter selten aktiv
    pre = eq["pre"] - 0.5 * max(0.0, max(gains))
    parts = [f"volume={pre:.2f}dB"]
    parts += [f"equalizer=f={f}:t=o:w=1:g={g:.2f}" for f, g in zip(BANDS, gains) if abs(g) >= 0.05]
    parts.append("alimiter=limit=0.97")
    return "lavfi=[" + ",".join(parts) + "]"


CROSSFADE_CHOICES = [(0, "aus"), (2, "2 s"), (4, "4 s"), (6, "6 s"), (8, "8 s"), (12, "12 s")]
