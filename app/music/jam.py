# musicalist – Jam im WLAN, wie auf dem Handy (Jam.kt): starten (Gastgeber) oder beitreten (Gast).
# Gastgeber: kleiner HTTP-Server auf Port 37530 mit 4-stelligem Code, mDNS-Eintrag _musicalist-jam._tcp (zeroconf),
# Browser-Seite für Gäste ohne App (gleich wie auf dem Handy). Gäste dürfen nur hinzufügen; ihre Titel landen vor
# Radio/Autoplay. Gast: Jam per mDNS finden oder Adresse eintippen; solange beigetreten, schicken „abspielen“,
# „als nächstes“ und „anhängen“ den Titel an den Gastgeber statt ihn selbst zu spielen (Player.jam_route).
# Protokoll (identisch mit der Handy-App): GET /api/state, GET /api/search?q=, POST /api/add {t, next},
# POST /api/ctl {op: next|prev|toggle|remove, id} (nur Gäste mit Rechten); immer ?c=<code>&n=<name>&d=<geräte-kennung>.
# Titel als {id, t, a, al, d, th, src, sn}. Der Gastgeber kann Rechte geben, Geräte dafür merken (Einstellung
# jam_trusted), Gäste entfernen und die Jam umbenennen (jam_title). Im Stand stehen Rechte/Entfernte nur als Kurzform.
import base64, hashlib, json, secrets, socket, threading, time, urllib.parse, urllib.request

from gi.repository import GLib

import engine

PORT = 37530
TYPE = "_musicalist-jam._tcp.local."
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"       # ohne 0/O, 1/I
RELAY = "https://ntfy.sh"                       # Internet-Weg (Ende-zu-Ende verschlüsselt, wie Jam.kt)


def norm_code(c):
    return "".join(ch for ch in (c or "").upper() if ch in ALPHA)


def _topic(code):
    return "mjam-" + hashlib.sha256(f"musicalist-jam-topic|{code}".encode()).hexdigest()[:24]


def _key(code):
    return hashlib.sha256(f"musicalist-jam-key|{code}".encode()).digest()


def _seal(code, obj):
    from handy_sync import box
    return base64.b64encode(box(_key(code), json.dumps(obj, ensure_ascii=False).encode())).decode()


def _open(code, msg):
    from handy_sync import unbox
    try:
        return json.loads(unbox(_key(code), base64.b64decode(msg)))
    except Exception:  # noqa: BLE001 – fremde/kaputte Nachricht
        return None


def _publish(code, obj):
    req = urllib.request.Request(f"{RELAY}/{_topic(code)}", data=_seal(code, obj).encode(), method="POST",
                                 headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def slim(t):
    if not t:
        return None
    o = {"id": t.get("id"), "t": (t.get("t") or "")[:70], "a": (t.get("a") or "")[:50]}
    if t.get("src") == "jam":
        o["src"], o["sn"] = "jam", (t.get("sn") or "")[:24]
    return o


def to_proto(t):
    """engine-Titel → Protokoll."""
    src = t.get("_src") or ()
    o = {"id": t["videoId"], "t": t.get("title") or "?", "a": t.get("artist") or "", "al": t.get("album") or None,
         "d": int(t.get("duration") or 0), "th": t.get("thumb") or f"https://i.ytimg.com/vi/{t['videoId']}/hqdefault.jpg"}
    if src:
        o["src"] = src[0]
        if len(src) > 1 and src[1]:
            o["sn"] = str(src[1])
    return o


def from_proto(o):
    return {"videoId": o["id"], "title": o.get("t") or "?", "artist": o.get("a") or "", "album": o.get("al") or "",
            "duration": int(o.get("d") or 0), "thumb": o.get("th") or "", "artistId": None, "albumId": None}


def host_name():
    return (socket.gethostname().split(".")[0] or "pc").lower()


def jam_title():
    return (engine.setting("jam_title") or "").strip() or f"marmelade von {host_name()}"


def device_id():
    """Eigene zufällige Geräte-Kennung (bleibt) – daran erkennt ein Gastgeber gemerkte Geräte."""
    d = engine.setting("device_id")
    if not d:
        d = secrets.token_hex(10)
        engine.set_setting("device_id", d)
    return d


def hid(dev):
    """Öffentliche Kurzform einer Kennung (steht im Stand; die Kennung selbst nicht)."""
    return hashlib.sha256(f"musicalist-jam-dev|{dev}".encode()).hexdigest()[:12]


def _gkey(name, dev):
    dev = (dev or "").strip()[:40]
    return dev if len(dev) >= 8 else f"n:{name}"


def trusted():
    return dict(engine.setting("jam_trusted") or {})


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return ips


def _on_main(fn, timeout=3):
    """fn im GTK-Thread ausführen und auf das Ergebnis warten (der Player ist nicht threadsicher)."""
    box, ev = {}, threading.Event()

    def run():
        try:
            box["r"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e
        ev.set()
        return False
    GLib.idle_add(run)
    if not ev.wait(timeout):
        raise TimeoutError("player antwortet nicht")
    if "e" in box:
        raise box["e"]
    return box.get("r")


class Jam:
    def __init__(self, player):
        self.p = player
        self.httpd = None
        self.zc = None
        self.code = ""
        self.guests = {}            # key (Geräte-Kennung oder n:<name>) → {"name", "seen", "added", "admin", "dev"}
        self.kicked = set()
        self.events = []
        self.joined = None          # Gast: {"host", "port", "code", "name", "host_name"}
        self.listeners = []         # fn() bei Änderungen (Oberfläche)
        self.colors = ("#faf8ff", "#1b1b21", "#4c5c92")
        self.error = None
        self.say = None             # fn(text) der Oberfläche für Meldungen
        self.lan_ok = False         # auch im WLAN erreichbar (Browser-Gäste)
        self.net_status = ""        # Internet-Weg: verbunden / verbindet … / Fehler
        self._net_gen = 0
        self._net_state = None
        self._net_state_at = 0
        self._kick = False

    # ----- allgemein -----
    def _notify(self):
        for fn in list(self.listeners):
            GLib.idle_add(lambda f=fn: f() and False)

    _hosting = False

    @property
    def hosting(self):
        return self._hosting

    def url(self):
        ips = local_ips()
        return f"http://{ips[0]}:{PORT}/?c={self.code}" if ips else None

    # ================= Gastgeber =================
    def start(self):
        if self.httpd is not None:
            return True
        from http.server import ThreadingHTTPServer
        self.code = "".join(secrets.choice(ALPHA) for _ in range(6))
        self.guests, self.events, self.error, self.kicked = {}, [], None, set()
        self._hosting = True
        # im WLAN (auch für Browser-Gäste) – geht der Port nicht, läuft die Jam trotzdem übers Internet
        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", PORT), self._handler())
            self.httpd.daemon_threads = True
            self.httpd.timeout = 5
            threading.Thread(target=self.httpd.serve_forever, daemon=True, name="jam").start()
            threading.Thread(target=self._announce, daemon=True).start()
            self.lan_ok = True
        except OSError as e:
            self.httpd, self.lan_ok = None, False
            self.error = f"im wlan nicht erreichbar (port {PORT}: {e.strerror}) – läuft übers internet"
        self._net_host()
        self._notify()
        return True

    def stop(self):
        self._hosting = False
        self._net_stop()
        if self.httpd is not None:
            srv, self.httpd = self.httpd, None
            threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()
        if self.zc is not None:
            zc, self.zc = self.zc, None
            threading.Thread(target=lambda: zc.close(), daemon=True).start()
        self._notify()

    def _announce(self):
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError:
            return
        try:
            ips = local_ips()
            info = ServiceInfo(TYPE, f"{jam_title()[:60]}.{TYPE}", port=PORT,
                               addresses=[socket.inet_aton(i) for i in ips], properties={"v": "1"},
                               server=f"{host_name()}-jam.local.")
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            zc.register_service(info)
            self.zc = zc
        except Exception as e:  # noqa: BLE001
            engine.log(f"jam mdns: {e}")

    def _event(self, text):
        self.events = ([text] + self.events)[:20]
        self._notify()
        if self.say:
            GLib.idle_add(lambda: self.say(f"󰀂 {text}") and False)

    def _seen(self, name, key):
        g = self.guests.get(key)
        if g is None:
            tr = key in trusted()
            self._event(f"{name} ist der marmelade beigetreten" + (" (gemerkt: hat rechte)" if tr else ""))
            g = self.guests[key] = {"added": 0, "admin": tr, "dev": None if key.startswith("n:") else key}
        g["name"], g["seen"] = name, time.time()

    def is_admin(self, key):
        return bool((self.guests.get(key) or {}).get("admin")) or key in trusted()

    # ----- Gastgeber verwaltet Gäste -----
    def set_admin(self, key, on):
        g = self.guests.get(key)
        if not g:
            return
        if not on and key in trusted():
            tr = trusted()
            tr.pop(key, None)
            engine.set_setting("jam_trusted", tr)
        g["admin"] = on
        self._event(f"{g['name']} hat jetzt gastgeber-rechte" if on else f"{g['name']} hat keine rechte mehr")
        self._kick = True

    def trust(self, key, on):
        g = self.guests.get(key) or {}
        dev = g.get("dev") or (None if key.startswith("n:") else key)
        if not dev:
            return
        tr = trusted()
        if on:
            tr[dev] = g.get("name") or dev[:6]
            if g:
                g["admin"] = True
        else:
            tr.pop(dev, None)
        engine.set_setting("jam_trusted", tr)
        if g:
            self._event(f"{g['name']}: gerät gemerkt (immer rechte)" if on else f"{g['name']}: gerät vergessen")
        self._kick = True

    def kick(self, key):
        g = self.guests.pop(key, None) or {}
        self.kicked.add(key)
        self._event(f"{g.get('name', 'gast')} wurde aus der marmelade entfernt")
        self._kick = True

    def rename(self, title):
        engine.set_setting("jam_title", (title or "").strip()[:40])
        self._kick = True
        self._notify()

    def roles(self, st):
        gs = sorted(self.guests.items(), key=lambda kv: (kv[1].get("name") or "").lower())
        st["title"] = jam_title()
        st["guests"] = [g.get("name") for _, g in gs]
        st["people"] = [{"n": (g.get("name") or "")[:24], "a": self.is_admin(k)} for k, g in gs[:16]]
        st["admins"] = [hid(g["dev"]) for k, g in gs if g.get("dev") and self.is_admin(k)]
        st["kicked"] = [hid(k) for k in self.kicked if not k.startswith("n:")]
        return st

    def ctl(self, op, vid, name):
        """Steuerbefehl eines Gasts mit Rechten (GTK-Thread)."""
        def run():
            p = self.p
            if op == "next":
                p.next()
            elif op == "prev":
                if p.index > 0:
                    p._why = "zurück"
                    p.index -= 1
                    p.load()
                else:
                    p.seek(0)
            elif op == "toggle":
                p.toggle()
            elif op == "remove":
                i = next((k for k in range(p.index + 1, len(p.queue)) if p.queue[k].get("videoId") == vid), None)
                if i is None:
                    return False
                p.remove(i)
            else:
                return False
            return True
        if _on_main(run):
            self._event(f"{name}: " + {"next": "übersprungen", "prev": "zurück", "toggle": "pause/weiter",
                                         "remove": "titel entfernt"}.get(op, op))
            self._kick = True

    def state(self):
        def read():
            p = self.p
            cur = p.current
            q = [to_proto(t) for t in p.queue[p.index + 1:p.index + 31]] if p.index >= 0 else []
            return {"now": to_proto(cur) if cur else None, "playing": bool(p.started and not p.paused),
                    "queue": q}
        st = _on_main(read)
        st["host"] = host_name()
        return self.roles(st)

    def search(self, q):
        res = self.p.music.search(q, "songs") if q else []
        return [to_proto(t) for t in (engine.track(r) for r in res) if t][:20]

    def add(self, o, nxt, name, key=None):
        t = from_proto(o)
        t["_src"] = ("jam", name)
        _on_main(lambda: self.p.jam_insert(t, nxt))
        key = key or f"n:{name}"
        self._seen(name, key)
        self.guests[key]["added"] = self.guests[key].get("added", 0) + 1
        self._event(f"{name} hat „{t['title']}“ hinzugefügt")

    def page(self):
        bg, fg, pr = self.colors
        title = jam_title().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return PAGE.replace("{{BG}}", bg).replace("{{FG}}", fg).replace("{{PR}}", pr).replace("{{TITLE}}", title)

    def _handler(self):
        jam = self
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 5

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False).encode()
                elif isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            def _route(self, method):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                if u.path in ("/", "/index.html"):
                    return self._send(200, jam.page(), "text/html; charset=utf-8")
                if norm_code(q.get("c")) != jam.code:
                    return self._send(401, {"error": "code falsch"})
                name = (q.get("n") or "gast").strip()[:24] or "gast"
                key = _gkey(name, q.get("d"))
                if key in jam.kicked:
                    return self._send(403, {"error": "kicked"})
                jam._seen(name, key)
                try:
                    if u.path == "/api/state":
                        return self._send(200, {**jam.state(), "you": {"admin": jam.is_admin(key)}})
                    if u.path == "/api/ctl" and method == "POST":
                        if not jam.is_admin(key):
                            return self._send(403, {"error": "keine rechte"})
                        n = int(self.headers.get("Content-Length") or 0)
                        o = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                        jam.ctl(o.get("op"), o.get("id"), name)
                        return self._send(200, {"ok": True})
                    if u.path == "/api/search":
                        return self._send(200, {"results": jam.search(q.get("q", ""))})
                    if u.path == "/api/add" and method == "POST":
                        n = int(self.headers.get("Content-Length") or 0)
                        o = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                        jam.add(o["t"], bool(o.get("next")), name, key)
                        return self._send(200, {"ok": True})
                except Exception as e:  # noqa: BLE001
                    engine.log(f"jam: {e!r}")
                    return self._send(500, {"error": str(e)[:200]})
                self._send(404, {"error": "?"})

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

        return H

    # ================= Gast =================
    def discover(self, wait=2.5):
        """Jams im WLAN (blockierend). → [(name, host, port)]"""
        try:
            from zeroconf import IPVersion, ServiceBrowser, Zeroconf
        except ImportError:
            return []
        found = {}
        zc = Zeroconf(ip_version=IPVersion.V4Only)

        class L:
            def add_service(self, z, typ, name):
                info = z.get_service_info(typ, name, timeout=1500)
                if info and info.addresses:
                    found[name] = (name.split("._")[0], socket.inet_ntoa(info.addresses[0]), info.port)

            def update_service(self, *a):
                pass

            def remove_service(self, *a):
                pass
        try:
            ServiceBrowser(zc, TYPE, L())
            time.sleep(wait)
        finally:
            zc.close()
        own = set(local_ips()) if self.hosting else set()
        return [f for f in found.values() if f[1] not in own]

    def _url(self, j, path, **extra):
        q = {"c": j["code"], "n": j["name"], "d": device_id(), **extra}
        return f"http://{j['host']}:{j['port']}{path}?" + urllib.parse.urlencode(q)

    def _get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                msg = json.load(e).get("error")
            except Exception:  # noqa: BLE001
                msg = None
            raise RuntimeError(msg or f"http {e.code}") from None

    def join(self, host, port, code, name):
        """Blockierend. Prüft Code + Erreichbarkeit."""
        j = {"host": host.strip(), "port": int(port or PORT), "code": norm_code(code), "name": (name or host_name()).strip()}
        st = self._get(self._url(j, "/api/state"))
        j["host_name"] = st.get("host", "jam")
        self.joined = j
        self._notify()
        return j["host_name"]

    def leave(self):
        if self.joined and self.joined.get("net"):
            self._net_stop()
        self.joined = None
        self._notify()

    def _kicked_out(self):
        self.leave()
        if self.say:
            GLib.idle_add(lambda: self.say("󰀂 du wurdest aus der marmelade entfernt") and False)

    def remote_state(self):
        j = self.joined
        if not j:
            return None
        if j.get("net"):
            st = self._net_state if time.time() - self._net_state_at < 90 else None
        else:
            try:
                st = self._get(self._url(j, "/api/state"))
            except RuntimeError as e:
                if str(e) == "kicked":
                    self._kicked_out()
                    return None
                raise
        if st and hid(device_id()) in (st.get("kicked") or []):
            self._kicked_out()
            return None
        return st

    @staticmethod
    def am_admin(st):
        if not st:
            return False
        if isinstance(st.get("you"), dict):
            return bool(st["you"].get("admin"))
        return hid(device_id()) in (st.get("admins") or [])

    def ctl_remote(self, op, vid=None):
        """Blockierend. Gast mit Rechten steuert die Wiedergabe des Gastgebers."""
        j = self.joined
        if not j:
            raise RuntimeError("keine marmelade")
        if j.get("net"):
            _publish(j["code"], {"k": "ctl", "op": op, "id": vid, "name": j["name"], "dev": device_id()})
            return
        req = urllib.request.Request(self._url(j, "/api/ctl"), data=json.dumps({"op": op, "id": vid}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.load(e).get("error")
            except Exception:  # noqa: BLE001
                msg = None
            raise RuntimeError(msg or f"http {e.code}") from None

    def add_remote(self, t, nxt):
        j = self.joined
        if not j:
            raise RuntimeError("keine marmelade")
        if j.get("net"):
            o = to_proto(t)
            o.pop("src", None)
            o.pop("sn", None)
            _publish(j["code"], {"k": "add", "name": j["name"], "dev": device_id(), "next": nxt, "t": o})
            return
        o = to_proto(t)
        o.pop("src", None)
        o.pop("sn", None)
        req = urllib.request.Request(self._url(j, "/api/add"), data=json.dumps({"t": o, "next": nxt}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"http {e.code}") from None


# ================= Internet-Weg (Relay) =================
def _listen(jam, code, on_msg):
    """Nachrichten des Themas lesen (Dauerverbindung, verbindet neu), bis _net_stop()."""
    jam._net_gen += 1
    gen = jam._net_gen

    def run():
        since = str(int(time.time()))
        while gen == jam._net_gen:
            try:
                jam.net_status = "verbindet …"
                jam._notify()
                with urllib.request.urlopen(f"{RELAY}/{_topic(code)}/json?since={since}", timeout=90) as r:
                    jam.net_status = "verbunden"
                    jam._notify()
                    for line in r:
                        if gen != jam._net_gen:
                            return
                        try:
                            e = json.loads(line)
                        except ValueError:
                            continue
                        if e.get("event") != "message":
                            continue
                        since = e.get("id", since)
                        m = _open(code, e.get("message", ""))
                        if m:
                            on_msg(m)
            except Exception as e:  # noqa: BLE001
                if gen != jam._net_gen:
                    return
                jam.net_status = f"internet: {str(e)[:60]} – neuer versuch …"
                jam._notify()
                time.sleep(3)
    threading.Thread(target=run, daemon=True, name="jam-netz").start()
    return gen


def _net_stop(self):
    self._net_gen += 1
    self._net_state = None
    self.net_status = ""


def _net_host(self):
    code = self.code

    def on_msg(m):
        name = (m.get("name") or "gast")[:24] or "gast"
        key = _gkey(name, m.get("dev"))
        if m.get("k") in ("hello", "add", "ctl") and key in self.kicked:
            return
        if m.get("k") == "hello":
            self._seen(name, key)
            self._kick = True
        elif m.get("k") == "add" and isinstance(m.get("t"), dict):
            try:
                self.add(m["t"], bool(m.get("next")), name, key)
            except Exception as e:  # noqa: BLE001
                engine.log(f"jam netz: {e!r}")
            self._kick = True
        elif m.get("k") == "ctl" and self.is_admin(key):
            try:
                self.ctl(m.get("op"), m.get("id"), name)
            except Exception as e:  # noqa: BLE001
                engine.log(f"jam netz ctl: {e!r}")
    gen = _listen(self, code, on_msg)

    def publisher():
        last, last_at = None, 0
        while gen == self._net_gen and self._hosting:
            try:
                st = self.state()
                o = self.roles({"k": "state", "host": host_name(), "now": slim(st.get("now")), "playing": st.get("playing"),
                                "queue": [slim(t) for t in (st.get("queue") or [])[:12]]})
                sig = json.dumps(o, sort_keys=True)
                if sig != last or time.time() - last_at > 30 or self._kick:
                    self._kick = False
                    _publish(code, {**o, "ts": int(time.time())})
                    last, last_at = sig, time.time()
            except Exception as e:  # noqa: BLE001
                engine.log(f"jam netz stand: {e!r}")
            time.sleep(1.5)
    threading.Thread(target=publisher, daemon=True, name="jam-netz-stand").start()


def _join_net(self, code, name):
    code = norm_code(code)
    if len(code) != 6:
        raise RuntimeError("der code hat 6 zeichen")
    self._net_stop()
    last = None
    with urllib.request.urlopen(f"{RELAY}/{_topic(code)}/json?poll=1&since=2m", timeout=10) as r:
        for line in r.read().decode().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = _open(code, e.get("message", ""))
            if m and m.get("k") == "state":
                last = m
    if last is None:
        raise RuntimeError("keine marmelade mit diesem code (oder der gastgeber ist offline)")
    nm = (name or host_name()).strip()
    self._net_state, self._net_state_at = last, time.time()
    self.joined = {"host": "", "port": 0, "code": code, "name": nm, "host_name": last.get("host", "jam"), "net": True}

    def on_msg(m):
        if m.get("k") == "state":
            self._net_state, self._net_state_at = m, time.time()
    _listen(self, code, on_msg)
    try:
        _publish(code, {"k": "hello", "name": nm, "dev": device_id()})
    except Exception:  # noqa: BLE001
        pass
    self._notify()
    return self.joined["host_name"]


Jam._net_stop = _net_stop
Jam._net_host = _net_host
Jam.join_net = _join_net


def qr_matrix(data):
    """QR-Code als Matrix (Listen aus bool) oder None ohne qrcode-Paket."""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=1)
    q.add_data(data)
    q.make(fit=True)
    return q.get_matrix()


def qr_text(data):
    """QR-Code als Text aus Halbblöcken (▀▄█) – passt in die monospace-Oberfläche. None ohne qrcode-Paket."""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=1)
    q.add_data(data)
    q.make(fit=True)
    m = q.get_matrix()
    lines = []
    for y in range(0, len(m), 2):
        top, bot = m[y], m[y + 1] if y + 1 < len(m) else [False] * len(m[y])
        lines.append("".join("█" if a and b else "▀" if a else "▄" if b else " " for a, b in zip(top, bot)))
    return "\n".join(lines)


PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>marmelade · musicalist</title>
<style>
:root{--bg:{{BG}};--fg:{{FG}};--pr:{{PR}}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 ui-monospace,"JetBrains Mono",Menlo,monospace;padding:14px;max-width:640px;margin:auto}
.panel{position:relative;border:1px solid color-mix(in srgb,var(--pr) 45%,transparent);border-radius:6px;padding:16px 12px 10px;margin:14px 0}
.panel>b.t{position:absolute;top:-10px;left:10px;background:var(--bg);color:var(--pr);padding:0 4px;font-size:12px}
.row{display:flex;gap:10px;align-items:center;padding:6px 0}.row img{width:44px;height:44px;object-fit:cover;border-radius:3px;flex:none}
.row .tx{flex:1;min-width:0}.row .tx div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dim{opacity:.7;font-size:12px}
button{font:inherit;color:var(--fg);background:none;border:1px solid color-mix(in srgb,var(--pr) 70%,transparent);border-radius:4px;padding:8px 10px;cursor:pointer;min-height:40px}
button.p{background:var(--pr);color:var(--bg)}input{font:inherit;color:var(--fg);background:none;border:1px solid var(--pr);border-radius:4px;padding:10px;width:100%}
h1{font-size:16px;margin:0;color:var(--pr)}#msg{min-height:20px;color:var(--pr);font-size:12px}
</style></head><body>
<h1 id="ttl">♫ {{TITLE}}</h1><div id="msg"></div>
<div id="login" class="panel"><b class="t">beitreten</b>
<input id="name" placeholder="dein name"><div style="height:8px"></div><input id="code" placeholder="code (6 zeichen)" autocapitalize="characters">
<div style="height:8px"></div><button class="p" onclick="go()">beitreten</button></div>
<div id="app" hidden>
<div class="panel"><b class="t">läuft</b><div id="now"></div>
<div id="ctl" hidden style="display:flex;gap:8px;margin-top:6px"><button onclick="ctl('prev')">⏮</button><button class="p" onclick="ctl('toggle')">⏯</button><button onclick="ctl('next')">⏭ überspringen</button></div></div>
<div class="panel"><b class="t">suchen &amp; hinzufügen</b><input id="q" placeholder="titel, künstler …" oninput="typed()"><div id="res"></div></div>
<div class="panel"><b class="t">als nächstes</b><div id="queue"></div></div>
</div>
<script>
const P=new URLSearchParams(location.search);let C=P.get('c')||localStorage.jamCode||'',N=localStorage.jamName||'',A=false,T=null;
let D=localStorage.jamDev;if(!D||D.length<8){D=(crypto.randomUUID?crypto.randomUUID():String(Math.random())+Date.now()).replace(/[^a-f0-9]/gi,'').slice(0,20);localStorage.jamDev=D}
document.getElementById('code').value=C;document.getElementById('name').value=N;
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const api=(p,x)=>p+(p.includes('?')?'&':'?')+'c='+encodeURIComponent(C)+'&n='+encodeURIComponent(N)+'&d='+D+(x||'');
function msg(m){document.getElementById('msg').textContent=m;setTimeout(()=>{if(document.getElementById('msg').textContent==m)document.getElementById('msg').textContent=''},4000)}
function row(t,btn){return '<div class="row"><img src="'+esc(t.th)+'" alt=""><div class="tx"><div>'+esc(t.t)+'</div><div class="dim">'+esc(t.a)+'</div></div>'+(btn||'')+'</div>'}
async function go(){N=document.getElementById('name').value.trim()||'gast';C=document.getElementById('code').value.trim().toUpperCase();
 const r=await fetch(api('/api/state'));if(r.status==403){out();return}if(!r.ok){msg('code falsch');return}
 localStorage.jamName=N;localStorage.jamCode=C;document.getElementById('login').hidden=true;document.getElementById('app').hidden=false;show(await r.json());T=setInterval(load,3000)}
function out(){clearInterval(T);document.getElementById('app').hidden=true;document.getElementById('login').hidden=true;msg('du wurdest aus der marmelade entfernt');document.getElementById('msg').textContent='du wurdest aus der marmelade entfernt'}
async function load(){const r=await fetch(api('/api/state'));if(r.status==403){out();return}if(r.ok)show(await r.json())}
let Q=[];function show(s){A=!!(s.you&&s.you.admin);Q=s.queue||[];if(s.title)document.getElementById('ttl').textContent='♫ '+s.title;
 document.getElementById('ctl').hidden=!A;document.getElementById('ctl').style.display=A?'flex':'none';
 const ppl=(s.people||[]).map(p=>esc(p.n)+(p.a?' ★':'')).join(', ')||esc((s.guests||[]).join(', '));
 document.getElementById('now').innerHTML=s.now?row(s.now)+'<div class="dim">'+(s.playing?'spielt':'pausiert')+' · gäste: '+ppl+(A?' · du hast gastgeber-rechte':'')+'</div>':'nichts läuft';
 document.getElementById('queue').innerHTML=Q.map((t,i)=>row(t,(t.src=='jam'&&t.sn?'<span class="dim">'+esc(t.sn)+'</span>':'')+(A?'<button onclick="ctl(\'remove\','+i+')">✕</button>':''))).join('')||'<div class="dim">leer</div>'}
async function ctl(op,i){const id=i==null?null:Q[i].id;const r=await fetch(api('/api/ctl'),{method:'POST',body:JSON.stringify({op,id})});if(!r.ok)msg('geht nicht (keine rechte?)');setTimeout(load,400)}
let tm;function typed(){clearTimeout(tm);tm=setTimeout(search,400)}
let R=[];async function search(){const q=document.getElementById('q').value.trim();if(!q){document.getElementById('res').innerHTML='';return}
 const r=await fetch(api('/api/search','&q='+encodeURIComponent(q)));R=(await r.json()).results||[];
 document.getElementById('res').innerHTML=R.map((t,i)=>row(t,'<button onclick="add('+i+',true)">nächstes</button><button class="p" onclick="add('+i+',false)">+</button>')).join('')}
async function add(i,next){const r=await fetch(api('/api/add'),{method:'POST',body:JSON.stringify({t:R[i],next})});msg(r.ok?'„'+R[i].t+'“ hinzugefügt':'ging nicht');load()}
if(C&&N)go();
</script></body></html>"""
