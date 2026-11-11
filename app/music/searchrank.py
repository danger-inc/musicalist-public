"""Was ist mit der Suche wahrscheinlich gemeint? (Gegenstück zu SearchRank.kt am Handy.)
Punktzahl = Namenstreffer (am wichtigsten) + eigenes Hören (Hörprotokoll) + Beliebtheit (Platz in YouTubes Reihenfolge) + Grundneigung je Art."""
import math
import re
import time
import unicodedata

PRIOR = {"artist": 0.35, "song": 0.25, "album": 0.1, "playlist": 0.0, "podcast": 0.0}


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    return re.sub(r"[^\w]+", " ", s).replace("_", " ").strip()


def name_match(q, name, sub=""):
    nq, nn = norm(q), norm(name)
    if not nq or not nn:
        return 0.0
    if nn == nq:
        return 1.0
    both = norm(f"{name} {sub}").split()
    toks = nq.split()
    best = 0.78 if nn.startswith(nq + " ") else 0.6 if (f" {nq} " in f" {nn} ") else 0.5 if nq in nn else 0.0
    if len(toks) > 1 and all(t in both for t in toks):
        best = max(best, 0.85)
    elif toks:
        best = max(best, 0.45 * sum(t in both for t in toks) / len(toks))
    return best


PICK_DAYS = 60


def pick_bonus(ident, st, now=None):
    """0..0,8: wie frisch der Titel zuletzt aus der Suche gespielt wurde („neulich gesucht“; nach 60 Tagen 0)."""
    picks = st[2] if len(st) > 2 else {}
    t = picks.get(ident)
    if not t:
        return 0.0
    age = ((now or time.time()) - t) / 86400.0
    return 0.8 * (1 - age / PICK_DAYS) if 0 <= age <= PICK_DAYS else 0.0


def favor(kind, ident, st):
    """Bekannte Titel zuerst: schon gehört (Hörprotokoll) oder neulich aus der Suche gespielt. 0 = unbekannt."""
    if kind != "song" or not ident:
        return 0.0
    plays = st[0].get(ident, 0)
    return (0.9 * math.log(1 + plays) if plays > 0 else 0.0) + pick_bonus(ident, st)


def mark(ident, st):
    """Kleines Symbol vor dem Titel: Lupe = neulich gesucht/gespielt, Uhr = schon mal gehört."""
    if pick_bonus(ident, st) > 0:
        return "󰍉"
    return "󰋚" if st[0].get(ident, 0) > 0 else ""


def stats(rows, picks=None):
    """rows: (at, vid, title, artist, dur) des Hörprotokolls → Zähler je Titel-ID und Künstler (+ gemerkte Such-Treffer)."""
    by_id, by_art = {}, {}
    for r in rows:
        try:
            _at, vid, _title, artist, _dur = r[:5]
        except ValueError:
            continue
        by_id[vid] = by_id.get(vid, 0) + 1
        for a in str(artist or "").split(","):
            a = norm(a)
            if a:
                by_art[a] = by_art.get(a, 0) + 1
    return by_id, by_art, dict(picks or {})


def score(q, kind, name, sub, rank, ident, st):
    m = name_match(q, name, sub)
    by_id, by_art = st[0], st[1]
    plays = by_id.get(ident, 0) if kind == "song" else by_art.get(norm(name), 0) if kind == "artist" else 0
    pick = pick_bonus(ident, st) if kind == "song" else 0.0
    own = 0.9 * math.log(1 + plays) + pick if m > 0.4 else 0.0
    return 3.0 * m + own + 0.8 / (1 + rank) + PRIOR.get(kind, 0.0)
