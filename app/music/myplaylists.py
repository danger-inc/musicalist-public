"""Welche Titel stehen in meinen Playlists? Für die Suche: diese Titel zuerst (auch wenn YouTube sie nicht liefert),
eigene Playlists als Treffer. Aus den Bibliothek-Playlists gebaut, höchstens alle 6 h neu (DATA/playlist-index.json).
Gleich wie MyPlaylists.kt in der Handy-App."""
import json
import os
import threading
import time

import engine
import searchrank

FILE = os.path.join(engine.DATA, "playlist-index.json")
_lock = threading.Lock()
by_id = {}          # videoId → {"t": track, "l": [playlistnamen]}
lists = []          # [{"id", "title"}] meiner Playlists
_at = 0


def load():
    global by_id, lists, _at
    if by_id or lists:
        return
    try:
        with open(FILE, encoding="utf-8") as f:
            o = json.load(f)
        by_id, lists, _at = o.get("t") or {}, o.get("lists") or [], o.get("at") or 0
    except (OSError, ValueError):
        pass


def refresh(music, force=False):
    """Blockierend (Netz). Ohne Anmeldung passiert nichts (library() wirft dann)."""
    global by_id, lists, _at
    with _lock:
        load()
        if not force and time.time() - _at < 6 * 3600:
            return
        try:
            pls = [p for p in music.library() if p["id"] not in ("LM", "SE")][:40]
        except Exception:  # noqa: BLE001
            return
        out = {}
        for p in pls:
            try:
                tracks = music.playlist(p["id"])[1]
            except Exception:  # noqa: BLE001
                continue
            for t in tracks:
                e = out.setdefault(t["videoId"], {"t": {k: t.get(k) for k in ("videoId", "title", "artist", "artistId", "album", "albumId", "duration", "thumb")}, "l": []})
                if p["title"] not in e["l"]:
                    e["l"].append(p["title"])
        by_id, lists, _at = out, [{"id": p["id"], "title": p["title"]} for p in pls], time.time()
        try:
            with open(FILE, "w", encoding="utf-8") as f:
                json.dump({"at": _at, "t": by_id, "lists": lists}, f, ensure_ascii=False)
        except OSError:
            pass


def matches(q, n=15):
    """Titel aus meinen Playlists, deren Name/Künstler·in zur Suche passt (beste zuerst)."""
    hits = [(searchrank.name_match(q, e["t"]["title"], e["t"].get("artist") or ""), e["t"]) for e in by_id.values()]
    return [t for m, t in sorted((h for h in hits if h[0] >= 0.45), key=lambda h: -h[0])[:n]]


def playlist_hits(q):
    return [p for p in lists if searchrank.name_match(q, p["title"]) >= 0.45]
