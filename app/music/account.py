"""Konto bei musicalist-server (Nutzername + Passwort) – gleiches Protokoll wie die Handy-App (acct/*.kt).

Das Passwort geht nur beim Anlegen/Anmelden an den Server; danach gilt ein Sitzungs-Token (DATA/account.json, 0600).
Abgeglichen wird, was auch das Handy abgleicht:
  Block „identity“   Nutzername/Schlüssel + Freunde (friends.sync_out/sync_in, gleiches Format wie beim WLAN-Abgleich)
  Block „settings.pc“ Einstellungen des PCs (eigener Block – die des Handys heißen „settings“)
  Log „hoer“          Hörprotokoll (nur Zeilen mit eigener Geräte-Kennung gehen hoch, fremde werden eingemischt)
  Logs „chat.<kennung>“ Chatverläufe je Freund
Der Relay (Nachrichten an Freunde) läuft nur über den Server, wenn „server_relay“ an ist; sonst weiter ntfy.sh."""
import base64
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

import engine

DEFAULT_URL = "https://musicserver.tailf63251.ts.net"
FILE = os.path.join(engine.DATA, "account.json")
# Einstellungen, die zwischen den Geräten einer Person gleich sein sollen (nichts Rechner-Gebundenes wie Pfade/Fensterlage)
SYNC_KEYS = ("history", "crossfade", "eq", "eq_custom", "ctl_bar", "lib_order", "pixel", "pixel_cfg", "visual", "quick_n", "quick_side",
             "quick_res", "dislikes", "last_playlist", "recap_auto", "analyse_art", "eco_spec", "yt_history", "tv_bar", "autoplay")


class ServerError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def _lead_zeros(h):
    n = 0
    for b in h:
        if b == 0:
            n += 8
            continue
        return n + (8 - b.bit_length())
    return n


def solve(ch, name, bits):
    """sha256(challenge(24) | name | nonce(8, Big-Endian)) mit führenden Nullbits."""
    base = hashlib.sha256()
    base.update(ch)
    base.update(name.encode())
    n = 0
    while True:
        h = base.copy()
        h.update(n.to_bytes(8, "big"))
        if _lead_zeros(h.digest()) >= bits:
            return n
        n += 1


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Account:
    def __init__(self, player):
        global _ACCT
        _ACCT = self
        self.player = player
        self.lock = threading.RLock()
        self.st = self._load()
        self.listeners = []          # fn() nach Anmeldung/Abmeldung/Abgleich
        self.busy = False
        self.last_result = ""
        self._timer = None
        self._soon = False
        self._last_hash = 0
        apply_relay(self.relay_on and self.on)

    # ---------- Zustand ----------
    def _load(self):
        try:
            with open(FILE, encoding="utf-8") as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            tmp = FILE + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.st, f)
            os.replace(tmp, FILE)
        except OSError as e:
            engine.log(f"konto: speichern {e!r}")

    @property
    def on(self):
        return bool(self.st.get("token") and self.st.get("name"))

    @property
    def name(self):
        return self.st.get("name") or ""

    @property
    def url(self):
        return (self.st.get("server") or DEFAULT_URL).rstrip("/")

    @property
    def relay_on(self):
        return self.on                 # Pflicht: mit Konto läuft alles über den Server (bei Fehlern fällt es auf ntfy.sh zurück)

    def set_server(self, url):
        url = (url or "").strip().rstrip("/")
        self.st["server"] = url if url and url != DEFAULT_URL else ""
        self._save()

    def _fire(self):
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    # ---------- HTTP ----------
    def _call(self, method, path, body=None, token=None, headers=None, raw=False, timeout=25):
        data = None
        h = dict(headers or {})
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode()
                h.setdefault("Content-Type", "application/json")
            else:
                data = body
                h.setdefault("Content-Type", "application/octet-stream")
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
                return (r.status, dict(r.headers), payload) if raw else (json.loads(payload) if payload else {})
        except urllib.error.HTTPError as e:
            if raw and e.code in (304, 404):
                return e.code, dict(e.headers), b""
            msg = ""
            try:
                msg = json.loads(e.read()).get("error", "")
            except Exception:  # noqa: BLE001
                pass
            raise ServerError(e.code, msg or f"server: {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ServerError(0, f"server nicht erreichbar ({getattr(e, 'reason', e)})") from None

    @staticmethod
    def _explain(x, what):
        return {409: "dieser name ist auf dem server schon vergeben", 401: x.args[0] if x.args and x.args[0] else "nutzername oder passwort falsch",
                429: x.args[0] if x.args and x.args[0] else "zu viele versuche – kurz warten"}.get(x.code, str(x) or what)

    # ---------- Konto ----------
    def create(self, name, password):
        name = (name or "").strip().lower()
        if len(password) < 10:
            raise ValueError("das passwort braucht mindestens 10 zeichen")
        try:
            c = self._call("GET", "/v1/challenge")
            nonce = solve(_b64d(c["challenge"])[:24].ljust(24, b"\0"), name, int(c["bits"]))
            res = self._call("POST", "/v1/account", {"name": name, "password": password, "challenge": c["challenge"], "nonce": nonce, "label": self._label()})
        except ServerError as x:
            raise ValueError(self._explain(x, "anlegen geht nicht")) from None
        self._store(name, res["token"])
        self.sync(force=True)

    def login(self, name, password):
        """Anmelden (auch auf einem neuen Rechner): holt die gesicherte Identität zurück. Gibt eine Meldung zurück."""
        name = (name or "").strip().lower()
        try:
            res = self._call("POST", "/v1/login", {"name": name, "password": password, "label": self._label()})
        except ServerError as x:
            raise ValueError(self._explain(x, "anmelden geht nicht")) from None
        self._store(name, res["token"])
        fr = getattr(self.player, "friends", None)
        try:
            ver, data = self._blob("identity")
        except ServerError:
            ver, data = 0, None
        if data is None:
            self.sync(force=True)
            return "angemeldet – es gab noch keine sicherung"
        o = json.loads(data)
        if fr is not None:
            me = "".join(ch for ch in str(o.get("me") or "").upper() if ch in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
            if len(me) == 16 and not fr.named:           # neuer Rechner: gleiche Identität wie die anderen Geräte
                engine.set_setting("friends_secret", me)
            fr.sync_in(o, "server")
        self.st["last"] = ver
        self._save()
        r = self.sync(force=True)
        n = len(fr.friends) if fr is not None else 0
        return f"angemeldet – {n} freund·innen wiederhergestellt" + (f", {r['jdown']} hörprotokoll-einträge, {r['cdown']} chat-nachrichten" if r else "")

    def change_password(self, old, new):
        if len(new) < 10:
            raise ValueError("das neue passwort braucht mindestens 10 zeichen")
        try:
            self._call("POST", "/v1/me/password", {"old": old, "new": new}, token=self.st.get("token"))
        except ServerError as x:
            raise ValueError(self._explain(x, "ändern geht nicht")) from None

    def delete_from_server(self, password):
        try:
            self._call("DELETE", "/v1/me", {"password": password}, token=self.st.get("token"))
        except ServerError as x:
            raise ValueError(self._explain(x, "löschen geht nicht")) from None
        self._forget()

    def logout(self):
        if self.st.get("token"):
            try:
                self._call("POST", "/v1/logout", b"", token=self.st["token"])
            except ServerError:
                pass
        self._forget()

    @staticmethod
    def _label():
        import socket
        return ("pc " + socket.gethostname().split(".")[0])[:30]

    def _store(self, name, token):
        server = self.st.get("server")
        self.st = {"name": name, "token": token}
        if server:
            self.st["server"] = server
        self._save()
        apply_relay(self.relay_on)
        self._fire()

    def _forget(self):
        server = self.st.get("server")
        self.st = {"server": server} if server else {}
        self._save()
        apply_relay(False)
        self._fire()

    # ---------- Blöcke / Logs ----------
    def _blob(self, key):
        """(Version, Daten) oder (0, None) wenn es den Block nicht gibt."""
        code, hd, body = self._call("GET", f"/v1/blob/{key}", token=self.st["token"], raw=True)
        if code == 404:
            return 0, None
        return int(hd.get("X-Version") or hd.get("x-version") or 0), body

    def _put_blob(self, key, data, if_version=None):
        h = {"If-Version": str(if_version)} if if_version is not None else {}
        return int(self._call("PUT", f"/v1/blob/{key}", data, token=self.st["token"], headers=h)["version"])

    def _append(self, log, data):
        return int(self._call("POST", f"/v1/log/{log}", data, token=self.st["token"])["seq"])

    def _read_log(self, log, after, limit=100):
        o = self._call("GET", f"/v1/log/{log}?after={after}&limit={limit}", token=self.st["token"])
        return [(e["seq"], _b64d(e["data"])) for e in o.get("entries") or []], int(o.get("next") or after), bool(o.get("more"))

    @staticmethod
    def _chunks(rows, max_bytes=200_000):
        cur, n = [], 0
        for r in rows:
            if n + len(r) > max_bytes and cur:
                yield cur
                cur, n = [], 0
            cur.append(r)
            n += len(r) + 1
        if cur:
            yield cur

    # ---------- Abgleich ----------
    def _identity(self):
        fr = getattr(self.player, "friends", None)
        if fr is None:
            return
        ver, data = self._blob("identity")
        remote = None
        if data is not None:
            try:
                remote = json.loads(data)
            except ValueError:
                remote = None
            if self.st.get("last") != ver and remote is not None:
                fr.sync_in(remote, "server")
                self.st["last"] = ver
        body = fr.sync_out()
        self._last_local = hash(json.dumps(body, sort_keys=True))
        if remote and remote.get("me"):
            body["me"] = remote["me"]                      # „ich“ bleibt, was die anderen Geräte schon gesichert haben
        raw = json.dumps(body, sort_keys=True).encode()
        h = hash(raw)
        if h != self._last_hash or data is None:
            try:
                self.st["last"] = self._put_blob("identity", raw, ver if data is not None else 0)
                self._last_hash = h
            except ServerError as x:
                if x.code != 409:
                    raise

    def _settings(self):
        local = {k: engine.setting(k) for k in SYNC_KEYS if engine.setting(k) is not None}
        raw = json.dumps(local, sort_keys=True)
        last_ver = self.st.get("set_ver")
        last_pushed = self.st.get("set_pushed")
        ver, data = self._blob("settings.pc")
        if data is None:
            self.st["set_ver"] = self._put_blob("settings.pc", raw.encode(), 0)
            self.st["set_pushed"] = raw
            return "hochgeladen"
        if last_ver is not None and ver == last_ver:
            if raw == last_pushed:
                return "unverändert"
            try:
                self.st["set_ver"] = self._put_blob("settings.pc", raw.encode(), ver)
            except ServerError as x:
                if x.code == 409:
                    return self._settings()
                raise
            self.st["set_pushed"] = raw
            return "hochgeladen"
        # anderer Rechner war schneller (oder erstes Mal hier): das Gesicherte gilt
        try:
            remote = json.loads(data)
        except ValueError:
            return "unlesbar"
        for k, v in remote.items():
            if k in SYNC_KEYS:
                engine.set_setting(k, v)
        self.st["set_ver"] = ver
        self.st["set_pushed"] = json.dumps({k: engine.setting(k) for k in SYNC_KEYS if engine.setting(k) is not None}, sort_keys=True)
        return "übernommen"

    def _journal(self):
        j = getattr(self.player, "journal", None)
        if j is None:
            return 0, 0
        me = engine.device_id()[:8]
        up = down = 0
        while True:
            rows, nxt, more = j.lines_from(int(self.st.get("jsent") or 0), limit=400)
            mine = [json.dumps(r, ensure_ascii=False) for r in rows if r.get("dev") == me]
            for c in self._chunks(mine):
                self._append("hoer", "\n".join(c).encode())
                up += len(c)
            self.st["jsent"] = nxt
            if not more:
                break
        after = int(self.st.get("jrecv") or 0)
        while True:
            entries, nxt, more = self._read_log("hoer", after, 100)
            rows = []
            for _s, d in entries:
                for line in d.decode("utf-8", "replace").splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and r.get("dev") != me:
                        rows.append(r)
            if rows:
                down += j.merge(rows)
            after = nxt
            self.st["jrecv"] = after
            if not more:
                break
        return up, down

    def _chats(self):
        fr = getattr(self.player, "friends", None)
        if fr is None:
            return 0, 0
        import friends as frm
        up = down = 0
        known = dict(self.st.get("chat_sent") or {})
        for f in list(fr.friends):
            sec = f["secret"]
            fid = frm.fid(sec)
            log = f"chat.{fid}"
            sent = set(known.get(fid) or [])
            fresh = [m for m in fr.messages(sec) if m.get("mid") and m["mid"] not in sent and not m.get("failed")]
            if fresh:
                rows = [json.dumps({"mid": m["mid"], "me": bool(m.get("me")), "at": int(m.get("at") or 0), "x": m.get("x"), "t": m.get("t"),
                                    "failed": False, "rd": int(m.get("rd") or 0)}, ensure_ascii=False) for m in fresh]
                for c in self._chunks(rows):
                    self._append(log, "\n".join(c).encode())
                up += len(fresh)
                sent.update(m["mid"] for m in fresh)
            key = "crecv_" + fid
            after = int(self.st.get(key) or 0)
            first = after == 0 and not fr.messages(sec)
            newest = 0
            while True:
                entries, nxt, more = self._read_log(log, after, 100)
                for _s, d in entries:
                    for line in d.decode("utf-8", "replace").splitlines():
                        try:
                            m = json.loads(line)
                        except ValueError:
                            continue
                        mid = str(m.get("mid") or "")
                        if not mid:
                            continue
                        sent.add(mid)                     # was von einem anderen Gerät kam, nicht wieder hochladen
                        item = {"mid": mid, "me": bool(m.get("me")), "at": int(m.get("at") or 0)}
                        if m.get("x"):
                            item["x"] = str(m["x"])[:1000]
                        if isinstance(m.get("t"), dict):
                            item["t"] = m["t"]
                        if m.get("rd"):
                            item["rd"] = int(m["rd"])
                        if fr.is_tomb(mid):
                            continue                      # auf einem Gerät zurückgenommen/gelöscht
                        if fr._log(sec, item):
                            down += 1
                        newest = max(newest, item["at"])
                after = nxt
                self.st[key] = after
                if not more:
                    break
            if first and newest:                          # erste Übernahme: alles Alte gilt als gelesen
                rd = dict(engine.setting("friends_read") or {})
                if newest + 1 > (rd.get(sec) or 0):
                    rd[sec] = newest + 1
                    engine.set_setting("friends_read", rd)
            known[fid] = list(sent)[-2000:]
        self.st["chat_sent"] = known
        self._prune(fr, known, frm)
        if down:
            for fn in list(getattr(fr, "listeners", [])):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
        return up, down

    KEEP_DAYS = 14

    def _prune(self, fr, known, frm):
        """Lokal gespeicherte Nachrichten, die älter als ein paar Tage sind UND auf dem Server liegen, werden hier gelöscht
        (auf dem Server bleiben sie; ein neues Gerät holt sie beim Anmelden von dort)."""
        days = int(engine.setting("chat_keep_days") or self.KEEP_DAYS)
        cutoff = int((time.time() - days * 86400) * 1000)
        with fr._chat_lock:
            d = dict(fr._chats())
            changed = False
            for sec, msgs in list(d.items()):
                on_server = set(known.get(frm.fid(sec)) or [])
                keep = [m for m in msgs if (m.get("at") or 0) >= cutoff or m.get("mid") not in on_server]
                if len(keep) != len(msgs):
                    d[sec] = keep
                    changed = True
            if changed:
                engine.set_setting("friends_chat", d)

    def _chatmeta(self):
        """Gelesen-Stand, Zurücknehmen und Lesebestätigungen zwischen den eigenen Geräten (Log „chatmeta“)."""
        fr = getattr(self.player, "friends", None)
        if fr is None:
            return 0, 0
        import jam as jm
        me = jm.device_id()[:8]
        out = list(engine.setting("chat_meta_out") or [])
        up = 0
        if out:
            lines = [json.dumps({**e, "d": me}, ensure_ascii=False) for e in out]
            for c in self._chunks(lines):
                self._append("chatmeta", "\n".join(c).encode())
            up = len(out)
            engine.set_setting("chat_meta_out", list(engine.setting("chat_meta_out") or [])[len(out):])
        down, changed = 0, 0
        after = int(self.st.get("cmeta") or 0)
        while True:
            entries, nxt, more = self._read_log("chatmeta", after, 100)
            for _s, d in entries:
                for line in d.decode("utf-8", "replace").splitlines():
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(ev, dict) or ev.get("d") == me:
                        continue
                    down += 1
                    if fr.apply_meta(ev):
                        changed += 1
            after = nxt
            self.st["cmeta"] = after
            if not more:
                break
        if changed:
            for fn in list(getattr(fr, "listeners", [])):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
        return up, down

    def _devices(self):
        """Jedes Gerät legt „dev.<kennung>“ an (Marmelade-Kennung, Name, eigener Freundes-Code) und liest die der anderen:
        „gekoppelt“ = gleiches Konto (Handy und beliebig viele Rechner sehen und vertrauen sich in der Marmelade, Status geht an alle Codes)."""
        import jam as jm
        fr = getattr(self.player, "friends", None)
        if fr is None:
            return 0
        me = jm.device_id()
        hid = "dev." + hashlib.sha256(me.encode()).hexdigest()[:16]
        raw = json.dumps({"jd": me, "name": jm.host_name(), "kind": "pc", "sec": fr.secret}, sort_keys=True)
        if self.st.get("dev_sent") != raw:
            self._put_blob(hid, raw.encode())
            self.st["dev_sent"] = raw
        old = dict(engine.setting("acct_devs") or {})
        now = {}
        for b in self._call("GET", "/v1/blob", token=self.st["token"]) or []:
            k = b.get("key", "")
            if not k.startswith("dev.") or k == hid:
                continue
            c = old.get(k)
            if c and c.get("ver") == b.get("version"):
                now[k] = c
                continue
            ver, data = self._blob(k)
            try:
                o = json.loads(data) if data else None
            except ValueError:
                o = None
            if not isinstance(o, dict) or len(str(o.get("jd") or "")) < 8 or o.get("jd") == me:
                continue
            now[k] = {"ver": ver, "jd": str(o["jd"]), "name": str(o.get("name") or "gerät")[:40], "sec": str(o.get("sec") or ""), "kind": str(o.get("kind") or "")}
        engine.set_setting("acct_devs", now)
        fr.devices_changed()
        return len(now)

    def _stats(self):
        """Wöchentliche Statistik: für jede abgeschlossene Woche mit Hörprotokoll einmal einen Block „stats.w.<Jahr>-W<KW>“ auf den Server
        (Top-Titel/-Künstler mit Zählern; daraus wertet der Betreiber über alle Nutzenden aus). PC und Handy rechnen aus demselben
        abgeglichenen Hörprotokoll das Gleiche → gleicher Schlüssel, Überschreiben ist harmlos."""
        import analyse
        j = getattr(self.player, "journal", None)
        rows = (j.load() if j is not None else None) or []
        if not rows:
            return 0
        sent = dict(self.st.get("stats_sent") or {})
        first = min(r["at"] for r in rows)
        n = 0
        for off in range(-1, -400, -1):
            lo, hi, _t, _s = analyse.bounds("w", off)
            if hi <= first:
                break
            period = "%d-W%02d" % analyse.day_key(lo).isocalendar()[:2]
            old = sent.get(period)
            if old and off < -2:
                continue                                # ältere Wochen: einmal hochladen genügt (die letzten 2 werden bei Änderung erneuert)
            r = analyse.analyse(rows, "w", off)
            if r.get("empty"):
                sent[period] = "e"
                continue
            doc = {"v": 1, "period": period, "secs": int(r["base"]["secs"]),
                   "tracks": [{"id": t["id"], "t": t.get("t", ""), "a": t.get("a", ""), "n": int(t["plays"]), "s": int(t["secs"])} for t in r["tracks"][:100]],
                   "artists": [{"n": a["name"], "s": int(a["secs"]), "p": int(a["plays"])} for a in r["artists"][:50]]}
            raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
            h = hashlib.sha1(raw).hexdigest()[:12]
            if old == h:
                continue
            self._put_blob("stats.w." + period, raw)
            sent[period] = h
            n += 1
            if n >= 60:
                break
        self.st["stats_sent"] = sent
        return n

    def sync(self, force=False):
        """Alles abgleichen (blockierend). Ohne force höchstens alle 2 Minuten. → Zahlen oder None."""
        if not self.on:
            return None
        with self.lock:
            if not force and time.time() - float(self.st.get("_at") or 0) < 120:
                return None
            self.busy = True
            self._fire()
            res = {"settings": "", "jup": 0, "jdown": 0, "cup": 0, "cdown": 0, "error": ""}
            try:
                for what, fn in (("identity", self._identity), ("settings", self._settings), ("journal", self._journal), ("devices", self._devices), ("stats", self._stats), ("chats", self._chats), ("chatmeta", self._chatmeta)):
                    try:
                        r = fn()
                        if what == "settings":
                            res["settings"] = r
                        elif what == "journal":
                            res["jup"], res["jdown"] = r
                        elif what == "chats":
                            res["cup"], res["cdown"] = r
                    except ServerError as x:
                        if x.code == 401:
                            self._forget()
                            res["error"] = "abgemeldet – passwort wurde geändert oder zurückgesetzt, bitte neu anmelden"
                            return res
                        res["error"] = f"{what}: {x}"
                        engine.log(f"konto: {what} {x!r}")
                    except Exception as e:  # noqa: BLE001
                        res["error"] = f"{what}: {e}"
                        engine.log(f"konto: {what} {e!r}")
                self.st["_at"] = time.time()
                self._save()
            finally:
                self.busy = False
                self.last_result = res["error"] or time.strftime("%H:%M") + f" · ↑{res['jup'] + res['cup']} ↓{res['jdown'] + res['cdown']}"
                self._fire()
            return res

    def push_soon(self):
        """Identität in ~20 s sichern (nach Änderungen an der Freundesliste)."""
        if not self.on or self._soon:
            return
        fr = getattr(self.player, "friends", None)
        if fr is not None and hash(json.dumps(fr.sync_out(), sort_keys=True)) == getattr(self, "_last_local", None):
            return                                      # an der Freundesliste hat sich nichts geändert
        self._soon = True

        def run():
            time.sleep(20)
            self._soon = False
            try:
                self.sync(force=True)
            except Exception as e:  # noqa: BLE001
                engine.log(f"konto: {e!r}")
        threading.Thread(target=run, daemon=True).start()

    def sync_soon(self, sec=15):
        """Chat hat sich geändert → in ~15 s alles abgleichen (das andere gekoppelte Gerät sieht die Nachricht dann bald)."""
        if not self.on or getattr(self, "_soon_sync", False):
            return
        self._soon_sync = True

        def run():
            time.sleep(sec)
            self._soon_sync = False
            try:
                self.sync(force=True)
            except Exception as e:  # noqa: BLE001
                engine.log(f"konto: {e!r}")
        threading.Thread(target=run, daemon=True).start()

    # ---------- Hintergrund ----------
    def start(self):
        if self._timer is not None:
            return

        def loop():
            time.sleep(30)
            while True:
                if self.on:
                    try:
                        self.sync()
                    except Exception as e:  # noqa: BLE001
                        engine.log(f"konto: {e!r}")
                time.sleep(120)
        self._timer = threading.Thread(target=loop, daemon=True)
        self._timer.start()


def apply_relay(on):
    """Nachrichten an Freunde über den eigenen Server statt ntfy.sh (gleiches Protokoll)."""
    import friends
    import jam
    base = (_ACCT.url if _ACCT is not None else DEFAULT_URL) if on else friends.NTFY
    changed = friends.RELAY != base
    friends.RELAY = jam.RELAY = base
    if changed and on:
        fr = getattr(_ACCT.player, "friends", None) if _ACCT is not None else None
        if fr is not None:
            fr._claim_at = 0          # Nutzername sofort auf dem neuen Relay anmelden (sonst findet dich niemand bis zur nächsten Runde)


_ACCT = None


def create(player):
    global _ACCT
    _ACCT = Account(player)
    return _ACCT
