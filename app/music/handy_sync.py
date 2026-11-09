# musicalist – Abgleich mit der Handy-App im WLAN (Hörprotokoll in beide Richtungen, auf Wunsch die Anmeldung).
#
# Ablauf: In den Einstellungen „handy koppeln“ → Code (8 Zeichen) + Adresse erscheinen für 3 Minuten. Das Handy findet
# den Rechner per mDNS (_musicalist._tcp, wenn zeroconf da ist) oder über die eingetippte Adresse.
# Koppeln = Diffie-Hellman (RFC-3526-Gruppe 14) + Code-Bestätigung in beide Richtungen → gemeinsamer Schlüssel je Gerät.
# Danach ist jede Anfrage verschlüsselt und signiert (HMAC-SHA256 als Stromchiffre + HMAC-Prüfsumme, nur stdlib).
# Abgleich nach Zeilen-Stand: jede Seite schickt ihre eigenen Einträge ab dem Stand, den die andere schon hat;
# doppelte (gleiches at + id) werden beim Zusammenführen übersprungen.
# Der Server läuft erst, wenn einmal gekoppelt wurde (Einstellung „handy_sync“). Port 37526/tcp.
import hashlib, hmac, json, os, secrets, socket, threading, time

import engine

PORT = 37526
DEVICES = os.path.join(engine.DATA, "handy.json")
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
        "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
        "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
        "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
        "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
        "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
G = 2
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # ohne 0/O/1/I


def _hm(key, *parts):
    h = hmac.new(key, digestmod=hashlib.sha256)
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.digest()


def _stream(key, nonce, n):
    out = bytearray()
    i = 0
    while len(out) < n:
        out += _hm(key, nonce, i.to_bytes(4, "big"))
        i += 1
    return bytes(out[:n])


def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big") if a else b""


def box(key, data):
    """Verschlüsseln + signieren: nonce(16) | daten ^ strom | hmac(32)."""
    ke, km = _hm(key, b"enc"), _hm(key, b"mac")
    nonce = secrets.token_bytes(16)
    ct = _xor(data, _stream(ke, nonce, len(data)))
    return nonce + ct + _hm(km, nonce, ct)


def unbox(key, blob):
    ke, km = _hm(key, b"enc"), _hm(key, b"mac")
    if len(blob) < 48:
        raise ValueError("zu kurz")
    nonce, ct, tag = blob[:16], blob[16:-32], blob[-32:]
    if not hmac.compare_digest(tag, _hm(km, nonce, ct)):
        raise ValueError("falsche signatur")
    return _xor(ct, _stream(ke, nonce, len(ct)))


def _int_bytes(x):
    return x.to_bytes(256, "big")


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))          # kein Paket – nur die Ausgangsadresse ermitteln
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return ips


class Server:
    def __init__(self, player):
        self.p = player
        self.httpd = None
        self.zc = None
        self.pairing = None        # {"code", "until", "pending": {A: (B, key)}}
        self.lock = threading.Lock()
        self.listeners = []        # fn() nach Koppeln/Abgleich (Einstellungen aktualisieren)
        self.error = None
        self.devices = self._load()

    # ----- Geräte -----
    def _load(self):
        try:
            with open(DEVICES) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        tmp = DEVICES + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(self.devices, f)
        os.replace(tmp, DEVICES)

    def remove(self, dev_id):
        with self.lock:
            self.devices.pop(dev_id, None)
            self._save()
        self._notify()

    def _notify(self):
        from gi.repository import GLib
        for fn in list(self.listeners):
            GLib.idle_add(lambda f=fn: f() and False)

    # ----- Server -----
    @property
    def running(self):
        return self.httpd is not None

    def start(self):
        if self.httpd is not None:
            return True
        from http.server import ThreadingHTTPServer
        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", PORT), self._handler())
        except OSError as e:
            self.error = f"port {PORT} belegt ({e.strerror})"
            engine.log(f"handy-abgleich: {self.error}")
            return False
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="handy-sync").start()
        threading.Thread(target=self._announce, daemon=True).start()
        self.error = None
        return True

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.zc is not None:
            try:
                self.zc.close()
            except Exception:  # noqa: BLE001
                pass
            self.zc = None

    def _announce(self):
        """mDNS-Eintrag, damit das Handy den Rechner ohne Adresse findet (zeroconf optional)."""
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError:
            return
        try:
            ips = local_ips()
            name = socket.gethostname().split(".")[0] or "pc"
            info = ServiceInfo("_musicalist._tcp.local.", f"musicalist {name}._musicalist._tcp.local.", port=PORT,
                               addresses=[socket.inet_aton(i) for i in ips], properties={"v": "1"},
                               server=f"{name}-musicalist.local.")
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            zc.register_service(info)
            self.zc = zc
        except Exception as e:  # noqa: BLE001
            engine.log(f"handy-abgleich mdns: {e}")

    def start_pairing(self):
        """Neuen Code für 3 Minuten. Startet den Server dauerhaft (Einstellung handy_sync)."""
        engine.set_setting("handy_sync", True)
        ok = self.start()
        code = "".join(secrets.choice(ALPHA) for _ in range(8))
        with self.lock:
            self.pairing = {"code": code, "until": time.time() + 180, "pending": {}}
        return ok, code[:4] + "-" + code[4:], local_ips()

    def stop_pairing(self):
        with self.lock:
            self.pairing = None

    # ----- Anfragen -----
    def _handler(self):
        srv = self
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code, obj):
                self._send(code, json.dumps(obj).encode())

            def do_GET(self):
                if self.path == "/hello":
                    self._json(200, {"app": "musicalist", "v": 1, "name": socket.gethostname().split(".")[0],
                                     "pairing": srv.pairing is not None and srv.pairing["until"] > time.time()})
                else:
                    self._json(404, {"error": "?"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n > 64 * 1024 * 1024:
                    return self._json(413, {"error": "zu groß"})
                body = self.rfile.read(n)
                try:
                    if self.path == "/pair":
                        return self._json(*srv.pair1(json.loads(body)))
                    if self.path == "/pair2":
                        return self._json(*srv.pair2(json.loads(body)))
                    if self.path == "/sync":
                        dev = srv.devices.get(self.headers.get("X-Dev", ""))
                        if dev is None:
                            return self._json(401, {"error": "unbekanntes gerät – neu koppeln"})
                        key = bytes.fromhex(dev["key"])
                        try:
                            req = json.loads(unbox(key, body))
                        except ValueError:
                            return self._json(401, {"error": "schlüssel passt nicht – neu koppeln"})
                        res = srv.sync(self.headers.get("X-Dev"), req)
                        return self._send(200, box(key, json.dumps(res, ensure_ascii=False).encode()),
                                          "application/octet-stream")
                except Exception as e:  # noqa: BLE001
                    engine.log(f"handy-abgleich: {e!r}")
                    return self._json(500, {"error": str(e)[:200]})
                self._json(404, {"error": "?"})

        return H

    def pair1(self, req):
        with self.lock:
            pr = self.pairing
            if pr is None or pr["until"] < time.time():
                return 403, {"error": "am pc zuerst „handy koppeln“ drücken"}
            A = int(req["A"], 16)
            if not 1 < A < P - 1:
                return 400, {"error": "ungültig"}
            b = secrets.randbits(256)
            B = pow(G, b, P)
            key = hashlib.sha256(_int_bytes(pow(A, b, P))).digest()
            pr["pending"][req["A"]] = (B, key, str(req.get("name") or "handy")[:40])
            code = pr["code"].encode()
            tag = _hm(code, b"srv", _int_bytes(A), _int_bytes(B)).hex()
        return 200, {"B": format(B, "x"), "tag": tag, "name": socket.gethostname().split(".")[0]}

    def pair2(self, req):
        with self.lock:
            pr = self.pairing
            if pr is None or req.get("A") not in pr["pending"]:
                return 403, {"error": "kopplung abgelaufen"}
            B, key, name = pr["pending"][req["A"]]
            want = _hm(pr["code"].encode(), b"cli", _int_bytes(int(req["A"], 16)), _int_bytes(B)).hex()
            if not hmac.compare_digest(want, str(req.get("tag"))):
                self.pairing = None              # falscher Code: Kopplung beenden (kein Durchprobieren)
                return 403, {"error": "code falsch"}
            dev_id = secrets.token_hex(8)
            self.devices[dev_id] = {"name": name, "key": key.hex(), "paired": time.time(), "last": None}
            self._save()
            self.pairing = None
        self._notify()
        return 200, {"id": dev_id}

    def sync(self, dev_id, req):
        """req: rows (eigene Einträge des Handys), have (Zeilen-Stand des PC-Protokolls, den das Handy hat),
        login (Anmeldung mitschicken)."""
        j = self.p.journal
        added = j.merge(req.get("rows") or [])
        rows, nxt, more = j.lines_from(int(req.get("have") or 0), limit=4000, skip_dev="handy")
        res = {"rows": rows, "next": nxt, "more": more, "added": added}
        fr = getattr(self.p, "friends", None)
        if fr is not None and isinstance(req.get("friends"), dict):
            try:
                fr.sync_in(req["friends"], dev_id)
                res["friends"] = fr.sync_out()
            except Exception as e:  # noqa: BLE001
                engine.log(f"handy-abgleich: freunde {e!r}")
        try:
            import jam
            res["jd"] = jam.device_id()           # eigene Marmelade-Kennung: das Handy gibt dem PC dann Rechte
        except Exception:  # noqa: BLE001
            pass
        if req.get("login"):
            res["cookie"] = engine.browser_cookie()
        with self.lock:
            d = self.devices.get(dev_id)
            if d is not None:
                d["last"] = time.time()
                d["got"] = d.get("got", 0) + added
                if isinstance(req.get("jd"), str) and 8 <= len(req["jd"]) <= 40:
                    d["jam"] = req["jd"]
                self._save()
        self._notify()
        return res
