"""Gemeinsame Playlists: Wer den Code kennt, kann Titel hinzufügen und entfernen (Freund·innen schicken ihn sich).
Läuft wie die Freunde-Chats über das Relay: Thema mpl-… und Schlüssel aus dem Code, Inhalt verschlüsselt (handy_sync.box).
Jede Änderung ist eine Nachricht {k: meta|add|del, …}; der Stand entsteht durch Nachspielen aller Nachrichten.
Der Server hält mpl-Themen 365 Tage (wie Namen). Gleiches Protokoll in der Handy-App (SharedLists.kt)."""
import base64
import hashlib
import json
import secrets
import time
import urllib.request

import engine
import friends

ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def topic(code):
    return "mpl-" + hashlib.sha256(f"musicalist-playlist-topic|{code}".encode()).hexdigest()[:24]


def key(code):
    return hashlib.sha256(f"musicalist-playlist-key|{code}".encode()).digest()


def norm(code):
    return "".join(ch for ch in (code or "").upper() if ch in ALPHA)


def mine():
    """[{code, name}] – die Listen, bei denen ich mitmache (lokal gemerkt)."""
    return [x for x in (engine.setting("shared_lists") or []) if isinstance(x, dict) and x.get("code")]


def _remember(code, name):
    ls = [x for x in mine() if x["code"] != code] + [{"code": code, "name": name}]
    engine.set_setting("shared_lists", ls)


def forget(code):
    engine.set_setting("shared_lists", [x for x in mine() if x["code"] != code])


def publish(code, obj):
    from handy_sync import box
    body = base64.b64encode(box(key(code), json.dumps(obj, ensure_ascii=False).encode()))
    req = urllib.request.Request(f"{friends.RELAY}/{topic(code)}", data=body, method="POST", headers={"Content-Type": "text/plain"})
    with friends.relay_open(req, timeout=12) as r:
        r.read()


def replay(msgs):
    """Nachrichten (in Reihenfolge) → (name, [titel …]); Titel: {videoId,title,artist,thumb,by}. Reine Rechnung."""
    name, items = "", {}
    for m in msgs:
        k = m.get("k")
        if k == "meta" and m.get("name"):
            name = str(m["name"])[:60]
        elif k == "add" and len(m.get("id") or "") == 11 and m["id"] not in items:
            items[m["id"]] = {"videoId": m["id"], "title": m.get("t") or "?", "artist": m.get("a") or "", "by": m.get("by") or "", "duration": 0,
                              "thumb": f"https://i.ytimg.com/vi/{m['id']}/hqdefault.jpg"}
        elif k == "del":
            items.pop(m.get("id"), None)
    return name, list(items.values())


def load(code):
    """Stand vom Relay holen → (name, titel)."""
    from handy_sync import unbox
    with friends.relay_open(f"{friends.RELAY}/{topic(code)}/json?poll=1&since=all", timeout=12) as r:
        raw = r.read().decode("utf-8", "replace")
    msgs = []
    for line in raw.splitlines():
        try:
            e = json.loads(line)
            if e.get("event") == "message":
                msgs.append(json.loads(unbox(key(code), base64.b64decode(e["message"]))))
        except (ValueError, KeyError, TypeError):
            continue                                # fremde/kaputte Nachricht: überspringen
    name, items = replay(msgs)
    if name:
        _remember(code, name)
    return name, items


def create(name, me):
    code = "".join(secrets.choice(ALPHA) for _ in range(10))
    publish(code, {"k": "meta", "name": name.strip()[:60] or "gemeinsame playlist", "by": me, "ts": int(time.time())})
    _remember(code, name.strip()[:60] or "gemeinsame playlist")
    return code


def join(code):
    code = norm(code)
    if len(code) != 10:
        raise ValueError("der code hat 10 zeichen")
    name, _items = load(code)
    if not name:
        raise ValueError("keine playlist mit diesem code gefunden")
    return code, name


def add(code, t, me):
    publish(code, {"k": "add", "id": t["videoId"], "t": t.get("title") or "", "a": t.get("artist") or "", "by": me, "ts": int(time.time())})


def remove(code, vid, me):
    publish(code, {"k": "del", "id": vid, "by": me, "ts": int(time.time())})


if __name__ == "__main__":       # Selbsttest der Rechnung
    n, it = replay([{"k": "meta", "name": "Party"}, {"k": "add", "id": "a" * 11, "t": "Eins", "by": "x"},
                    {"k": "add", "id": "b" * 11, "t": "Zwei"}, {"k": "add", "id": "a" * 11, "t": "doppelt"}, {"k": "del", "id": "b" * 11}])
    assert n == "Party" and [x["title"] for x in it] == ["Eins"], (n, it)
    assert norm("abc-def ghjk") == "ABCDEFGHJK"
    print("ok")
