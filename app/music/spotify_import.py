"""Spotify-Datenexport (DSGVO-Auskunft, ZIP/Ordner/JSON) → Playlists in YouTube Music.
Liest Playlist*.json (+ YourLibrary.json = gespeicherte Titel), sucht jeden Titel in YT Music, legt je Playlist eine
private Playlist an (gibt es schon eine mit gleichem Namen, werden nur fehlende Titel ergänzt). Treffer werden in
DATA/spotify_match.json gemerkt: abgebrochene/wiederholte Läufe fangen nicht von vorn an."""
import io
import json
import os
import re
import threading
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor

import engine

SAVED = "Spotify · gespeicherte Titel"
MATCH_FILE = os.path.join(engine.DATA, "spotify_match.json")
MISSING_FILE = os.path.join(engine.DATA, "spotify_nicht_gefunden.txt")


def _json_files(path):
    """[(name, bytes)] aller .json-Dateien aus ZIP, Ordner oder einer einzelnen JSON-Datei."""
    out = []
    if os.path.isdir(path):
        for root, _d, files in os.walk(path):
            for f in files:
                if f.lower().endswith(".json"):
                    with open(os.path.join(root, f), "rb") as fh:
                        out.append((f, fh.read()))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith(".json") and not n.endswith("/"):
                    out.append((os.path.basename(n), z.read(n)))
    else:
        with open(path, "rb") as fh:
            out.append((os.path.basename(path), fh.read()))
    return out


def parse(path):
    """→ [{"name", "tracks": [{"t","a","al","uri"}]}]; Episoden/lokale Dateien werden übersprungen."""
    pls, saved = [], []
    for name, raw in _json_files(path):
        try:
            d = json.loads(raw.decode("utf-8-sig"))
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("playlists"), list):
            for p in d["playlists"]:
                tr = []
                for it in p.get("items") or []:
                    x = (it or {}).get("track")
                    if x and x.get("trackName"):
                        tr.append({"t": x["trackName"], "a": x.get("artistName") or "", "al": x.get("albumName") or "",
                                   "uri": x.get("trackUri") or ""})
                if tr:
                    pls.append({"name": (p.get("name") or "Spotify").strip() or "Spotify", "tracks": tr})
        elif isinstance(d, dict) and isinstance(d.get("tracks"), list) and name.lower().startswith("yourlibrary"):
            for x in d["tracks"]:
                if x.get("track"):
                    saved.append({"t": x["track"], "a": x.get("artist") or "", "al": x.get("album") or "", "uri": x.get("uri") or ""})
    if saved:
        pls.append({"name": SAVED, "tracks": saved})
    return pls


# ----- Abgleich -----
_NOISE = re.compile(r"\(.*?\)|\[.*?\]|\s-\s.*$|feat\.?.*$|ft\.?.*$|remaster(ed)?|\d{4}", re.I)


def norm(s, strip=True):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    if strip:
        s = _NOISE.sub(" ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _score(want_t, want_a, c):
    ct = norm(c.get("title"))
    arts = " ".join(norm(a.get("name", ""), False) for a in (c.get("artists") or []))
    wt, wa = norm(want_t), norm(want_a, False)
    if not ct or not wt:
        return 0
    if ct == wt:
        s = 3
    elif ct.startswith(wt) or wt.startswith(ct) or wt in ct or ct in wt:
        s = 2
    else:
        return 0
    if wa and (wa in arts or any(p and p in wa for p in arts.split())):
        s += 2
    elif wa:
        return 0 if s < 3 else 1         # richtiger Titel, falscher Künstler: nur als Notlösung
    return s


def find(music, t):
    """Beste Video-ID in YT Music zu einem Spotify-Titel oder None."""
    for q in (f"{t['t']} {t['a']}".strip(), t["t"]):
        try:
            res = music.yt.search(q, filter="songs", limit=6)
        except Exception:  # noqa: BLE001
            continue
        best = max(res, key=lambda c: _score(t["t"], t["a"], c), default=None)
        if best and _score(t["t"], t["a"], best) >= 4 and best.get("videoId"):
            return best["videoId"]
    return None


def _load_cache():
    try:
        with open(MATCH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def run(music, playlists, progress, cancel=None):
    """playlists: parse()-Auswahl. progress(done, total, text). → Bericht {"made","tracks","missing":[…],"errors":[…]}.
    Blockierend – in einem Thread aufrufen."""
    cache = _load_cache()
    lock = threading.Lock()
    uniq = {}
    for p in playlists:
        for t in p["tracks"]:
            uniq.setdefault(t["uri"] or f"{t['a']}|{t['t']}", t)
    todo = [(k, t) for k, t in uniq.items() if k not in cache]
    total, done = len(uniq), len(uniq) - len(todo)
    progress(done, total, "suche titel …")

    def work(kt):
        nonlocal done
        k, t = kt
        if cancel and cancel.is_set():
            return
        vid = find(music, t)
        with lock:
            cache[k] = vid or ""
            done += 1
            if done % 25 == 0:
                try:
                    with open(MATCH_FILE, "w", encoding="utf-8") as f:
                        json.dump(cache, f)
                except OSError:
                    pass
        progress(done, total, f"{done}/{total} gesucht")
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(work, todo))
    try:
        with open(MATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        pass
    rep = {"made": 0, "tracks": 0, "missing": [], "errors": []}
    if cancel and cancel.is_set():
        rep["errors"].append("abgebrochen (gefundene Titel sind gemerkt)")
        return rep
    have = {}
    try:
        have = {p["title"].strip(): p["id"] for p in music.editable_playlists()}
    except Exception:  # noqa: BLE001
        pass
    for p in playlists:
        vids, seen = [], set()
        for t in p["tracks"]:
            v = cache.get(t["uri"] or f"{t['a']}|{t['t']}")
            if v:
                if v not in seen:
                    seen.add(v)
                    vids.append(v)
            else:
                rep["missing"].append(f"{p['name']}: {t['a']} – {t['t']}")
        if not vids:
            continue
        progress(total, total, f"lege „{p['name']}“ an …")
        try:
            if p["name"] in have:
                music.add_to_playlist(have[p["name"]], vids)
            else:
                pid = music.yt.create_playlist(p["name"], "von Spotify importiert", privacy_status="PRIVATE", video_ids=vids[:100])
                if not isinstance(pid, str):
                    raise RuntimeError(str(pid)[:120])
                for i in range(100, len(vids), 100):
                    music.yt.add_playlist_items(pid, vids[i:i + 100], duplicates=True)
            rep["made"] += 1
            rep["tracks"] += len(vids)
        except Exception as e:  # noqa: BLE001
            rep["errors"].append(f"{p['name']}: {engine.explain(e) if hasattr(engine, 'explain') else e}")
    if rep["missing"]:
        try:
            with open(MISSING_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(rep["missing"]) + "\n")
        except OSError:
            pass
    return rep
