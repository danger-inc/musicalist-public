"""Freunde: eigener Code (16 Zeichen); wer ihn kennt, liest den geteilten Stand – sonst niemand.
Gleiches Protokoll wie Friends.kt (Handy): Thema/Schlüssel nur aus dem Code, Relay ntfy.sh sieht nur verschlüsselte Nachrichten.
Nachricht {"k":"prof","name","ts","now":{id,t,a}|null,"pl":bool,"recent":[…],"recs":[…]}.
Geteilt wird nur, wenn "friends_share" an ist (Default aus)."""
import base64
import hashlib
import json
import secrets
import socket
import threading
import time
import urllib.request

import engine

RELAY = "https://ntfy.sh"
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def norm(code):
    return "".join(c for c in (code or "").upper() if c in ALPHA)


def pretty(s):
    return "-".join(s[i:i + 4] for i in range(0, len(s), 4))


def _topic(sec):
    return "mfr-" + hashlib.sha256(f"musicalist-friend-topic|{sec}".encode()).hexdigest()[:24]


def _key(sec):
    return hashlib.sha256(f"musicalist-friend-key|{sec}".encode()).digest()


def _publish(sec, obj):
    from handy_sync import box
    body = base64.b64encode(box(_key(sec), json.dumps(obj, ensure_ascii=False).encode()))
    req = urllib.request.Request(f"{RELAY}/{_topic(sec)}", data=body, method="POST", headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def _open(sec, msg):
    from handy_sync import unbox
    try:
        return json.loads(unbox(_key(sec), base64.b64decode(msg)))
    except Exception:  # noqa: BLE001 – fremde/kaputte Nachricht
        return None


def entry(t):
    """engine-Titel → {id,t,a}."""
    return {"id": t["videoId"], "t": (t.get("title") or "?")[:70], "a": (t.get("artist") or "")[:50]}


def to_track(e, who=None):
    """Eintrag → engine-Titel (Quelle „freunde“)."""
    t = {"videoId": e["id"], "title": e.get("t") or "?", "artist": e.get("a") or "", "album": "", "duration": 0,
         "thumb": f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg", "artistId": None, "albumId": None}
    t["_src"] = ("freunde", who or "")
    return t


class Friends:
    def __init__(self, player):
        self.p = player
        self.listeners = []        # fn() nach neuem Abruf
        self.busy = False
        self.error = None
        self._gen = 0
        self._last_pub = 0.0
        self._cur_id = None
        self._playing = False
        self._cur = None
        self.friends = list(engine.setting("friends") or [])     # [{secret,name,prof,at}]
        self.recs = list(engine.setting("friends_recs") or [])
        self.recent = list(engine.setting("friends_recent") or [])
        player.listeners.append(self._on_player)
        threading.Thread(target=self._beat, daemon=True).start()

    # ----- eigene Einstellungen -----
    @property
    def share(self):
        v = engine.setting("friends_share")
        return True if v is None else bool(v)          # Default: an (Freunde sehen nur mit deinem Code etwas)

    @property
    def aliases(self):
        """Codes der eigenen gekoppelten Geräte (dev_id → Code): wer einen davon hat, sieht dieselbe Hörzeit."""
        return [v for v in (engine.setting("friends_alias") or {}).values() if isinstance(v, str) and len(v) == 16 and v != self.secret]

    LEVELS = ("minimal", "normal", "mehr")

    @property
    def level(self):
        v = engine.setting("friends_level")
        return v if v in self.LEVELS else "mehr"

    def set_level(self, v):
        """Umfang des Geteilten: minimal (läuft gerade, letzte 5, Stunden der Woche) · normal · mehr."""
        if v in self.LEVELS:
            engine.set_setting("friends_level", v)
            self._pf_at = 0
            self._touch(0)

    def set_share(self, on):
        engine.set_setting("friends_share", bool(on))
        if on:
            self._touch(0)
        else:
            self._retract()

    @property
    def name(self):
        return (engine.setting("friends_name") or "").strip() or (socket.gethostname().split(".")[0] or "pc").lower()

    def set_name(self, n):
        engine.set_setting("friends_name", (n or "").strip()[:24])
        self._touch(0)

    @property
    def secret(self):
        s = engine.setting("friends_secret")
        if not s:
            s = "".join(secrets.choice(ALPHA) for _ in range(16))
            engine.set_setting("friends_secret", s)
        return s

    def renew(self):
        self._retract()
        engine.set_setting("friends_secret", "".join(secrets.choice(ALPHA) for _ in range(16)))
        self._touch(0)

    # ----- veröffentlichen -----
    def _on_player(self, what):
        if what not in ("track", "state"):
            return
        p = self.p
        t = p.current
        pid = t["videoId"] if t else None
        playing = bool(t) and p.started and not p.paused
        changed = False
        if pid != self._cur_id:
            self._cur_id, self._cur, changed = pid, t, True
            if t and not str(pid).startswith("local:"):
                threading.Timer(5.0, self._played, args=(pid, t)).start()
        if playing != self._playing:
            self._playing, changed = playing, True
        if changed:
            self._touch()

    def _played(self, pid, t):
        """Nach 5 s echter Wiedergabe in „zuletzt gehört“."""
        if self._cur_id != pid or not self._playing:
            return
        self.recent = [{**entry(t), "at": int(time.time() * 1000)}] + [r for r in self.recent if r.get("id") != pid]
        self.recent = self.recent[:8]
        engine.set_setting("friends_recent", self.recent)
        self._touch()

    def _beat(self):
        while True:
            time.sleep(30)
            try:
                if self.share and self._playing and time.time() - self._last_pub > 180:
                    self._touch(0)
            except Exception:  # noqa: BLE001
                pass

    def profile(self):
        """Kurzes Hörprofil der Woche (höchstens alle 20 min neu gerechnet)."""
        now = time.time()
        if now - getattr(self, "_pf_at", 0) < 20 * 60 and hasattr(self, "_pf"):
            return self._pf
        self._pf_at = now
        try:
            import analyse
            r = analyse.analyse(self.p.journal.load() or [], "w", 0)
            if r.get("empty"):
                self._pf = None
            else:
                lv = self.level
                self._pf = {"h": round(r["base"]["secs"] / 360) / 10}
                if lv != "minimal":
                    na, nt = 5, 3
                    self._pf.update({"n": r["base"]["tracks"], "ar": r["base"]["artists"],
                            "art": [{"n": x["name"][:30], "m": round(x["secs"] / 60)} for x in r["artists"][:na]],
                            "trk": [{"t": x["t"][:40], "a": x["a"][:30], "n": x["plays"]} for x in r["tracks"][:nt]],
                            "pk": r.get("peak_hour", 0), "sk": round(r.get("skip_rate") or 0)})
                if lv == "mehr":         # die interessantesten weiteren Zahlen aus der Analyse (nur Zahlen/Kurzwörter, keine Titel)
                    self._pf.update({"ct": r.get("chronotype") or "", "dv": round(r.get("diversity") or 0),
                                     "t1": round(r.get("top1_share") or 0), "rs": round(r.get("repeat_share") or 0),
                                     "nw": len(r.get("new_artists") or [])})
                    if r.get("det_n"):
                        self._pf["cr"] = round(r.get("complete_rate") or 0)
                    if r.get("streak_now"):
                        self._pf["sn"] = int(r["streak_now"])
        except Exception as e:  # noqa: BLE001
            engine.log(f"freunde: profil {e!r}")
            self._pf = None
        return self._pf

    def _payload(self):
        """Genau das sehen Freunde von dir."""
        t = self._cur
        now = entry(t) if t and not str(t["videoId"]).startswith("local:") else None
        lv = self.level
        o = {"k": "prof", "v": 1, "name": self.name, "ts": int(time.time()), "now": now, "pl": bool(now and self._playing),
             "recent": [{k: r[k] for k in ("id", "t", "a")} for r in self.recent[:5]],
             "recs": [] if lv == "minimal" else [{k: r[k] for k in ("id", "t", "a")} for r in self.recs[:6]]}
        pf = self.profile()
        if pf:
            o["pf"] = pf
        size = lambda: len(json.dumps(o, ensure_ascii=False))
        if size() > 2500:                       # Nachrichten sind auf 4 kB begrenzt: erst Empfehlungen, dann „zuletzt“, zuletzt das Profil kürzen
            o["recs"] = o["recs"][:3]
        if size() > 2500:
            o["recent"] = o["recent"][:5]
        if size() > 2500:
            o.pop("pf", None)
        if size() > 2500:
            o["recent"] = o["recent"][:2]
        return o

    def _touch(self, delay=None):
        """Im Hintergrund veröffentlichen, höchstens alle 4 s, am Ende immer der letzte Stand."""
        if not self.share:
            return
        wait = 0 if delay == 0 else max(0.3, 4.0 - (time.time() - self._last_pub))
        self._gen += 1
        gen = self._gen

        def run():
            if wait:
                time.sleep(wait)
            if gen != self._gen:
                return
            self._last_pub = time.time()
            try:
                o = self._payload()
            except Exception as e:  # noqa: BLE001
                engine.log(f"freunde: payload {e!r}")
                return
            for sec in [self.secret] + self.aliases:       # gekoppelte Geräte (Handy/Laptop) = eine Person: Stand in alle Themen
                try:
                    _publish(sec, o)
                except Exception as e:  # noqa: BLE001
                    engine.log(f"freunde: senden {e!r}")
        threading.Thread(target=run, daemon=True).start()

    def _retract(self):
        sec = self.secret

        def run():
            try:
                _publish(sec, {"k": "prof", "v": 1, "name": self.name, "ts": int(time.time()), "now": None, "pl": False,
                               "recent": [], "recs": []})
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=run, daemon=True).start()

    # ----- Empfehlungen -----
    def recommend(self, t):
        if str(t.get("videoId", "")).startswith("local:"):
            return False
        self.recs = [{**entry(t), "at": int(time.time() * 1000)}] + [r for r in self.recs if r.get("id") != t["videoId"]]
        self.recs = self.recs[:12]
        engine.set_setting("friends_recs", self.recs)
        self._touch(0)
        return True

    def send_to(self, f, t):
        """Direkt an einen Freund (Nachricht in SEIN Thema, mit seinem Schlüssel)."""
        if str(t.get("videoId", "")).startswith("local:"):
            return False
        msg = {"k": "rec", "from": self.name, "ts": int(time.time()), "t": entry(t)}

        def run():
            try:
                _publish(f["secret"], msg)
            except Exception as e:  # noqa: BLE001
                engine.log(f"freunde: empfehlen {e!r}")
        threading.Thread(target=run, daemon=True).start()
        return True

    @property
    def inbox(self):
        return list(engine.setting("friends_inbox") or [])

    def dismiss(self, i):
        box = self.inbox
        if 0 <= i < len(box):
            box.pop(i)
            engine.set_setting("friends_inbox", box)

    def poll_inbox(self):
        """Eigenes Thema nach direkt geschickten Empfehlungen absuchen → Anzahl neuer."""
        sec = self.secret
        seen = list(engine.setting("friends_inbox_seen") or [])
        fresh = []
        added = []
        try:
            with urllib.request.urlopen(f"{RELAY}/{_topic(sec)}/json?poll=1&since=all", timeout=12) as r:
                for line in r.read().decode("utf-8", "replace").splitlines():
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("event") != "message" or e.get("id") in seen:
                        continue
                    m = _open(sec, e.get("message", ""))
                    if m and m.get("k") == "friend":                    # jemand hat meinen Code hinzugefügt → auch mein Freund
                        seen.append(e.get("id"))
                        fs, ts = norm(m.get("secret")), int(e.get("time") or 0) * 1000
                        if len(fs) == 16 and fs != sec and not any(f["secret"] == fs for f in self.friends) and self.gone.get(fs, 0) < ts:
                            self.friends.append({"secret": fs, "name": str(m.get("name") or "freund")[:24] or "freund", "prof": None, "at": 0, "t": ts})
                            self._save()
                            added.append(str(m.get("name") or "jemand"))
                        continue
                    if not m or m.get("k") != "rec" or not isinstance(m.get("t"), dict):
                        continue
                    seen.append(e.get("id"))
                    fresh.append({**{k: m["t"].get(k, "") for k in ("id", "t", "a")}, "from": str(m.get("from") or "freund")[:24],
                                  "at": int(e.get("time") or 0) * 1000})
        except Exception:  # noqa: BLE001
            return 0
        engine.set_setting("friends_inbox_seen", seen[-80:])
        if fresh:
            engine.set_setting("friends_inbox", (fresh + self.inbox)[:30])
        if added and getattr(self, "say", None):
            self.say(f"{', '.join(added)} hat dich hinzugefügt – ihr seid jetzt befreundet")
        return len(fresh)

    def unrecommend(self, vid):
        self.recs = [r for r in self.recs if r.get("id") != vid]
        engine.set_setting("friends_recs", self.recs)
        self._touch(0)

    # ----- Freunde -----
    def _save(self):
        engine.set_setting("friends", self.friends)

    @staticmethod
    def live(f):
        pr = f.get("prof") or {}
        return bool(pr.get("now") and pr.get("pl") and f.get("at") and time.time() * 1000 - f["at"] < 6 * 60_000)

    def fetch(self, sec):
        """Letzten Stand holen → (prof|None, at_ms). Wirft bei Netzfehlern."""
        last, at = None, 0
        with urllib.request.urlopen(f"{RELAY}/{_topic(sec)}/json?poll=1&since=all", timeout=12) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") != "message":
                    continue
                m = _open(sec, e.get("message", ""))
                if not m or m.get("k") != "prof":
                    continue
                tm = int(e.get("time") or 0) * 1000
                if tm >= at:
                    last, at = m, tm
        return last, at

    # ----- Abgleich mit dem Handy (über handy_sync) -----
    @property
    def gone(self):
        return dict(engine.setting("friends_gone") or {})

    def sync_out(self):
        return {"me": self.secret, "rc": [{**{k: r[k] for k in ("id", "t", "a")}, "at": r.get("at", 0)} for r in self.recent[:8]], "f": [{"s": f["secret"], "n": f.get("name") or "freund", "t": int(f.get("t") or 1)} for f in self.friends], "g": self.gone}

    def sync_in(self, o, dev="handy"):
        """Freunde vom Handy übernehmen (Vereinigung; bei Streit gewinnt der spätere Zeitpunkt). Dazu: eigener Code
        und „zuletzt gehört“ des gekoppelten Geräts → beide Geräte zeigen Freunden dieselbe Person."""
        gone = self.gone
        changed = False
        me = norm(o.get("me"))
        if len(me) == 16 and me != self.secret:
            al = dict(engine.setting("friends_alias") or {})
            if al.get(dev) != me:
                al[dev] = me
                engine.set_setting("friends_alias", al)
                changed = True
            if any(f["secret"] == me for f in self.friends):
                self.friends = [f for f in self.friends if f["secret"] != me]
                changed = True
        rc = [{"id": str(r.get("id")), "t": str(r.get("t") or "?")[:70], "a": str(r.get("a") or "")[:50], "at": int(r.get("at") or 0)}
              for r in (o.get("rc") or []) if isinstance(r, dict) and r.get("id")]
        if rc:
            seen = {}
            for r in rc + self.recent:
                if r["id"] not in seen or r.get("at", 0) > seen[r["id"]].get("at", 0):
                    seen[r["id"]] = r
            merged = sorted(seen.values(), key=lambda r: -(r.get("at") or 0))[:8]
            if [r["id"] for r in merged] != [r["id"] for r in self.recent]:
                self.recent = merged
                engine.set_setting("friends_recent", merged)
                changed = True
                self._touch()
        for sec, ts in (o.get("g") or {}).items():
            ts = int(ts)
            mine = next((f for f in self.friends if f["secret"] == sec), None)
            if (int(mine.get("t") or 0) if mine else 0) < ts:
                if mine:
                    self.friends = [f for f in self.friends if f["secret"] != sec]
                    changed = True
                if gone.get(sec, 0) < ts:
                    gone[sec] = ts
                    changed = True
        for x in o.get("f") or []:
            sec, t = norm(x.get("s")), int(x.get("t") or 1)
            if len(sec) != 16 or sec == self.secret or sec in self.aliases or gone.get(sec, 0) >= t:
                continue
            if not any(f["secret"] == sec for f in self.friends):
                self.friends.append({"secret": sec, "name": str(x.get("n") or "freund")[:24], "prof": None, "at": 0, "t": t})
                changed = True
        if changed:
            engine.set_setting("friends_gone", gone)
            self._save()
            for fn in list(self.listeners):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass

    def _hello(self, sec):
        """Beidseitig: wer deinen Code hinzufügt, meldet sich in DEINEM Thema und wird dort automatisch auch dein Freund."""
        msg = {"k": "friend", "name": self.name, "secret": self.secret, "ts": int(time.time())}

        def run():
            try:
                _publish(sec, msg)
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=run, daemon=True).start()

    def add(self, code):
        """Blockierend. Gibt den Namen zurück."""
        sec = norm(code)
        if len(sec) != 16:
            raise ValueError("der code hat 16 zeichen (buchstaben und ziffern)")
        if sec == self.secret:
            raise ValueError("das ist dein eigener code")
        if any(f["secret"] == sec for f in self.friends):
            raise ValueError("schon in deiner liste")
        prof, at = self.fetch(sec)
        f = {"secret": sec, "name": (prof or {}).get("name") or "freund", "prof": prof, "at": at, "t": int(time.time() * 1000)}
        self.friends.append(f)
        gone = self.gone
        if gone.pop(sec, None) is not None:
            engine.set_setting("friends_gone", gone)
        self._save()
        self._hello(sec)
        return f["name"]

    def remove(self, sec):
        self.friends = [f for f in self.friends if f["secret"] != sec]
        gone = self.gone
        gone[sec] = int(time.time() * 1000)
        engine.set_setting("friends_gone", gone)
        self._save()

    def refresh(self):
        """Blockierend: alle Freunde parallel abfragen."""
        if self.busy:
            return
        self.busy = True
        try:
            n = self.poll_inbox()
            if n and getattr(self, "notify", None):
                self.notify(n)
            if not self.friends:
                return
            snap = list(self.friends)
            out = {}

            def one(f):
                try:
                    prof, at = self.fetch(f["secret"])
                    if prof is not None:
                        out[f["secret"]] = {"secret": f["secret"], "name": prof.get("name") or f["name"], "prof": prof, "at": at,
                                            "error": None}
                    else:
                        out[f["secret"]] = {**f, "error": None}
                except Exception as e:  # noqa: BLE001
                    out[f["secret"]] = {**f, "error": str(e)[:60]}
            ths = [threading.Thread(target=one, args=(f,)) for f in snap]
            for t in ths:
                t.start()
            for t in ths:
                t.join(20)
            self.friends = [out.get(f["secret"], f) for f in self.friends]
            self._save()
        finally:
            self.busy = False
