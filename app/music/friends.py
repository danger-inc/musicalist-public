"""Freunde: eigener Code (16 Zeichen); wer ihn kennt, liest den geteilten Stand – sonst niemand.
Gleiches Protokoll wie Friends.kt (Handy): Thema/Schlüssel nur aus dem Code, Relay ntfy.sh sieht nur verschlüsselte Nachrichten.
Nachricht {"k":"prof","name","ts","now":{id,t,a}|null,"pl":bool,"recent":[…],"recs":[…]}.
Geteilt wird nur, wenn "friends_share" an ist (Default aus)."""
import base64
import hashlib
import json
import re
import secrets
import socket
import threading
import time
import urllib.request

import engine
import localmusic

RELAY = "https://ntfy.sh"
NTFY = "https://ntfy.sh"


def relay_open(target, timeout=12):
    """urlopen für Relay-Aufrufe: geht der eigene Server nicht (Fehler, 429, offline), fällt es auf ntfy.sh zurück (gleiches Protokoll)."""
    try:
        return urllib.request.urlopen(target, timeout=timeout)
    except (urllib.error.URLError, OSError):
        if RELAY.rstrip("/") == NTFY:
            raise
        url = target.full_url if isinstance(target, urllib.request.Request) else target
        if not url.startswith(RELAY):
            raise
        new = NTFY + url[len(RELAY):]
        if isinstance(target, urllib.request.Request):
            new = urllib.request.Request(new, data=target.data, method=target.get_method(), headers=dict(target.header_items()))
        return urllib.request.urlopen(new, timeout=timeout)
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def norm(code):
    return "".join(c for c in (code or "").upper() if c in ALPHA)


def pretty(s):
    return "-".join(s[i:i + 4] for i in range(0, len(s), 4))


def _topic(sec):
    return "mfr-" + hashlib.sha256(f"musicalist-friend-topic|{sec}".encode()).hexdigest()[:24]


def _key(sec):
    return hashlib.sha256(f"musicalist-friend-key|{sec}".encode()).digest()


# ---------- Nutzername: Namens-Thema (öffentlich, nur Anspruch + Anfragen) ----------
NAME_OK = re.compile(r"^[a-z0-9._-]{3,20}$")


def uname_of(n):
    """Name → Kleinschreibung ohne Sonderzeichen (so wird verglichen und gefunden)."""
    return re.sub(r"[^a-z0-9._-]", "", str(n or "").strip().lower())[:20]


def _ntopic(un):
    return "mfn-" + hashlib.sha256(f"musicalist-friend-name|{un}".encode()).hexdigest()[:24]


def _retry(make, tries=4):
    """HTTP-Aufruf mit Wiederholung: ntfy.sh antwortet bei Überlast/Rate-Limit mit 429/5xx (oft nur kurz) – dann
    warten (Retry-After, höchstens 6 s) und neu versuchen. Wirft zuletzt den echten Fehler."""
    import urllib.error
    last = None
    for i in range(tries):
        try:
            return make()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                break
            try:
                w = float(e.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                w = 0
            time.sleep(min(max(w, 1.0 + i * 1.5), 6.0))
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(1.0 + i)
    raise last


def why(e):
    """Verständlicher Grund für das Scheitern einer Relay-Anfrage."""
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429:
            return "der Server ist gerade überlastet (zu viele Anfragen) – bitte in einer Minute nochmal"
        return f"der Server antwortet mit Fehler {e.code} – bitte später nochmal"
    return "keine verbindung zum internet/Server – bitte später nochmal"


def _post_plain(topic, obj):
    def go():
        req = urllib.request.Request(f"{RELAY}/{topic}", data=json.dumps(obj, ensure_ascii=False).encode(), method="POST",
                                     headers={"Content-Type": "text/plain"})
        return relay_open(req, timeout=12).read()
    _retry(go)


def _read_plain(topic):
    """Alle lesbaren JSON-Nachrichten eines Namens-Themas → [(ntfy-Ereignis, Nachricht)]."""
    out = []
    def go():
        with relay_open(f"{RELAY}/{topic}/json?poll=1&since=all", timeout=12) as r:
            return r.read().decode("utf-8", "replace")
    if True:
        for line in _retry(go).splitlines():
            try:
                e = json.loads(line)
                m = json.loads(e.get("message", "")) if e.get("event") == "message" else None
            except ValueError:
                continue
            if isinstance(m, dict):
                out.append((e, m))
    return out


def _dh():
    from handy_sync import P, G, _int_bytes
    return P, G, _int_bytes


def inc_active(v):
    """Incognito-Angabe eines Profils: 1 = bis zum Ausschalten, sonst Ende (Unix-Sekunden)."""
    try:
        v = int(v or 0)
    except (TypeError, ValueError):
        return False
    return v == 1 or v > time.time()


def pick_state(per):
    """per: {gerät: (nachricht, zeit_ms)} → (nachricht|None, zeit_ms). Incognito irgendeines Geräts gilt für alle;
    sonst gewinnt das Gerät, auf dem gerade (vor < 6 min) Musik läuft; sonst die neueste Nachricht."""
    if not per:
        return None, 0
    now = time.time() * 1000
    items = list(per.values())
    inc = [x for x in items if inc_active(x[0].get("inc"))]
    if inc:
        return max(inc, key=lambda x: x[1])
    live = [x for x in items if x[0].get("now") and x[0].get("pl") and now - x[1] < 6 * 60_000]
    if live:
        return max(live, key=lambda x: x[1])
    return max(items, key=lambda x: x[1])


def fid(sec):
    """Kennung des Absenders (aus seinem Code, verrät ihn nicht): damit ordnet der Empfänger Nachrichten dem Freund zu."""
    return hashlib.sha256(f"musicalist-friend-id|{sec}".encode()).hexdigest()[:12]


def _publish(sec, obj):
    from handy_sync import box
    body = base64.b64encode(box(_key(sec), json.dumps(obj, ensure_ascii=False).encode()))
    hdr = {"Content-Type": "text/plain"}
    if isinstance(obj, dict) and obj.get("k") == "prof":
        hdr["X-Tags"] = "prof"          # Status-Meldung: der Server behält je Thema nur die neuesten (Chats nie gekürzt); ntfy.sh ignoriert es
    req = urllib.request.Request(f"{RELAY}/{_topic(sec)}", data=body, method="POST", headers=hdr)
    with relay_open(req, timeout=10) as r:
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


def is_album(e):
    """Album („alb:“) oder Playlist („pl:“) als Empfehlung – wird als Sammlungs-Zeile gezeigt."""
    i = str((e or {}).get("id", ""))
    return i.startswith("alb:") or i.startswith("pl:")


def album_artist(alb):
    ars = [x["name"] for x in alb.get("artists") or [] if x.get("name")]
    return ", ".join(ars) or alb.get("artist") or ""


def album_entry(alb):
    """Album (ytmusicapi-Treffer) → {id:"alb:<browseId>", t, a, th}. Ältere Versionen zeigen es als Titel ohne Ton."""
    th = alb.get("thumb") or ((alb.get("thumbnails") or [{}])[-1].get("url") if alb.get("thumbnails") else "") or ""
    return {"id": "alb:" + str(alb.get("browseId")), "t": (alb.get("title") or "?")[:70], "a": album_artist(alb)[:50], "th": th}


def to_track(e, who=None):
    """Eintrag → engine-Titel (Quelle „freunde“)."""
    t = {"videoId": e["id"], "title": e.get("t") or "?", "artist": e.get("a") or "", "album": "", "duration": 0,
         "thumb": f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg", "artistId": None, "albumId": None}
    if localmusic.is_pod(e["id"]) and e.get("pu"):        # Handy-Podcast: Adresse merken, dann spielt er wie lokal
        urls = dict(engine.setting("pod_urls") or {})
        if urls.get(e["id"]) != e["pu"]:
            urls[e["id"]] = e["pu"]
            engine.set_setting("pod_urls", dict(list(urls.items())[-300:]))
        t.update(thumb=e.get("th") or "", album=e.get("pn") or "")
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
        self._chat_lock = threading.Lock()
        self.friends = list(engine.setting("friends") or [])     # [{secret,name,prof,at}]
        self.recs = list(engine.setting("friends_recs") or [])
        self.recent = list(engine.setting("friends_recent") or [])
        player.listeners.append(self._on_player)
        try:
            import recap
            self.recaps = recap.Recaps(self)          # Rückblick-Bilder (Woche/Monat/Jahr)
        except Exception as e:  # noqa: BLE001
            engine.log(f"rückblick: {e!r}")
            self.recaps = None
        threading.Thread(target=self._beat, daemon=True).start()

    # ----- eigene Einstellungen -----
    @property
    def share(self):
        v = engine.setting("friends_share")
        return True if v is None else bool(v)          # Default: an (Freunde sehen nur mit deinem Code etwas)

    @property
    def aliases(self):
        """Codes der eigenen gekoppelten Geräte (dev_id → Code): wer einen davon hat, sieht dieselbe Hörzeit."""
        out = [v for v in (engine.setting("friends_alias") or {}).values() if isinstance(v, str) and len(v) == 16 and v != self.secret]
        for d in (engine.setting("acct_devs") or {}).values():          # alle weiteren Geräte des Kontos
            s = d.get("sec") if isinstance(d, dict) else None
            if isinstance(s, str) and len(s) == 16 and s != self.secret and s not in out:
                out.append(s)
        return out

    def devices_changed(self):
        """Nach dem Abgleich der Geräteliste: eigene Geräte-Codes gehören nicht in die Freundesliste."""
        own = set(self.aliases)
        if own and any(x["secret"] in own for x in self.friends):
            self.friends = [x for x in self.friends if x["secret"] not in own]
            self._save()

    @property
    def inc_until(self):
        """0 = aus, 1 = bis zum Ausschalten, sonst Ende (Unix-Sekunden)."""
        v = int(engine.setting("friends_inc") or 0)
        return v if (v == 1 or v > time.time()) else 0

    @property
    def incognito(self):
        return self.inc_until != 0

    def set_incognito(self, minutes):
        """minutes: None = aus, 0 = bis ich es ausschalte, sonst so viele Minuten."""
        until = 0 if minutes is None else (1 if minutes == 0 else int(time.time()) + minutes * 60)
        engine.set_setting("friends_inc", until)
        self._pf_at = 0
        self._touch(0)
        if until > 1:
            def end():
                if int(engine.setting("friends_inc") or 0) == until:
                    engine.set_setting("friends_inc", 0)
                    self._touch(0)
                    for fn in list(self.listeners):
                        fn()
            t = threading.Timer(minutes * 60 + 1.5, end)
            t.daemon = True
            t.start()

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

    # ----- Nutzername (Pflicht) und Freundschaftsanfragen per Name -----
    @property
    def uname(self):
        return engine.setting("friends_uname") or ""

    @property
    def named(self):
        return bool(self.uname)

    @property
    def uid(self):
        return engine.setting("friends_uid") or ""

    def _pk(self):
        P, G, _ib = _dh()
        return pow(G, int(engine.setting("friends_nk"), 16), P)

    def name_state(self, display, uid=None):
        """('ok' | 'taken' | 'bad', normierter Name). Blockierend (Netz)."""
        un = uname_of(display)
        if not NAME_OK.match(un):
            return "bad", un
        uid = uid or self.uid
        taken = any(m.get("k") == "claim" and m.get("uid") and m.get("uid") != uid for _e, m in _read_plain(_ntopic(un)))
        return ("taken" if taken else "ok"), un

    def set_username(self, display):
        """Nutzernamen festlegen/ändern (blockierend). Wirft ValueError mit verständlichem Text."""
        display = (display or "").strip()[:20]
        uid = self.uid or secrets.token_hex(6)
        try:
            st, un = self.name_state(display, uid)
        except Exception as e:  # noqa: BLE001
            raise ValueError(why(e)) from e
        if st == "bad":
            raise ValueError("3–20 zeichen: kleine/große buchstaben, ziffern, . _ -")
        if st == "taken":
            raise ValueError("dieser name ist schon vergeben")
        engine.set_setting("friends_uid", uid)
        if not engine.setting("friends_nk"):
            engine.set_setting("friends_nk", secrets.token_hex(32))
        engine.set_setting("friends_uname", un)
        engine.set_setting("friends_name", display)
        engine.set_setting("friends_name_t", int(time.time() * 1000))
        try:
            self._claim()
        except Exception as e:  # noqa: BLE001
            engine.log(f"freunde: anspruch {e!r}")
        self._touch(0)

    def _claim(self):
        """Namen im Namens-Thema anmelden (wird alle paar Stunden erneuert, das Relay vergisst nach ~12 h)."""
        _post_plain(_ntopic(self.uname), {"k": "claim", "uname": self.uname, "name": self.name, "uid": self.uid,
                                          "pk": format(self._pk(), "x"), "ts": int(time.time())})
        self._claim_at = time.time()

    def find(self, display):
        """Person per Nutzername suchen → {"uname","name","pk"} (blockierend)."""
        un = uname_of(display)
        if not NAME_OK.match(un):
            raise ValueError("so ein name ist nicht möglich (3–20 zeichen: buchstaben, ziffern, . _ -)")
        if un == self.uname:
            raise ValueError("das bist du")
        try:
            claims = [(e, m) for e, m in _read_plain(_ntopic(un)) if m.get("k") == "claim" and m.get("pk") and m.get("uid")]
        except Exception as e:  # noqa: BLE001
            raise ValueError(why(e)) from e
        if not claims:
            raise ValueError("niemand mit diesem namen gefunden (oder die Person war länger nicht online)")
        first = min(claims, key=lambda x: int(x[0].get("time") or 0))[1]["uid"]       # wer zuerst kam, gilt
        e, m = max((x for x in claims if x[1]["uid"] == first), key=lambda x: int(x[0].get("time") or 0))
        return {"uname": un, "name": str(m.get("name") or un)[:24], "pk": m["pk"]}

    def request(self, display):
        """Freundschaftsanfrage an einen Namen (blockierend). Der eigene Code reist verschlüsselt mit (Schlüssel aus dem
        Anspruch der Person) und wird erst nach Annahme benutzt."""
        P, G, ib = _dh()
        info = self.find(display)
        if any(x.get("uname") == info["uname"] for x in self.friends_sent):
            raise ValueError("anfrage ist schon unterwegs")
        pk = int(info["pk"], 16)
        if not (1 < pk < P - 1):
            raise ValueError("ungültiger schlüssel")
        a = int.from_bytes(secrets.token_bytes(32), "big")
        key = hashlib.sha256(ib(pow(pk, a, P))).digest()
        from handy_sync import box
        body = base64.b64encode(box(key, json.dumps({"secret": self.secret, "uid": self.uid}).encode())).decode()
        _post_plain(_ntopic(info["uname"]), {"k": "req", "uname": self.uname, "name": self.name, "uid": self.uid,
                                             "pa": format(pow(G, a, P), "x"), "box": body, "ts": int(time.time())})
        sent = self.friends_sent + [{"uname": info["uname"], "name": info["name"], "at": int(time.time() * 1000)}]
        engine.set_setting("friends_sent", sent[-30:])
        return info["name"]

    @property
    def friends_sent(self):
        return list(engine.setting("friends_sent") or [])

    def cancel_sent(self, uname):
        engine.set_setting("friends_sent", [x for x in self.friends_sent if x.get("uname") != uname])

    def _drop_sent(self, name):
        un = uname_of(name)
        left = [x for x in self.friends_sent if x.get("uname") != un]
        if len(left) != len(self.friends_sent):
            engine.set_setting("friends_sent", left)

    @property
    def requests(self):
        return list(engine.setting("friends_reqs") or [])

    def poll_requests(self):
        """Eigenes Namens-Thema nach Anfragen absuchen (blockierend) → Zahl neuer."""
        if not self.named or not engine.setting("friends_nk"):
            return 0
        from handy_sync import unbox
        P, G, ib = _dh()
        nk = int(engine.setting("friends_nk"), 16)
        seen = list(engine.setting("friends_req_seen") or [])
        reqs = self.requests
        new = 0
        try:
            items = _read_plain(_ntopic(self.uname))
        except Exception:  # noqa: BLE001
            return 0
        for e, m in items:
            if m.get("k") != "req" or e.get("id") in seen:
                continue
            seen.append(e.get("id"))
            try:
                A = int(m["pa"], 16)
                if not (1 < A < P - 1):
                    continue
                key = hashlib.sha256(ib(pow(A, nk, P))).digest()
                pl = json.loads(unbox(key, base64.b64decode(m["box"])))
            except Exception:  # noqa: BLE001
                continue
            sec = norm(pl.get("secret"))
            if len(sec) != 16 or sec == self.secret or pl.get("uid") == self.uid or sec in self.aliases \
                    or any(f["secret"] == sec for f in self.friends) or any(r["secret"] == sec for r in reqs):
                continue
            reqs.insert(0, {"id": e.get("id"), "uname": str(m.get("uname") or "")[:20],
                            "name": str(m.get("name") or m.get("uname") or "?")[:24], "secret": sec,
                            "at": int(e.get("time") or 0) * 1000})
            new += 1
        engine.set_setting("friends_req_seen", seen[-300:])
        engine.set_setting("friends_reqs", reqs[:30])
        return new

    def accept(self, req):
        """Anfrage annehmen (blockierend): die Person wird Freund, ihr Gerät trägt uns automatisch ein."""
        name = self.add(req["secret"])
        engine.set_setting("friends_reqs", [r for r in self.requests if r.get("secret") != req["secret"]])
        return name

    def decline(self, req):
        engine.set_setting("friends_reqs", [r for r in self.requests if r.get("secret") != req["secret"]])

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
        newtrack = False
        if pid != self._cur_id:
            self._cur_id, self._cur, changed, newtrack = pid, t, True, True
            if t and not str(pid).startswith("local:"):
                threading.Timer(5.0, self._played, args=(pid, t)).start()
        if playing != self._playing:
            self._playing, changed = playing, True
        if changed and not (newtrack and playing and t):      # neuer Titel läuft: erst nach 5 s melden (_played) – eine Nachricht statt zwei
            self._touch()

    def _played(self, pid, t):
        """Nach 5 s echter Wiedergabe in „zuletzt gehört“."""
        if self._cur_id != pid or not self._playing:
            return
        if self.incognito:
            self._touch()
            return
        self.recent = [{**entry(t), "at": int(time.time() * 1000)}] + [r for r in self.recent if r.get("id") != pid]
        self.recent = self.recent[:8]
        engine.set_setting("friends_recent", self.recent)
        self._touch()

    def _beat(self):
        while True:
            time.sleep(30)
            try:
                if self.share and self._playing and time.time() - self._last_pub > 240:
                    self._touch(0)
                if self.named and time.time() - getattr(self, "_claim_at", 0) > 6 * 3600:
                    self._claim()
                if self.recaps is not None:
                    self.recaps.check()               # Sonntagabend / Monatsende / Silvester
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
                self._pf = {"h": round(r["base"]["secs"] / 360) / 10, "hm": round(r["base"]["secs"] / 60)}
                if lv != "minimal":
                    na, nt = 5, 3
                    self._pf.update({"n": r["base"]["tracks"], "ar": r["base"]["artists"],
                            "art": [{"n": x["name"][:30], "m": round(x["secs"] / 60)} for x in r["artists"][:na]],
                            "trk": [{"t": x["t"][:40], "a": x["a"][:30], "n": x["plays"], "i": x.get("id")} for x in r["tracks"][:nt]],
                            "pk": r.get("peak_hour", 0), "sk": round(r.get("skip_rate") or 0)})
                if lv == "mehr":         # die interessantesten weiteren Zahlen aus der Analyse (nur Zahlen/Kurzwörter, keine Titel)
                    self._pf.update({"ct": r.get("chronotype") or "", "dv": round(r.get("diversity") or 0),
                                     "t1": round(r.get("top1_share") or 0), "rs": round(r.get("repeat_share") or 0),
                                     "nw": len(r.get("new_artists") or [])})
                    if r.get("det_n"):
                        self._pf["cr"] = round(r.get("complete_rate") or 0)
                    if r.get("streak_now"):
                        self._pf["sn"] = int(r["streak_now"])
            if self._pf is not None:
                self._pf.update(self._palette())
                rows = self.p.journal.load() or []

                def agg(art):
                    rr = analyse.analyse(rows, art, 0)
                    if rr.get("empty"):
                        return None
                    a = {"hm": round(rr["base"]["secs"] / 60)}
                    if self.level != "minimal":
                        a.update({"n": rr["base"]["tracks"], "ar": rr["base"]["artists"]})
                        if rr["artists"]:
                            a["a"] = {"n": rr["artists"][0]["name"][:30], "m": round(rr["artists"][0]["secs"] / 60)}
                        if rr["tracks"]:
                            t0 = rr["tracks"][0]
                            a["s"] = {"t": t0["t"][:40], "a": t0["a"][:30], "n": t0["plays"], "i": t0.get("id")}
                    return a
                for key, art in (("mo", "m"), ("yr", "y")):          # Summen für Monats-/Jahresrückblick
                    v = agg(art)
                    if v:
                        self._pf[key] = v
        except Exception as e:  # noqa: BLE001
            engine.log(f"freunde: profil {e!r}")
            self._pf = None
        return self._pf

    @staticmethod
    def _palette():
        try:
            import recap
            return recap.own_palette()
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _accent():
        try:
            import recap
            return recap.own_accent()
        except Exception:  # noqa: BLE001
            return ""

    def _payload(self):
        """Genau das sehen Freunde von dir."""
        t = self._cur
        inc = self.inc_until
        now = entry(t) if t and not str(t["videoId"]).startswith("local:") and not inc else None
        lv = self.level
        o = {"k": "prof", "v": 1, "dev": engine.device_id()[:8], "name": self.name, "ts": int(time.time()), "now": now, "pl": bool(now and self._playing),
             "recent": [] if inc else [{k: r[k] for k in ("id", "t", "a")} for r in self.recent[:5]],
             "recs": [] if lv == "minimal" else [{k: r[k] for k in ("id", "t", "a", "th") if k in r} for r in self.recs[:6]]}
        pf = None if inc else self.profile()
        if inc:
            o["inc"] = inc
        if pf:
            o["pf"] = dict(pf)
        size = lambda: len(json.dumps(o, ensure_ascii=False))
        if size() > 2500:                       # Nachrichten sind auf 4 kB begrenzt: erst Empfehlungen, dann „zuletzt“, zuletzt das Profil kürzen
            o["recs"] = o["recs"][:3]
        if size() > 2500:
            o["recent"] = o["recent"][:5]
        if size() > 2500 and "pf" in o:                # Monat/Jahr zuerst weglassen
            o["pf"].pop("mo", None)
            o["pf"].pop("yr", None)
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
            sig = json.dumps({k: v for k, v in o.items() if k != "ts"}, sort_keys=True, default=str)
            if delay != 0 and sig == getattr(self, "_sig", None) and time.time() - getattr(self, "_sent", 0) < 240:
                return                                      # unverändert, Herzschlag noch frisch → keine Nachricht (Tageslimit 250)
            self._sig, self._sent = sig, time.time()
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

    def recommend_album(self, alb):
        if not alb.get("browseId"):
            return False
        e = album_entry(alb)
        self.recs = [{**e, "at": int(time.time() * 1000)}] + [r for r in self.recs if r.get("id") != e["id"]]
        self.recs = self.recs[:12]
        engine.set_setting("friends_recs", self.recs)
        self._touch(0)
        return True

    # ----- Chat -----
    # Nachricht in SEIN Thema (verschlüsselt mit seinem Schlüssel): {"k":"msg","from","fid","ts","x":Text} bzw.
    # {"k":"rec",…,"t":Lied,"x":Text?}. Ältere Versionen kennen nur "rec" (→ Eingang) und ignorieren "msg".
    CHAT_MAX = 300

    def _chats(self):
        return engine.setting("friends_chat") or {}

    def messages(self, sec):
        return list(self._chats().get(sec) or [])

    def _log(self, sec, item):
        with self._chat_lock:
            d = dict(self._chats())
            l = list(d.get(sec) or [])
            if item.get("mid") and any(x.get("mid") == item["mid"] for x in l):
                return False
            l.append(item)
            l.sort(key=lambda x: x.get("at") or 0)
            d[sec] = l[-self.CHAT_MAX:]
            engine.set_setting("friends_chat", d)
        a = getattr(getattr(self, "p", None), "account", None)
        if a is not None:
            a.sync_soon()                               # Konto: Chat bald abgleichen (andere gekoppelte Geräte)
        return True

    def unread(self, sec):
        rd = (engine.setting("friends_read") or {}).get(sec) or 0
        return sum(1 for m in self.messages(sec) if not m.get("me") and (m.get("at") or 0) > rd)

    def unread_total(self):
        return sum(self.unread(f["secret"]) for f in self.friends)

    def mark_read(self, sec):
        d = dict(engine.setting("friends_read") or {})
        d[sec] = int(time.time() * 1000) + 1
        engine.set_setting("friends_read", d)
        self._send_receipt(sec)

    @property
    def read_receipts(self):
        v = engine.setting("friends_receipts")
        return True if v is None else bool(v)

    def set_read_receipts(self, on):
        engine.set_setting("friends_receipts", bool(on))

    def _send_receipt(self, sec):
        """Der anderen Person melden, bis zu welcher ihrer Nachrichten ich gelesen habe (nur bei Neuem)."""
        if not self.read_receipts:
            return
        f = next((x for x in self.friends if x["secret"] == sec), None)
        last = next((m for m in reversed(self.messages(sec)) if not m.get("me") and str(m.get("mid", "")).startswith("m")), None)
        if f is None or last is None:
            return
        rc = dict(engine.setting("friends_rcpt") or {})
        if (last.get("at") or 0) <= rc.get(sec, 0):
            return
        rc[sec] = last["at"]
        engine.set_setting("friends_rcpt", rc)
        msg = {"k": "read", "from": self.name, "fid": fid(self.secret), "fids": self._my_fids(), "mid": str(last["mid"])[1:], "ts": int(time.time() * 1000)}

        def run():
            try:
                _publish(sec, msg)
            except Exception as e:  # noqa: BLE001
                engine.log(f"freunde: lesebestätigung {e!r}")
        threading.Thread(target=run, daemon=True).start()

    def _got_receipt(self, sec, mid, ts):
        with self._chat_lock:
            d = dict(self._chats())
            l = list(d.get(sec) or [])
            ref = next((m for m in l if m.get("me") and m.get("mid") == mid), None)
            if ref is None:
                return False
            ch = False
            for i, m in enumerate(l):
                if m.get("me") and (m.get("at") or 0) <= ref["at"] and not m.get("rd"):
                    l[i] = {**m, "rd": ts}
                    ch = True
            if ch:
                d[sec] = l
                engine.set_setting("friends_chat", d)
            return ch

    def _my_fids(self):
        return [fid(self.secret)] + [fid(a) for a in self.aliases]

    def friend_by(self, fx_id, name, fids=()):
        """Absender einem Freund zuordnen. Ein Mensch mit zwei Geräten (PC+Handy) hat zwei Codes → zwei Kennungen: erst die Kennung
        (auch die Liste „fids“ aller Geräte des Absenders), dann gemerkte Zweitkennungen, zuletzt der Name (nur wenn eindeutig) –
        dann wird die neue Kennung als weiteres Gerät dieses Freundes gemerkt."""
        ids = [x for x in ([fx_id] + [str(x) for x in (fids or []) if isinstance(x, str)]) if x]
        for f in self.friends:
            if fid(f["secret"]) in ids:
                return f
        memo = engine.setting("friends_fidalias") or {}
        for x in ids:
            sec = memo.get(x)
            for f in self.friends:
                if sec and f["secret"] == sec:
                    return f
        nm = (name or "").strip().casefold()
        cand = [f for f in self.friends if (f.get("name") or "").strip().casefold() == nm] if nm else []
        if len(cand) == 1 and (ids or not fx_id):
            if ids:
                memo = dict(memo)
                for x in ids:
                    memo[x] = cand[0]["secret"]
                engine.set_setting("friends_fidalias", memo)
            return cand[0]
        return None

    def send_msg(self, f, text="", t=None, alb=None):
        """Text und/oder Lied an einen Freund; steht sofort im eigenen Verlauf."""
        text = (text or "").strip()[:1000]
        if t is not None and str(t.get("videoId", "")).startswith("local:"):
            return False
        if not text and t is None and alb is None:
            return False
        now = int(time.time() * 1000)
        mid = secrets.token_hex(6)
        msg = {"k": "rec" if (t is not None or alb is not None) else "msg", "from": self.name, "fid": fid(self.secret), "fids": self._my_fids(), "ts": now // 1000, "mid": mid}
        if text:
            msg["x"] = text
        item = {"mid": mid, "me": True, "at": now}
        if text:
            item["x"] = text
        if alb is not None:
            msg["t"] = item["t"] = album_entry(alb)
        elif t is not None:
            msg["t"] = entry(t)
            item["t"] = entry(t)
        self._log(f["secret"], item)

        def run():
            try:
                _publish(f["secret"], msg)
            except Exception as e:  # noqa: BLE001
                engine.log(f"freunde: senden {e!r}")
                self._mark_failed(f["secret"], mid)
        threading.Thread(target=run, daemon=True).start()
        for fn in list(self.listeners):
            fn()
        return True

    def _mark_failed(self, sec, mid):
        with self._chat_lock:
            d = dict(self._chats())
            l = [dict(x, failed=True) if x.get("mid") == mid else x for x in d.get(sec) or []]
            d[sec] = l
            engine.set_setting("friends_chat", d)
        for fn in list(self.listeners):
            fn()

    UNSEND_MS = 5 * 60_000

    def can_unsend(self, m):
        return bool(m.get("me")) and time.time() * 1000 - (m.get("at") or 0) < self.UNSEND_MS

    def unsend(self, f, mid):
        """Eigene Nachricht innerhalb von 5 Minuten zurücknehmen (verschwindet auch beim anderen, wenn er die neue Version hat)."""
        m = next((x for x in self.messages(f["secret"]) if x.get("mid") == mid), None)
        if m is None or not self.can_unsend(m):
            return False
        with self._chat_lock:
            d = dict(self._chats())
            d[f["secret"]] = [x for x in d.get(f["secret"]) or [] if x.get("mid") != mid]
            engine.set_setting("friends_chat", d)
        msg = {"k": "del", "from": self.name, "fid": fid(self.secret), "fids": self._my_fids(), "mid": mid, "ts": int(time.time())}

        def run():
            try:
                _publish(f["secret"], msg)
            except Exception as e:  # noqa: BLE001
                engine.log(f"freunde: zurücknehmen {e!r}")
        threading.Thread(target=run, daemon=True).start()
        for fn in list(self.listeners):
            fn()
        return True

    def send_to(self, f, t):
        """Direkt an einen Freund: erscheint in seinem Chat mit dir."""
        return self.send_msg(f, "", t)

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
        chat_new = 0
        try:
            with relay_open(f"{RELAY}/{_topic(sec)}/json?poll=1&since=all", timeout=12) as r:
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
                        self._drop_sent(str(m.get("name") or ""))        # meine Anfrage wurde angenommen
                        continue
                    if m and m.get("k") == "read" and m.get("mid"):
                        seen.append(e.get("id"))
                        who = self.friend_by(str(m.get("fid") or ""), str(m.get("from") or ""), m.get("fids"))
                        if who is not None and self._got_receipt(who["secret"], str(m["mid"]), int(m.get("ts") or e.get("time", 0) * 1000)):
                            chat_new += 1
                        continue
                    if m and m.get("k") == "del" and m.get("mid"):
                        seen.append(e.get("id"))
                        who = self.friend_by(str(m.get("fid") or ""), str(m.get("from") or ""), m.get("fids"))
                        if who is not None:
                            with self._chat_lock:
                                d = dict(self._chats())
                                l = d.get(who["secret"]) or []
                                keep = [x for x in l if x.get("mid") != "m" + str(m["mid"])]
                                if len(keep) != len(l):
                                    d[who["secret"]] = keep
                                    engine.set_setting("friends_chat", d)
                                    chat_new += 1
                        continue
                    if m and m.get("k") in ("msg", "rec") and m.get("fid") and (m.get("x") or isinstance(m.get("t"), dict)):
                        who = self.friend_by(str(m.get("fid")), str(m.get("from") or ""), m.get("fids"))
                        if who is not None:                              # neue Nachricht → in den Chat mit diesem Freund
                            seen.append(e.get("id"))
                            item = {"mid": ("m" + str(m["mid"])) if m.get("mid") else "n" + str(e.get("id")), "me": False, "at": int(e.get("time") or 0) * 1000}
                            if m.get("x"):
                                item["x"] = str(m["x"])[:1000]
                            if isinstance(m.get("t"), dict):
                                item["t"] = {k: m["t"][k] for k in ("id", "t", "a", "pu", "th", "pn") if m["t"].get(k)}
                            if self._log(who["secret"], item):
                                chat_new += 1
                        continue
                    if not m or m.get("k") != "rec" or not isinstance(m.get("t"), dict):
                        continue
                    seen.append(e.get("id"))
                    fresh.append({**{k: m["t"].get(k, "") for k in ("id", "t", "a", "pu", "th", "pn") if m["t"].get(k)},
                                  **{k: m["t"].get(k, "") for k in ("id", "t", "a")}, "from": str(m.get("from") or "freund")[:24],
                                  "at": int(e.get("time") or 0) * 1000})
        except Exception:  # noqa: BLE001
            return 0
        engine.set_setting("friends_inbox_seen", seen[-500:])
        if fresh:
            engine.set_setting("friends_inbox", (fresh + self.inbox)[:30])
        if added and getattr(self, "say", None):
            self.say(f"{', '.join(added)} hat dich hinzugefügt – ihr seid jetzt befreundet")
        return len(fresh) + chat_new

    def unrecommend(self, vid):
        self.recs = [r for r in self.recs if r.get("id") != vid]
        engine.set_setting("friends_recs", self.recs)
        self._touch(0)

    # ----- Freunde -----
    def _save(self):
        engine.set_setting("friends", self.friends)
        a = getattr(self.p, "account", None) if hasattr(self, "p") else None
        if a is not None:
            a.push_soon()                              # Konto: Freundesliste bald sichern

    @staticmethod
    def live(f):
        pr = f.get("prof") or {}
        return bool(not inc_active(pr.get("inc")) and pr.get("now") and pr.get("pl") and f.get("at") and time.time() * 1000 - f["at"] < 6 * 60_000)

    def fetch_many(self, secs):
        """EINE Anfrage für alle Themen (kommagetrennt) → {sec: [ntfy-Ereignisse]}. ntfy.sh begrenzt je IP auf 60 Anfragen / 5 min
        und 250 Nachrichten / Tag – eine Anfrage je Freund führte zu 429, und Freunde „verschwanden“."""
        import urllib.error
        by = {_topic(s): s for s in secs}
        out = {}
        try:
            with relay_open(f"{RELAY}/{','.join(by)}/json?poll=1&since=all", timeout=15) as r:
                for line in r.read().decode("utf-8", "replace").splitlines():
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("event") == "message" and e.get("topic") in by:
                        out.setdefault(by[e["topic"]], []).append(e)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                self._cool = time.time() + 90
            raise
        return out

    def fetch(self, sec, events=None):
        """Letzten Stand holen → (prof|None, at_ms). Wirft bei Netzfehlern.
        Gekoppelte Geräte (PC + Handy) senden in dasselbe Thema und gelten als eine Person: je Gerät (dev) zählt die letzte
        Nachricht; läuft irgendwo gerade Musik, gewinnt dieses Gerät (sonst überschrieb ein ruhendes Gerät den Stand des spielenden)."""
        per = {}
        if events is None:
            events = self.fetch_many([sec]).get(sec, [])
        for e in events:
            m = _open(sec, e.get("message", ""))
            if not m or m.get("k") != "prof":
                continue
            tm = int(e.get("time") or 0) * 1000
            dv = str(m.get("dev") or "")
            if dv not in per or tm >= per[dv][1]:
                per[dv] = (m, tm)
        return pick_state(per)

    # ----- Abgleich mit dem Handy (über handy_sync) -----
    @property
    def gone(self):
        return dict(engine.setting("friends_gone") or {})

    def _ident(self):
        return ({"uid": self.uid, "uname": self.uname, "name": self.name, "nk": engine.setting("friends_nk") or "",
                 "t": int(engine.setting("friends_name_t") or 0)} if self.named else None)

    def _adopt_ident(self, d):
        """Gekoppelte Geräte teilen Namen + Schlüssel; bei Streit gewinnt der zuletzt geänderte Name."""
        if not isinstance(d, dict) or not d.get("uname") or not d.get("nk") or not d.get("uid"):
            return False
        if self.named and int(d.get("t") or 0) <= int(engine.setting("friends_name_t") or 0):
            return False
        engine.set_setting("friends_uid", str(d["uid"])[:24])
        engine.set_setting("friends_nk", str(d["nk"])[:80])
        engine.set_setting("friends_uname", uname_of(d["uname"]))
        engine.set_setting("friends_name", str(d.get("name") or d["uname"])[:24])
        engine.set_setting("friends_name_t", int(d.get("t") or 0))
        self._touch(0)
        return True

    def sync_out(self):
        return {"id": self._ident(), "me": self.secret, "rc": [{**{k: r[k] for k in ("id", "t", "a")}, "at": r.get("at", 0)} for r in self.recent[:8]], "f": [{"s": f["secret"], "n": f.get("name") or "freund", "t": int(f.get("t") or 1)} for f in self.friends], "g": self.gone}

    def sync_in(self, o, dev="handy"):
        """Freunde vom Handy übernehmen (Vereinigung; bei Streit gewinnt der spätere Zeitpunkt). Dazu: eigener Code
        und „zuletzt gehört“ des gekoppelten Geräts → beide Geräte zeigen Freunden dieselbe Person."""
        gone = self.gone
        changed = self._adopt_ident(o.get("id"))
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
        if self.busy or time.time() < getattr(self, "_cool", 0):       # nach 429 still warten, alte Stände bleiben
            return
        self.busy = True
        try:
            n = self.poll_inbox()
            try:
                n += self.poll_requests()
            except Exception:  # noqa: BLE001
                pass
            if n and getattr(self, "notify", None):
                self.notify(n)
            if not self.friends:
                return
            snap = list(self.friends)
            out = {}
            try:
                allev = self.fetch_many([f["secret"] for f in snap])
            except Exception:  # noqa: BLE001
                return
            if time.time() < getattr(self, "_cool", 0):
                return

            def one(f):
                try:
                    prof, at = self.fetch(f["secret"], allev.get(f["secret"], []))
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
