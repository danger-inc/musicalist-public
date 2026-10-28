# musicalist – Engine: YouTube Music (ytmusicapi) + Wiedergabe über mpv (JSON-IPC) + MPRIS (Waybar, Medientasten,
# playerctl) + Anmeldung über die Zen-Sitzung. Keine GTK-Widgets hier, nur Logik.
#
# Stream-Adressen löst yt-dlp im Prozess auf (≈1,5 s); der nächste Titel wird schon während des laufenden
# vorgeladen, damit der Wechsel sofort geht. Zustand (Warteschlange, Lautstärke …) liegt in state.json.
import glob, importlib, importlib.util, math, re, zlib, sys, json, os, random, shutil, socket, sqlite3, subprocess, tempfile, threading, time

from gi.repository import Gio, GLib

import tui
import localmusic
import audiofx

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(HERE, "auth")
BROWSER_JSON = os.path.join(AUTH_DIR, "browser.json")   # Anmeldung für ytmusicapi
COOKIES_TXT = os.path.join(AUTH_DIR, "cookies.txt")      # Anmeldung für yt-dlp
STATE = os.path.join(HERE, "state.json")
SETTINGS = os.path.join(HERE, "settings.json")
HISTORY = os.path.join(HERE, "history.json")
LISTENS = os.path.join(HERE, "listens.json")     # langes Hörprotokoll für den Rückblick (nur lokal)
PINS = os.path.join(HERE, "offline_pins.json")  # von Hand für offline gemerkte Titel (nur lokal)
PLAYS = os.path.join(HERE, "plays.json")       # Wiedergaben je Titel (für „meistgehört“, nur lokal)
# Audiodateien bewusst außerhalb von rice-apps (wird gesichert/veröffentlicht) – lassen sich jederzeit neu laden
OFFLINE_DIR = os.path.join(GLib.get_user_data_dir(), "musicalist", "offline")   # eigener Hörverlauf (nur lokal, wird nie veröffentlicht)
DEFAULT_SETTINGS = {"last_playlist": None,   # [id, titel] der zuletzt benutzten Playlist
                    "hover": False,       # Vorschau-Karte am Bildschirmrand: standardmäßig aus
                    "background": False,  # Fenster zu → weiterspielen? Standard: nein, ganz beenden
                    "visual": "orbit",    # Modus der Seite „visuals“
                    "history_pinned": False,  # Hörverlauf-Leiste angeheftet
                    "history": True,          # Hörverlauf führen (aus = nichts wird gemerkt, Leiste weg)
                    "yt_history": True,       # Wiedergaben an YouTube melden (Verlauf, Statistik, Empfehlungen)
                    "desk": False,            # Anzeige dauerhaft auf dem Hintergrundbild
                    "desk_pos": "bottom",
                    "offline": True,          # meistgehörte Titel als Datei speichern (geht ohne Netz, startet sofort)
                    "offline_n": 25,
                    "offline_mb": 2048,       # Obergrenze für den Offline-Ordner in MB (0 = unbegrenzt)
                    "ytdlp_auto": True,       # yt-dlp wöchentlich aktualisieren (YouTube ändert ständig etwas)
                    "ytdlp_checked": 0,
                    "crossfade": 0,           # Überblendung in Sekunden (0 = aus)
                    "eq": {"on": False, "preset": "flach", "gains": [0] * 10, "pre": 0},
                    "local": True,            # lokale Musik (Ordner) in der Bibliothek zeigen
                    "local_dir": ""}          # leer = ~/Music          # wie viele     # wo: bottom / bottom-left / bottom-right / top-right / top-left


def setting(key):
    try:
        with open(SETTINGS) as f:
            return json.load(f).get(key, DEFAULT_SETTINGS.get(key))
    except (OSError, ValueError, AttributeError):
        return DEFAULT_SETTINGS.get(key)


def set_setting(key, value):
    try:
        with open(SETTINGS) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data[key] = value
    try:
        with open(SETTINGS + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(SETTINGS + ".tmp", SETTINGS)
    except OSError:
        pass
IS_WIN = os.name == "nt"
RUNTIME = tempfile.gettempdir() if IS_WIN else GLib.get_user_runtime_dir()
MPV_SOCK = r"\\.\pipe\rice-music-mpv" if IS_WIN else RUNTIME + "/rice-music-mpv.sock"
MPV_SOCK2 = r"\\.\pipe\rice-music-mpv2" if IS_WIN else RUNTIME + "/rice-music-mpv2.sock"    # Standby für Überblendung


def open_url(url):
    """Adresse im Standardbrowser öffnen."""
    if IS_WIN:
        os.startfile(url)
    else:
        subprocess.Popen(["xdg-open", url], start_new_session=True)
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
PLAY_NEEDS_LOGIN = True     # abspielen nur mit bestätigter Google-Anmeldung


def log(msg):
    """Fehler ins Log ($XDG_RUNTIME_DIR/rice-music.log) – nie mit Zugangsdaten."""
    import sys
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def secs(text):
    """'3:34' → 214"""
    try:
        parts = [int(p) for p in str(text).split(":")]
    except ValueError:
        return 0
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def fmt(sec):
    sec = int(max(0, sec or 0))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def podcast_secs(text):
    """„25 min“, „1 hr 5 min“, „1:02:03“ → Sekunden."""
    if isinstance(text, (int, float)):
        return int(text)
    text = str(text or "")
    if ":" in text:
        return secs(text)
    h = re.search(r"(\d+)\s*(?:hr|h|std)", text)
    m = re.search(r"(\d+)\s*(?:min|m)\b", text)
    sec = re.search(r"(\d+)\s*s(?:ec)?\b", text)
    return (int(h.group(1)) * 3600 if h else 0) + (int(m.group(1)) * 60 if m else 0) + (int(sec.group(1)) if sec else 0)


def track(d):
    """Einheitliches Format aus Suche, Playlist, Album, Radio, Verlauf."""
    if not d or not d.get("videoId"):
        return None
    arts = d.get("artists") or []
    thumbs = d.get("thumbnails") or d.get("thumbnail") or []
    if isinstance(thumbs, dict):
        thumbs = thumbs.get("thumbnails", [])
    album = d.get("album")
    artist_id = next((a.get("id") for a in arts if a.get("id")), None) or d.get("artistId")
    return {"videoId": d["videoId"], "title": d.get("title") or "?",
            "artistId": artist_id, "albumId": (album.get("id") if isinstance(album, dict) else None) or d.get("albumId"),
            "artist": ", ".join(a["name"] for a in arts if a.get("name")) or d.get("author", ""),
            "album": album.get("name", "") if isinstance(album, dict) else (album or ""),
            "duration": d.get("duration_seconds") or secs(d.get("duration") or d.get("length") or 0),
            "thumb": thumbs[-1]["url"] if thumbs else "",
            "liked": d.get("likeStatus") == "LIKE", "setVideoId": d.get("setVideoId")}


# ---------- Anmeldung über Zen ----------
def browser_profiles():
    found = []
    if IS_WIN:
        appdata = os.environ.get("APPDATA", "")
        for base in ("zen/Profiles", "Mozilla/Firefox/Profiles", "librewolf/Profiles"):
            found += glob.glob(os.path.join(appdata, base, "*", "cookies.sqlite"))
        return found
    # Zen liegt je nach Version unter ~/.config/zen (XDG) oder ~/.zen, als Flatpak unter ~/.var/app
    for base in ("~/.config/zen", "~/.zen", "~/.var/app/app.zen_browser.zen/.zen",
                 "~/.var/app/app.zen_browser.zen/config/zen", "~/.mozilla/firefox", "~/.librewolf",
                 "~/.config/mozilla/firefox", "~/snap/firefox/common/.mozilla/firefox",
                 "~/.var/app/org.mozilla.firefox/.mozilla/firefox", "~/.var/app/io.gitlab.librewolf-community/.librewolf"):
        found += glob.glob(os.path.expanduser(base + "/*/cookies.sqlite"))
    return found


def read_cookies(db):
    """Cookies einer Browser-Datenbank lesen (Kopie, weil der Browser sie sperrt). Werte verlassen
    diese Funktion nur Richtung auth/ – sie werden nirgends angezeigt oder geloggt."""
    tmp = tempfile.mkdtemp(prefix="rice-music-")
    try:
        os.chmod(tmp, 0o700)
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                shutil.copy(db + suffix, os.path.join(tmp, "c.sqlite" + suffix))
        con = sqlite3.connect(os.path.join(tmp, "c.sqlite"))
        rows = con.execute("SELECT host, name, value, path, expiry, isSecure, lastAccessed FROM moz_cookies "
                           "WHERE host LIKE '%youtube.com' OR host LIKE '%google.com'").fetchall()
        con.close()
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fmusic.youtube.com%2F"


def ensure_deps(progress=None):
    """ytmusicapi/yt-dlp nachinstallieren, falls die Python-Umgebung sie nicht hat (kaputte/alte Installation)."""
    try:
        import ytmusicapi  # noqa: F401
        return
    except ImportError:
        pass
    if progress:
        progress("installiere ytmusicapi und yt-dlp (einmalig, dauert kurz) …")
    cmd = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade"]
    libs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pylibs")
    if IS_WIN:      # MSYS2-Python ist „externally managed“: Pakete wie der Installer nach <App>\pylibs
        cmd += ["--target", libs]
    r = subprocess.run(cmd + ["ytmusicapi>=1.10", "yt-dlp", "yt-dlp-ejs", "requests", "mutagen"],
                       capture_output=True, text=True, timeout=600)
    if IS_WIN and libs not in sys.path:
        sys.path.insert(0, libs)
    importlib.invalidate_caches()
    try:
        import ytmusicapi  # noqa: F401,F811
    except ImportError:
        out = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
        tail = ([l for l in out if "error" in l.lower()] or out or ["unbekannt"])[-1]
        log(f"pip: {r.returncode}: {' | '.join(out[-6:])}")
        raise RuntimeError(f"ytmusicapi fehlt und ließ sich nicht installieren ({tail.strip()[:200]})") from None


def explain(err):
    """Fehler in einem Satz, den man versteht (statt Python-/Netzwerk-Rohtext)."""
    e = str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__
    low = e.lower()
    if isinstance(err, LoginRequired):
        return e
    if any(k in low for k in ("name or service not known", "temporary failure in name", "network is unreachable",
                               "failed to resolve", "nodename nor servname", "connection refused",
                               "getaddrinfo", "no route to host", "timed out", "timeout")):
        return "keine verbindung zum internet"
    if "sign in to confirm" in low or "login required" in low or \
            ("http" in low and any(k in low for k in ("401", "403 ", "cookies"))):
        return "youtube verlangt anmeldung – einstellungen (,) → anmeldung neu einlesen"
    if any(k in low for k in ("unable to extract", "nsig", "player response", "signature")):
        return "youtube hat etwas geändert – yt-dlp wird aktualisiert (einstellungen: jetzt aktualisieren)"
    if "video unavailable" in low or "not available" in low or "private video" in low:
        return "titel nicht verfügbar (gesperrt oder entfernt)"
    if "429" in low or "too many requests" in low:
        return "youtube bremst gerade (zu viele anfragen) – gleich nochmal"
    return e[:160]


_ytdlp_lock = threading.Lock()


def ytdlp_version():
    """Installierte yt-dlp-Version aus den Paket-Metadaten – `import yt_dlp` kostet ~0,6 s (nur nötig beim Abspielen)."""
    mod = sys.modules.get("yt_dlp.version")
    if mod is not None and hasattr(mod, "__version__"):
        return mod.__version__
    try:                                    # version.py lesen, ohne das Paket zu importieren (~1 ms)
        spec = importlib.util.find_spec("yt_dlp")
        with open(os.path.join(os.path.dirname(spec.origin), "version.py")) as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", f.read())
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    try:
        from importlib.metadata import version
        return version("yt-dlp")
    except Exception:  # noqa: BLE001
        return "?"


def update_ytdlp(min_age=0):
    """yt-dlp per pip aktualisieren (blockierend – in einem Hintergrund-Thread aufrufen). min_age: nur wenn die
    letzte Prüfung so viele Sekunden her ist. Gibt (alt, neu) zurück, None wenn übersprungen; wirft bei Fehlern."""
    if not _ytdlp_lock.acquire(blocking=False):
        return None
    try:
        if min_age and time.time() - (setting("ytdlp_checked") or 0) < min_age:
            return None
        set_setting("ytdlp_checked", time.time())
        old = ytdlp_version()
        cmd = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade"]
        if IS_WIN:
            cmd += ["--target", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pylibs")]
        r = subprocess.run(cmd + ["yt-dlp", "yt-dlp-ejs"], capture_output=True, text=True, timeout=300)
        if r.returncode:
            out = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
            raise RuntimeError((out or ["pip-fehler"])[-1][:160])
        for m in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.") or m.startswith("yt_dlp_")]:
            del sys.modules[m]                 # beim nächsten import yt_dlp kommt die neue Version
        importlib.invalidate_caches()
        new = ytdlp_version()
        log(f"yt-dlp {old} → {new}")
        return old, new
    finally:
        _ytdlp_lock.release()


def login_from_browser(wait=240, progress=None):
    """Wie _login_once, öffnet aber bei fehlender/ungültiger Anmeldung den Browser zum Einloggen und
    wartet (bis `wait` s) darauf, dass dort die Anmeldung erscheint."""
    ensure_deps(progress)
    try:
        return _login_once()
    except (RuntimeError, ValueError, KeyError) as e:   # ValueError: JSONDecodeError ("Expecting value") bei ungültigen Cookies
        why = e
        log(f"anmeldung 1. versuch: {type(e).__name__}: {e}")
    logout()
    open_url(LOGIN_URL)
    if progress:
        progress(f"browser geöffnet, warte auf anmeldung … ({why})")
    end = time.time() + wait
    while time.time() < end:
        time.sleep(3)
        try:
            return _login_once()
        except (RuntimeError, ValueError, KeyError) as e:
            if str(e) != str(why):
                log(f"anmeldung: {type(e).__name__}: {e}")
            if progress and str(e) != str(why):
                progress(f"warte auf anmeldung … ({e})")
            why = e
            logout()
    raise RuntimeError(f"keine anmeldung erkannt ({why}) – im browser bei music.youtube.com einloggen und nochmal klicken")


# Diese Cookies braucht die Anmeldung wirklich. Hat der Browser sehr viele (Windows/Firefox: ~90, v. a. „ST-…“-Fragmente),
# lehnt Google den Cookie-Header mit „413 Request Entity Too Large“ (HTML statt JSON) ab.
_NEEDED = {"SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO", "SIDCC", "YSC", "PREF", "SOCS", "CONSENT",
           "VISITOR_INFO1_LIVE", "VISITOR_PRIVACY_METADATA", "__Secure-ROLLOUT_TOKEN"}
_MAX_COOKIES = 6000          # Bytes für den Cookie-Header (Google nimmt ca. 8 KB)


def _wichtig(name):
    return name in _NEEDED or re.match(r"__Secure-[13]P(SID|APISID)", name) is not None


def _slim(rows):
    rows = [r for r in rows if not r[1].startswith("ST-")]

    def yt(rs):
        return [r for r in rs if r[0].endswith("youtube.com")]
    # zu groß: unwichtige Cookies, größte zuerst, weglassen (die wichtigen bleiben immer)
    for r in sorted((r for r in yt(rows) if not _wichtig(r[1])), key=lambda r: -len(r[2])):
        if sum(len(x[1]) + len(x[2]) + 3 for x in yt(rows)) <= _MAX_COOKIES:
            break
        rows = [x for x in rows if x is not r]
    return rows


def _login_once():
    """Sucht das Browser-Profil mit YouTube-Anmeldung und legt die Zugangsdateien an.
    Gibt den Kontonamen zurück oder wirft RuntimeError."""
    best = None
    for db in browser_profiles():
        try:
            rows = read_cookies(db)
        except (OSError, sqlite3.Error):
            continue
        yt = [r for r in rows if r[0].endswith("youtube.com")]
        if any(r[1] in ("__Secure-3PAPISID", "SAPISID") for r in yt):
            last = max(r[6] for r in yt)
            if best is None or last > best[0]:
                best = (last, rows)
    if best is None:
        if not browser_profiles():
            raise RuntimeError("kein zen- oder firefox-profil gefunden")
        raise RuntimeError("keine youtube-anmeldung im browser gefunden – dort erst bei music.youtube.com einloggen")
    rows = _slim(best[1])
    os.makedirs(AUTH_DIR, mode=0o700, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    yt = {}
    for host, name, value, *_ in rows:
        if host.endswith("youtube.com"):
            yt[name] = value
    headers = {"cookie": "; ".join(f"{k}={v}" for k, v in yt.items()), "x-goog-authuser": "0",
               # Platzhalter: ytmusicapi erkennt Browser-Anmeldung nur an "SAPISIDHASH" und berechnet
               # den echten Wert bei jeder Anfrage selbst aus dem Cookie
               "authorization": "SAPISIDHASH 0_0",
               "origin": "https://music.youtube.com", "x-origin": "https://music.youtube.com",
               "user-agent": UA, "accept": "*/*", "accept-language": "de-DE,de;q=0.9,en;q=0.8",
               "content-type": "application/json"}
    lines = ["# Netscape HTTP Cookie File"]
    for host, name, value, path, expiry, secure, _ in rows:
        exp = int(expiry // 1000) if expiry > 1e11 else int(expiry)  # Firefox speichert teils ms
        lines.append("\t".join([host, "TRUE" if host.startswith(".") else "FALSE", path or "/",
                                "TRUE" if secure else "FALSE", str(exp), name, value]))
    for path, content in ((BROWSER_JSON, json.dumps(headers)), (COOKIES_TXT, "\n".join(lines) + "\n")):
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(path + ".tmp", path)
    try:
        for versuch in range(3):          # Verbindungsabbrüche (Windows: Fehler 10054) sind oft einmalig
            try:
                return account_name()
            except Exception as err:  # noqa: BLE001
                if "onnection" not in f"{type(err).__name__} {err}" or versuch == 2:
                    raise
                time.sleep(1.5)
    except Exception as e:  # noqa: BLE001 – Google liefert bei ungültigen Cookies kein JSON
        if "onnection" in f"{type(e).__name__} {e}":
            raise RuntimeError("keine Verbindung zu music.youtube.com (Firewall, VPN oder Virenscanner blockiert Python?)") from None
        raise ValueError(f"anmeldung ungültig: {e}") from None


def browser_auth():
    """Zugangsdaten für ytmusicapi (auch ältere Dateien ohne authorization-Eintrag)."""
    with open(BROWSER_JSON) as f:
        headers = json.load(f)
    headers.setdefault("authorization", "SAPISIDHASH 0_0")
    return headers


def account_name():
    from ytmusicapi import YTMusic
    info = YTMusic(browser_auth()).get_account_info()
    return info.get("accountName") or info.get("channelHandle") or "angemeldet"


class LoginRequired(Exception):
    pass


_verified = None   # Zeitstempel der browser.json, für die die Anmeldung zuletzt bestätigt wurde


def require_login():
    """Wirft LoginRequired, solange keine bei Google bestätigte Anmeldung vorliegt (blockiert – nur im Thread).
    Bestätigt wird einmal pro Anmeldedatei; nach neuem Anmelden wird neu geprüft."""
    global _verified
    try:
        stamp = os.path.getmtime(BROWSER_JSON)
    except OSError:
        raise LoginRequired("zum abspielen erst mit google anmelden (tab bibliothek → konto)") from None
    if _verified == stamp:
        return
    try:
        from ytmusicapi import YTMusic
        info = YTMusic(browser_auth()).get_account_info()
        ok = bool(info.get("accountName") or info.get("channelHandle"))
    except Exception:  # noqa: BLE001 – abgelaufene/kaputte Anmeldung
        ok = False
    if not ok:
        raise LoginRequired("anmeldung nicht bestätigt – bitte neu mit google anmelden")
    _verified = stamp


def logout():
    for p in (BROWSER_JSON, COOKIES_TXT):
        try:
            os.unlink(p)
        except OSError:
            pass


# ---------- YouTube Music ----------
class Music:
    """Dünne Hülle um ytmusicapi (alle Aufrufe blockieren – nur aus Threads benutzen)."""

    def __init__(self):
        self._yt = None
        self._yt_lock = threading.RLock()
        self.authed = False
        self.auth_error = None

    @property
    def yt(self):
        with self._yt_lock:             # mehrere Threads (Suche, Vorschläge, Bibliothek) starten gleichzeitig
            return self._make_yt()

    def _make_yt(self):
        # Sprache Englisch lassen: ytmusicapi erkennt Ergebnistypen nur dann sicher
        if self._yt is None:
            from ytmusicapi import YTMusic
            self.authed, self.auth_error = False, None
            if os.path.exists(BROWSER_JSON):
                try:
                    self._yt = YTMusic(browser_auth(), location="DE")
                    self.authed = True
                except Exception as e:  # noqa: BLE001 – kaputte Anmeldung: ohne weiter (Suche, Radio gehen)
                    self.auth_error = str(e)
                    log(f"anmeldung: {e}")
            if self._yt is None:
                self._yt = YTMusic(location="DE")
        return self._yt

    def reset(self):
        self._yt = None

    def search(self, q, kind):
        # limit 20: passt in eine Antwort (~0,4 s) – 40 braucht eine zweite Anfrage und dauert ~1,6 s
        flt = {"songs": "songs", "alben": "albums", "playlists": "playlists", "künstler": "artists",
               "videos": "videos", "podcasts": "podcasts"}[kind]
        return self.yt.search(q, filter=flt, limit=20)

    def search_albums(self, q):
        """Die besten Alben zur Suche (für den Abschnitt „alben“ unter den Titeln)."""
        return self.yt.search(q, filter="albums", limit=6)[:5]

    def top_result(self, q):
        """Bester Treffer der ungefilterten Suche (Titel, Künstler, Album …) oder None."""
        for r in self.yt.search(q, limit=1):
            if r.get("category") == "Top result":
                return r
        return None

    def suggestions(self, q):
        return self.yt.get_search_suggestions(q)

    def add_to_playlist(self, pid, vids):
        """(hinzugefügt, schon drin) – Anzahlen. Vorher Abgleich mit dem Inhalt der Playlist."""
        have = set()
        try:
            d = self.yt.get_playlist(pid, limit=None)
            have = {t.get("videoId") for t in d.get("tracks", []) if t.get("videoId")}
        except Exception:  # noqa: BLE001 – ohne Abgleich bleibt die Duplikat-Antwort der API
            pass
        new = [v for i, v in enumerate(vids) if v not in have and v not in vids[:i]]
        dup = len(vids) - len(new)
        if not new:
            return 0, dup
        res = self.yt.add_playlist_items(pid, new, duplicates=False)
        if isinstance(res, dict) and res.get("status") == "STATUS_SUCCEEDED":
            return len(new), dup
        if isinstance(res, dict) and "duplicate" in json.dumps(res).lower():
            return 0, len(vids)
        raise RuntimeError(str(res)[:160])

    def create_playlist(self, title, vids):
        pid = self.yt.create_playlist(title, "", privacy_status="PRIVATE", video_ids=vids or None)
        if not isinstance(pid, str):
            raise RuntimeError(str(pid)[:160])
        return pid

    # ----- eigene Playlists verwalten -----
    def rename_playlist(self, pid, title):
        res = self.yt.edit_playlist(pid, title=title)
        if isinstance(res, dict) and res.get("status") not in (None, "STATUS_SUCCEEDED"):
            raise RuntimeError(str(res)[:160])

    def delete_playlist(self, pid):
        res = self.yt.delete_playlist(pid)
        if isinstance(res, dict) and res.get("status") not in (None, "STATUS_SUCCEEDED"):
            raise RuntimeError(str(res)[:160])

    def remove_from_playlist(self, pid, tracks):
        vids = [{"videoId": t["videoId"], "setVideoId": t["setVideoId"]} for t in tracks if t.get("setVideoId")]
        if not vids:
            raise RuntimeError("diese playlist lässt sich nicht bearbeiten")
        res = self.yt.remove_playlist_items(pid, vids)
        if isinstance(res, dict) and res.get("status") not in (None, "STATUS_SUCCEEDED"):
            raise RuntimeError(str(res)[:160])

    # ----- Künstler abonnieren, neue Veröffentlichungen -----
    def subscribe(self, channel_id, on=True):
        (self.yt.subscribe_artists if on else self.yt.unsubscribe_artists)([channel_id])

    def subscriptions(self):
        return [{"id": r.get("browseId") or r.get("channelId"), "title": r.get("artist") or "?",
                 "sub": str(r.get("subscribers") or "")}
                for r in self.yt.get_library_subscriptions(limit=100) if r.get("browseId") or r.get("channelId")]

    def new_releases(self, limit_artists=25):
        """Neueste Alben/Singles der abonnierten Künstler (neuestes Jahr zuerst)."""
        from concurrent.futures import ThreadPoolExecutor
        subs = self.subscriptions()[:limit_artists]

        def one(a):
            try:
                d = self.yt.get_artist(a["id"])
            except Exception as e:  # noqa: BLE001
                log(f"neu von {a['title']}: {str(e)[:80]}")
                return []
            out = []
            for key in ("albums", "singles"):
                for r in (d.get(key) or {}).get("results", []):
                    if r.get("browseId"):
                        out.append({"id": r["browseId"], "title": r.get("title") or "?", "artist": a["title"],
                                    "year": str(r.get("year") or "0")})
            return out
        with ThreadPoolExecutor(5) as ex:
            rows = [r for part in ex.map(one, subs) for r in part]
        rows.sort(key=lambda r: r["year"], reverse=True)
        return [{"id": r["id"], "title": r["title"], "sub": f"{r['artist']} · {r['year']}"} for r in rows[:30]]

    # ----- Podcasts -----
    def podcast(self, pid):
        d = self.yt.get_podcast(pid, limit=100)
        name = (d.get("author") or {}).get("name") or ""
        out = []
        for e in d.get("episodes", []):
            if not e.get("videoId"):
                continue
            thumbs = e.get("thumbnails") or []
            out.append({"videoId": e["videoId"], "title": e.get("title") or "?", "artist": name,
                        "artistId": None, "albumId": None, "album": d.get("title", ""),
                        "duration": podcast_secs(e.get("duration")), "thumb": thumbs[-1]["url"] if thumbs else "",
                        "liked": False, "setVideoId": None, "podcast": True,
                        "note": e.get("date") or ""})
        return d.get("title", ""), out

    def podcast_library(self):
        return [{"id": r.get("podcastId") or r.get("browseId"), "title": r.get("title") or "?",
                 "sub": (r.get("author") or {}).get("name", "") if isinstance(r.get("author"), dict)
                 else str(r.get("author") or "")}
                for r in self.yt.get_library_podcasts(limit=50) if r.get("podcastId") or r.get("browseId")]

    def playlist(self, pid):
        if pid == "LM":  # Lieblingssongs
            d = self.yt.get_liked_songs(limit=500)
        else:
            d = self.yt.get_playlist(pid, limit=500)
        return d.get("title", ""), [t for t in map(track, d.get("tracks", [])) if t]

    def album(self, bid):
        d = self.yt.get_album(bid)
        thumb = (d.get("thumbnails") or [{}])[-1].get("url", "")
        out = []
        for t in d.get("tracks", []):
            t = track(t)
            if t:
                t["album"] = t["album"] or d.get("title", "")
                t["thumb"] = t["thumb"] or thumb
                out.append(t)
        return d.get("title", ""), out

    def artist(self, cid):
        """Künstlerseite: Name, Abonnenten, Top-Titel, Alben, Singles, ähnliche Künstler."""
        d = self.yt.get_artist(cid)
        songs = d.get("songs") or {}
        tracks = [t for t in map(track, songs.get("results", [])) if t]

        def coll(key):
            return [{"id": r.get("browseId"), "title": r.get("title") or "?",
                     "sub": str(r.get("year") or r.get("subscribers") or "")}
                    for r in (d.get(key) or {}).get("results", []) if r.get("browseId")]
        return {"name": d.get("name", ""), "subscribers": d.get("subscribers") or "", "tracks": tracks,
                "all_songs": songs.get("browseId"), "albums": coll("albums"), "singles": coll("singles"),
                "related": coll("related"), "radio": d.get("radioId"), "shuffle": d.get("shuffleId"),
                "channelId": d.get("channelId"), "subscribed": bool(d.get("subscribed"))}

    def watch_list(self, pid):
        """Mix/Radio-Playlist (RDEM…) – geht nicht über get_playlist."""
        d = self.yt.get_watch_playlist(playlistId=pid, limit=50)
        return "radio", [t for t in map(track, d.get("tracks", [])) if t]

    def artist_id(self, name):
        """Künstler-ID per Suche (für Titel, die ohne ID gespeichert wurden)."""
        name = (name or "").split(",")[0].strip()
        for r in self.yt.search(name, filter="artists", limit=3) if name else []:
            if r.get("browseId"):
                return r["browseId"]
        return None

    # ----- Wiedergaben an YouTube melden (wie die Website: Verlauf, „diesen Monat gehört“, Empfehlungen) -----
    CPNA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

    def report_start(self, vid):
        """Wiedergabe beginnen (videostatsPlaybackUrl) → landet im YouTube-Verlauf. Gibt die Daten für
        die Hörzeit-Meldungen zurück."""
        yt = self.yt                  # meldet erst an (setzt authed)
        if not self.authed:
            return None
        song = yt.get_song(vid)
        pt = song.get("playbackTracking") or {}
        url = (pt.get("videostatsPlaybackUrl") or {}).get("baseUrl")
        if not url:
            return None
        cpn = "".join(random.choice(self.CPNA) for _ in range(16))
        r = self.yt._send_get_request(url, {"ver": 2, "c": "WEB_REMIX", "cpn": cpn})
        if r.status_code not in (200, 204):
            raise RuntimeError(f"youtube-verlauf: http {r.status_code}")
        return {"cpn": cpn, "wt": (pt.get("videostatsWatchtimeUrl") or {}).get("baseUrl")}

    def report_watch(self, rep, st, et, length, final=False):
        """Gehörte Zeit melden (videostatsWatchtimeUrl, Abschnitt st–et in Sekunden)."""
        if not rep or not rep.get("wt") or et <= st:
            return
        self.yt._send_get_request(rep["wt"], {
            "ver": 2, "c": "WEB_REMIX", "cpn": rep["cpn"], "st": f"{st:.3f}", "et": f"{et:.3f}",
            "cmt": f"{et:.3f}", "len": f"{length:.3f}", "state": "paused" if final else "playing",
            "volume": 100, "muted": 0, "final": 1 if final else 0})

    def artist_songs(self, cid):
        d = self.yt.get_artist(cid)
        songs = d.get("songs") or {}
        if songs.get("browseId"):
            return d.get("name", ""), [t for t in map(track, self.yt.get_playlist(songs["browseId"], limit=100)
                                                     .get("tracks", [])) if t]
        return d.get("name", ""), [t for t in map(track, songs.get("results", [])) if t]

    def library(self):
        pls = self.yt.get_library_playlists(limit=100)
        return [{"id": p["playlistId"], "title": p["title"], "count": p.get("count", "")} for p in pls]

    def editable_playlists(self):
        """Eigene Playlists (in die man Titel legen kann) – ohne Lieblingssongs/Episoden."""
        return [p for p in self.library() if p["id"] not in ("LM", "SE")]

    def history(self):
        return [t for t in map(track, self.yt.get_history()) if t]

    def radio(self, vid):
        d = self.yt.get_watch_playlist(videoId=vid, radio=True, limit=40)
        return [t for t in map(track, d.get("tracks", [])) if t]

    def lyrics(self, vid):
        """Songtext von YouTube Music: {"lyrics": [(sek, text)] oder str, "source"} oder None."""
        w = self.yt.get_watch_playlist(videoId=vid, limit=1)
        if not w.get("lyrics"):
            return None
        try:
            res = self.yt.get_lyrics(w["lyrics"], timestamps=True)
        except Exception:  # noqa: BLE001 – ältere Antworten ohne Zeitstempel
            res = self.yt.get_lyrics(w["lyrics"])
        if not res or not res.get("lyrics"):
            return None
        lyr = res["lyrics"]
        if not isinstance(lyr, str):
            lyr = [(ln.start_time / 1000, ln.text) for ln in lyr]
        return {"lyrics": lyr, "source": (res.get("source") or "youtube music").lower()}

    def rate(self, vid, like):
        self.yt.rate_song(vid, "LIKE" if like else "INDIFFERENT")


# ---------- Songtexte ----------
import re as _re

_LRC = _re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
# Zusätze, die bei der Suche stören (Länge prüft LRCLIB ohnehin): „(Radio Edit)“, „- Remastered 2011“, „(feat. X)“
_NOISE = _re.compile(r"\s*[\(\[](?:feat\.?|ft\.?|with|radio edit|remaster(?:ed)?[^\)\]]*|official[^\)\]]*|"
                     r"explicit|clean|single version|album version|edit)[^\)\]]*[\)\]]|\s+-\s+remaster(?:ed)?.*$",
                     _re.I)


def parse_lrc(text):
    out = []
    for line in (text or "").splitlines():
        m = _LRC.match(line.strip())
        if m:
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    return out


class Lyrics:
    """Songtexte mit Zeitstempeln: zuerst LRCLIB (frei, Zeitstempel passen zur Länge des Titels, ±2 s),
    sonst YouTube Music. Ergebnisse bleiben im Speicher; preload() holt sie schon beim Titelwechsel –
    nicht erst beim Klick auf „lyrics“. Ergebnis: {"lyrics": [(sek, text)] | str, "source", "synced"} oder None."""
    API = "https://lrclib.net/api"

    def __init__(self, music):
        self.music = music
        self.cache = {}            # videoId → Ergebnis (None = keins)
        self.lock = threading.Lock()
        self.waiting = {}          # videoId → threading.Event (läuft gerade)

    def _get_json(self, path, params):
        import urllib.parse, urllib.request
        url = f"{self.API}/{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "musicalist (https://github.com/danger-inc/musicalist)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=6) as r:
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                code = getattr(e, "code", None)
                if code == 404:
                    return None
                if code in (429, 503) and attempt < 2:   # überlastet: kurz warten
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise
        return None

    def lrclib(self, t, dur):
        title = _NOISE.sub("", t["title"]).strip() or t["title"]
        artist = (t.get("artist") or "").split(",")[0].split(" & ")[0].strip()
        found = self._get_json("search", {"track_name": title, "artist_name": artist}) or []
        if not found and artist:
            found = self._get_json("search", {"q": f"{artist} {title}"}) or []
        best = None
        for r in found:
            if not (r.get("syncedLyrics") or r.get("plainLyrics")) or r.get("instrumental"):
                continue
            diff = abs((r.get("duration") or 0) - dur) if dur else 0
            if dur and diff > 2.5:
                continue                        # andere Fassung → Zeitstempel würden nicht passen
            score = (0 if r.get("syncedLyrics") else 1, diff)
            if best is None or score < best[0]:
                best = (score, r)
        if not best:
            return None
        r = best[1]
        if r.get("syncedLyrics"):
            lines = parse_lrc(r["syncedLyrics"])
            if lines:
                return {"lyrics": lines, "source": "lrclib", "synced": True}
        return {"lyrics": r["plainLyrics"], "source": "lrclib", "synced": False}

    def fetch(self, t, dur=0):
        """Blockiert (nur im Thread). Mehrfachaufrufe für denselben Titel warten auf den ersten."""
        vid = t["videoId"]
        with self.lock:
            if vid in self.cache:
                return self.cache[vid]
            ev = self.waiting.get(vid)
            mine = ev is None
            if mine:
                ev = self.waiting[vid] = threading.Event()
        if not mine:
            ev.wait(30)
            return self.cache.get(vid)
        res = None
        try:
            dur = dur or t.get("duration") or 0
            try:
                res = self.lrclib(t, dur)
            except Exception as e:  # noqa: BLE001
                log(f"lrclib: {str(e)[:100]}")
            if (not res or not res["synced"]) and not localmusic.is_local(vid):
                try:
                    yt = self.music.lyrics(vid)
                except Exception as e:  # noqa: BLE001
                    yt = None
                    log(f"lyrics yt: {str(e)[:100]}")
                if yt:
                    yt["synced"] = not isinstance(yt["lyrics"], str)
                    if yt["synced"] or not res:
                        res = yt
        finally:
            with self.lock:
                self.cache[vid] = res
                if len(self.cache) > 200:
                    self.cache.pop(next(iter(self.cache)))
                self.waiting.pop(vid, None)
            ev.set()
        return res

    def cached(self, vid):
        return self.cache.get(vid, False)      # False = noch nicht geladen

    def preload(self, tracks):
        """Im Hintergrund nacheinander laden (aktueller Titel zuerst)."""
        todo = [t for t in tracks if t and t["videoId"] not in self.cache]
        if todo:
            threading.Thread(target=lambda: [self.fetch(t) for t in todo], daemon=True).start()


# ---------- Stream-Adressen ----------
def js_runtimes():
    """JavaScript für yt-dlp (YouTube-Signaturen): nodejs ≥ 20 vom System, sonst deno aus der eigenen Umgebung
    (pip-Paket „deno“, kommt mit install.sh) oder vom System. Ubuntu 24.04 hat z. B. nur nodejs 18."""
    import sys
    node = shutil.which("node")
    if node:
        try:
            out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5).stdout
            if int(out.strip().lstrip("v").split(".")[0]) >= 20:
                return {"node": {}}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    deno = os.path.join(os.path.dirname(sys.executable), "deno")
    deno = deno if os.access(deno, os.X_OK) else shutil.which("deno")
    if deno:
        return {"deno": {"path": deno}}
    return {"node": {}}


class Resolver:
    """Stream-Adressen über yt-dlp. Zwei getrennte Wege, damit sich nichts gegenseitig blockiert:
    - fast: ohne Anmeldung (~1,5 s, Opus ~130 kbps) – für den Titel, den man gerade anklickt
    - hq:   mit Anmeldung (~4–6 s, Premium-Opus 256 kbps) – nur im Hintergrund zum Vorladen
    Vorgeladene hq-Adressen ersetzen fast-Einträge im Zwischenspeicher (4 h gültig)."""

    def __init__(self):
        self.cache = {}
        self.locks = {"fast": threading.Lock(), "warm": threading.Lock(), "hq": threading.Lock(), "m4a": threading.Lock()}
        self.ydls = {}
        self.queue_lock = threading.Lock()
        self.wanted = []
        self.worker = None
        self.inflight = {}          # videoId → threading.Event: wird gerade (schnell) aufgelöst
        self.warm_lock = threading.Lock()
        self.warm_next = None       # Hover: zuletzt gewünschter Titel (neuester gewinnt)
        self.warm_busy = False
        self.local = None           # vid → Pfad einer gespeicherten Datei (Offline), sonst None

    def reset(self):
        self.ydls = {}

    def ydl(self, kind):
        import yt_dlp
        cookies = COOKIES_TXT if kind == "hq" and os.path.exists(COOKIES_TXT) else None
        key = (kind, cookies)
        if key not in self.ydls:
            opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                    "format": "bestaudio[ext=m4a]/140/bestaudio" if kind == "m4a" else "bestaudio/best",
                    "js_runtimes": js_runtimes(), "skip_download": True}
            if cookies:
                opts["cookiefile"] = cookies
            self.ydls[key] = yt_dlp.YoutubeDL(opts)
        return self.ydls[key]

    def cached(self, vid):
        hit = self.cache.get(vid)
        return hit[1] if hit and hit[0] > time.time() else None

    def _extract(self, vid, kind):
        with self.locks[kind]:  # ein yt-dlp-Objekt ist nicht threadsicher
            info = self.ydl(kind).extract_info(f"https://music.youtube.com/watch?v={vid}", download=False)
        res = {"url": info["url"], "ua": (info.get("http_headers") or {}).get("User-Agent", UA),
               "abr": info.get("abr"), "codec": info.get("acodec", ""), "duration": info.get("duration"),
               "proto": info.get("protocol", ""),
               "kind": kind if kind in ("hq", "m4a") else "fast"}
        old = self.cached(vid)
        if not (old and old.get("kind") == "hq" and kind != "hq"):
            self.cache[vid] = (time.time() + 4 * 3600, res)
            if len(self.cache) > 300:                  # abgelaufene und älteste Adressen loswerden
                now = time.time()
                for k in [k for k, (exp, _r) in self.cache.items() if exp < now] or [next(iter(self.cache))]:
                    self.cache.pop(k, None)
        return res

    def _fast(self, vid, kind="fast"):
        """Schneller Weg; läuft für denselben Titel schon einer (z. B. vom Überfahren), auf den warten.
        kind "warm" = eigenes yt-dlp-Objekt fürs Überfahren, damit ein Klick auf einen anderen Titel nie wartet."""
        with self.queue_lock:
            ev = self.inflight.get(vid)
            mine = ev is None
            if mine:
                ev = self.inflight[vid] = threading.Event()
        if not mine:
            ev.wait(20)
            hit = self.cached(vid)
            if hit:
                return hit
            return self._extract(vid, kind)
        try:
            return self._extract(vid, kind)
        finally:
            with self.queue_lock:
                self.inflight.pop(vid, None)
            ev.set()

    def local_info(self, vid):
        if localmusic.is_local(vid):             # Datei aus dem Musikordner
            f = localmusic.path_of(vid)
            if not os.path.exists(f):
                raise RuntimeError(f"datei fehlt: {os.path.basename(f)}")
            return {"url": f, "ua": UA, "abr": None, "codec": os.path.splitext(f)[1].lstrip("."), "duration": None,
                    "kind": "offline"}
        f = self.local(vid) if self.local else None
        if not f:
            return None
        return {"url": f, "ua": UA, "abr": None, "codec": os.path.splitext(f)[1].lstrip("."), "duration": None,
                "kind": "offline"}

    def get(self, vid, failed=None):
        """Für sofortiges Abspielen: gespeicherte Datei, Zwischenspeicher, sonst der schnelle Weg (Notfall: hq).
        failed = Art ("fast"/"hq") der Adresse, die mpv nicht laden konnte → es wird der andere Weg versucht."""
        loc = self.local_info(vid)
        if loc:
            return loc
        if failed == "fast" and os.path.exists(COOKIES_TXT):
            return self._extract(vid, "hq")
        if failed in ("fast", "hq"):
            return self._extract(vid, "m4a")     # anderes Format (AAC statt Opus)
        if failed == "m4a":
            return self._extract(vid, "fast")
        hit = self.cached(vid)
        if hit:
            return hit
        try:
            return self._fast(vid)
        except Exception:  # noqa: BLE001 – z. B. altersbeschränkt: mit Anmeldung versuchen
            if not os.path.exists(COOKIES_TXT):
                raise
            return self._extract(vid, "hq")

    def warm(self, vid):
        """Maus liegt auf einem Titel: Adresse schon mal (schnell) holen – der Klick spielt dann sofort.
        Immer nur einer gleichzeitig; kommt ein neuer Wunsch, gewinnt der neueste."""
        if not vid or self.cached(vid) or vid in self.inflight or (self.local and self.local(vid)) \
                or localmusic.is_local(vid):
            return
        with self.warm_lock:
            self.warm_next = vid
            if self.warm_busy:
                return
            self.warm_busy = True

        def loop():
            while True:
                with self.warm_lock:
                    v, self.warm_next = self.warm_next, None
                    if v is None:
                        self.warm_busy = False
                        return
                if not self.cached(v):
                    try:
                        self._fast(v, "warm")
                    except Exception as e:  # noqa: BLE001
                        log(f"vorwärmen {v}: {str(e)[:100]}")
        threading.Thread(target=loop, daemon=True).start()

    def prefetch(self, vids):
        """Im Hintergrund nacheinander vorladen (neueste Wunschliste gewinnt)."""
        kind = "hq" if os.path.exists(COOKIES_TXT) else "fast"
        with self.queue_lock:
            self.wanted = [v for v in vids if not (self.cached(v) and self.cached(v).get("kind") == kind)
                           and not (self.local and self.local(v)) and not localmusic.is_local(v)]
            if self.worker and self.worker.is_alive():
                return
            self.worker = threading.Thread(target=self._prefetch_loop, args=(kind,), daemon=True)
            self.worker.start()

    def _prefetch_loop(self, kind):
        while True:
            with self.queue_lock:
                if not self.wanted:
                    return
                vid = self.wanted.pop(0)
            try:
                self._extract(vid, kind)
            except Exception as e:  # noqa: BLE001
                log(f"vorladen {vid}: {str(e)[:120]}")


# ---------- mpv ----------
class PipeSock:
    """mpv-IPC unter Windows (Named Pipe) mit der Socket-Schnittstelle sendall/recv. Ein Handle liest nur,
    ein zweites schreibt nur: ein wartendes ReadFile würde auf demselben Handle jedes WriteFile blockieren."""

    def __init__(self, path):
        self.rd = open(path, "r+b", buffering=0)
        self.wr = open(path, "r+b", buffering=0)

    def sendall(self, data, reader=False):
        f = self.rd if reader else self.wr
        f.write(data)

    def recv(self, n):
        return self.rd.read(n)


_mpv_ver = None


def mpv_version():
    """(Haupt, Neben) von `mpv --version`, z. B. (0, 37) – (0, 0) wenn nicht lesbar. Einmal pro Prozess."""
    global _mpv_ver
    if _mpv_ver is None:
        _mpv_ver = (0, 0)
        try:
            out = subprocess.run(["mpv", "--version"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"mpv\s+v?(\d+)\.(\d+)", out)
            if m:
                _mpv_ver = (int(m.group(1)), int(m.group(2)))
        except (OSError, subprocess.SubprocessError):
            pass
    return _mpv_ver


class Mpv:
    """mpv per JSON-IPC. Stirbt der Prozess (Absturz, Speichermangel, kill), startet er neu und on_restart() darf
    die Wiedergabe fortsetzen; nach 3 Neustarts in 2 Minuten wird aufgegeben (on_event "mpv-dead")."""

    def __init__(self, on_event, on_restart=None, path=None):
        self.on_event = on_event
        self.on_restart = on_restart
        self.path = path or MPV_SOCK
        self.props = {}            # zuletzt gemeldete Eigenschaften (time-pos, duration …) + "loaded"
        self.sock = None
        self.lock = threading.Lock()
        self.closing = False
        self.restarts = []
        self._start()

    def _start(self):
        if not IS_WIN:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        self.sock = None
        self.props = {}
        self.proc = tui.spawn_watch(["mpv", "--idle=yes", "--no-video", "--no-terminal", "--ytdl=no",
                                     "--audio-display=no", f"--input-ipc-server={self.path}",
                                     "--audio-client-name=musicalist", "--cache=yes", "--demuxer-max-bytes=64MiB",
                                     "--gapless-audio=weak", "--replaygain=track"] +
                                    ([f"--log-file={os.path.join(os.environ.get('TEMP', '.'), 'rice-mpv.log')}",
                                      "--msg-level=all=warn,ffmpeg=v"] if IS_WIN else []),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(300):
            try:
                if IS_WIN:
                    self.sock = PipeSock(self.path)
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.path)
                    self.sock = s
                break
            except OSError:
                time.sleep(0.01)
        if self.sock is None:
            raise RuntimeError("mpv startet nicht")
        # Beobachter am LESE-Handle anmelden (Ereignisse gehen an den Client, der sie bestellt hat)
        for i, p in enumerate(("time-pos", "duration", "pause", "volume", "idle-active", "paused-for-cache")):
            data = (json.dumps({"command": ["observe_property", i + 1, p]}) + "\n").encode()
            if IS_WIN:
                self.sock.sendall(data, reader=True)
            else:
                self.sock.sendall(data)
        threading.Thread(target=self.read, args=(self.sock,), daemon=True).start()

    def _died(self, sock):
        if self.closing or sock is not self.sock:
            return False
        try:
            self.proc.wait(timeout=1)               # Zombie einsammeln
        except Exception:  # noqa: BLE001 – hängt er noch, halb tot: sicherheitshalber beenden
            try:
                self.proc.kill()
            except OSError:
                pass
        now = time.time()
        self.restarts = [t for t in self.restarts if now - t < 120]
        log(f"mpv beendet (Code {self.proc.returncode}) – Neustart {len(self.restarts) + 1}/3")
        if len(self.restarts) >= 3:
            self.on_event({"event": "mpv-dead"})
            return False
        self.restarts.append(now)
        try:
            self._start()
        except Exception as e:  # noqa: BLE001
            log(f"mpv-neustart: {e}")
            self.on_event({"event": "mpv-dead"})
            return False
        if self.on_restart:
            self.on_restart()
        return False

    def cmd(self, *args):
        data = (json.dumps({"command": list(args)}) + "\n").encode()
        with self.lock:
            try:
                self.sock.sendall(data)
            except OSError:
                pass

    def set(self, prop, value):
        self.cmd("set_property", prop, value)

    def loadfile(self, url, start=0):
        """Datei laden (ersetzt den laufenden Titel), optional ab `start` Sekunden. Die Parameterliste von
        `loadfile` hat sich geändert: ab mpv 0.38 mit Index (-1), davor ohne – falsche Form = „invalid parameter“."""
        if not start:
            self.cmd("loadfile", url, "replace")
        elif mpv_version() >= (0, 38):
            self.cmd("loadfile", url, "replace", -1, f"start={start}")
        else:
            self.cmd("loadfile", url, "replace", f"start={start}")

    def read(self, sock):
        buf = b""
        while True:
            try:
                chunk = sock.recv(65536)
            except OSError:
                chunk = b""
            if not chunk:
                GLib.idle_add(self._died, sock)
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "event" in msg:
                    GLib.idle_add(self.on_event, msg)

    def quit(self):
        self.closing = True
        self.cmd("quit")


# ---------- Player ----------
class History:
    """Lokaler Hörverlauf für die Verlaufsleiste: neueste zuerst, je Eintrag Titel + Zeitpunkt."""
    KEEP = 400

    def __init__(self):
        try:
            with open(HISTORY) as f:
                self.items = [x for x in json.load(f) if isinstance(x, dict) and x.get("videoId")]
        except (OSError, ValueError):
            self.items = []
        self._save_id = None

    def add(self, t):
        if not t or not t.get("videoId"):
            return False
        now = time.time()
        top = self.items[0] if self.items else None
        if top and top["videoId"] == t["videoId"] and now - top.get("at", 0) < 600:
            top["at"] = now                     # gleicher Titel gleich wieder (wiederholen/neu laden) = ein Eintrag
        else:
            keep = {k: t.get(k) for k in ("videoId", "title", "artist", "album", "duration", "thumb")}
            keep["at"] = now
            self.items.insert(0, keep)
            del self.items[self.KEEP:]
        if self._save_id is None:
            self._save_id = GLib.timeout_add_seconds(3, self.save)
        return True

    def remove(self, i):
        if 0 <= i < len(self.items):
            del self.items[i]
            self.save()

    def clear(self):
        self.items = []
        self.save()

    def save(self):
        self._save_id = None
        try:
            with open(HISTORY + ".tmp", "w") as f:
                json.dump(self.items, f, ensure_ascii=False)
            os.replace(HISTORY + ".tmp", HISTORY)
        except OSError:
            pass
        return False


class Stats:
    """Langes Hörprotokoll für den Rückblick: [Zeit, videoId, Titel, Künstler, Dauer]. Beim ersten Start aus dem
    Hörverlauf vorbelegt. Nur lokal; wer den Hörverlauf ausschaltet, protokolliert nichts."""
    KEEP = 60000

    def __init__(self, history):
        try:
            with open(LISTENS) as f:
                self.rows = [r for r in json.load(f) if isinstance(r, list) and len(r) == 5]
        except (OSError, ValueError):
            self.rows = [[x.get("at", 0), x["videoId"], x.get("title") or "?", x.get("artist") or "",
                          x.get("duration") or 0] for x in reversed(history.items)]
        self._save_id = None

    def add(self, t):
        if not t or not t.get("videoId"):
            return
        self.rows.append([time.time(), t["videoId"], t.get("title") or "?", t.get("artist") or "",
                          t.get("duration") or 0])
        del self.rows[:-self.KEEP]
        if self._save_id is None:
            self._save_id = GLib.timeout_add_seconds(10, self.save)

    def clear(self):
        self.rows = []
        self.save()

    def save(self):
        self._save_id = None
        try:
            with open(LISTENS + ".tmp", "w") as f:
                json.dump(self.rows, f, ensure_ascii=False)
            os.replace(LISTENS + ".tmp", LISTENS)
        except OSError:
            pass
        return False

    @staticmethod
    def rebuild(vid, title, artist, dur):
        """Spielbarer Titel aus einer Protokollzeile (Cover: Standardbild von YouTube)."""
        if localmusic.is_local(vid):
            return localmusic.make_track(localmusic.path_of(vid), (title, artist, "", dur))
        return {"videoId": vid, "title": title, "artist": artist, "artistId": None, "albumId": None, "album": "",
                "duration": dur, "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "liked": False,
                "setVideoId": None}

    def report(self, days=None, now=None):
        """Zahlen für einen Zeitraum (days=None: alles)."""
        now = now or time.time()
        lo = now - days * 86400 if days else 0
        rows = [r for r in self.rows if r[0] >= lo]
        titles, artists, hours, wdays, perday = {}, {}, [0] * 24, [0] * 7, {}
        secs_total = 0
        for at, vid, title, artist, dur in rows:
            e = titles.setdefault(vid, [0, title, artist, dur])
            e[0] += 1
            secs_total += dur or 0
            for a in [x.strip() for x in artist.split(",") if x.strip()]:
                artists[a] = artists.get(a, 0) + 1
            lt = time.localtime(at)
            hours[lt.tm_hour] += 1
            wdays[lt.tm_wday] += 1
            perday[(lt.tm_year, lt.tm_yday)] = perday.get((lt.tm_year, lt.tm_yday), 0) + 1
        first = min((r[0] for r in rows), default=now)
        span_days = max(1, min(days or 10 ** 6, int((now - first) / 86400) + 1))
        return {"plays": len(rows), "seconds": secs_total, "unique": len(titles), "artists_n": len(artists),
                "top_titles": sorted(([n, vid, t, a, d] for vid, (n, t, a, d) in titles.items()), reverse=True)[:10],
                "top_artists": sorted(((n, a) for a, n in artists.items()), reverse=True)[:10],
                "hours": hours, "wdays": wdays, "days_active": len(perday), "span_days": span_days}


class Offline:
    """Meistgehörte Titel offline: Wiedergaben werden gezählt (mit Halbwertszeit – was man länger nicht hört,
    rutscht von allein raus), die besten N liegen als Audiodatei in OFFLINE_DIR. Abgleich beim Start, alle 6 h
    und wenn ein Titel neu in die Spitze kommt; herausgefallene Dateien werden gelöscht."""
    HALF = 21 * 86400        # Halbwertszeit einer Wiedergabe
    MIN_SCORE = 1.5          # ≈ zweimal in letzter Zeit gehört – einmal reinhören reicht nicht

    def __init__(self, history):
        self.listeners = []
        self.lock = threading.Lock()
        self.busy, self.status, self.errors, self._again = False, "", {}, False
        self.current = None              # gerade geladener Titel
        try:
            with open(PLAYS) as f:
                self.plays = json.load(f)
        except (OSError, ValueError):
            self.plays = self._seed(history.items)
        try:
            with open(os.path.join(OFFLINE_DIR, "index.json")) as f:
                self.index = json.load(f)
        except (OSError, ValueError):
            self.index = {}
        self._save_id = self._sync_id = None
        try:
            with open(PINS) as f:
                self.pins = json.load(f)
        except (OSError, ValueError):
            self.pins = {}
        GLib.timeout_add_seconds(60, lambda: self.sync() and False)          # kurz nach dem Start
        GLib.timeout_add_seconds(6 * 3600, lambda: self.sync() or True)

    # ----- Zählen -----
    def _seed(self, items):
        """Beim ersten Mal aus dem bisherigen Hörverlauf vorbelegen."""
        plays = {}
        for it in sorted(items, key=lambda x: x.get("at", 0)):
            self._bump(plays, it, it.get("at") or time.time())
        return plays

    def _bump(self, plays, t, now):
        e = plays.get(t["videoId"])
        if e is None:
            e = plays[t["videoId"]] = {"s": 0.0, "n": 0, "last": now}
        e["s"] = e["s"] * 0.5 ** (max(0, now - e["last"]) / self.HALF) + 1
        e["n"] += 1
        e["last"] = now
        e["t"] = {k: t.get(k) for k in ("videoId", "title", "artist", "album", "duration", "thumb")}

    def score(self, e, now=None):
        return e["s"] * 0.5 ** (max(0, (now or time.time()) - e["last"]) / self.HALF)

    def count(self, t):
        """Eine Wiedergabe (aufgerufen zusammen mit dem Hörverlauf, also nach 5 s echtem Hören)."""
        if not t or not t.get("videoId"):
            return
        self._bump(self.plays, t, time.time())
        if self._save_id is None:
            self._save_id = GLib.timeout_add_seconds(5, self.save)
        if setting("offline") and t["videoId"] not in self.index and t["videoId"] in self.wanted_ids():
            if self._sync_id is None:            # neu in der Spitze → bald laden (gebündelt)
                self._sync_id = GLib.timeout_add_seconds(30, self._sync_soon)

    def _sync_soon(self):
        self._sync_id = None
        self.sync()
        return False

    def save(self):
        self._save_id = None
        now = time.time()
        if len(self.plays) > 2000:              # Bodensatz wegwerfen
            keep = sorted(self.plays.items(), key=lambda kv: -self.score(kv[1], now))[:1500]
            self.plays = dict(keep)
        try:
            with open(PLAYS + ".tmp", "w") as f:
                json.dump(self.plays, f, ensure_ascii=False)
            os.replace(PLAYS + ".tmp", PLAYS)
        except OSError:
            pass
        return False

    def top(self, n=None):
        """[(track, score, anzahl)] – die meistgehörten Titel, beste zuerst."""
        now = time.time()
        rows = [(e["t"], self.score(e, now), e["n"]) for e in self.plays.values() if e.get("t")]
        rows = [r for r in rows if r[1] >= self.MIN_SCORE]
        rows.sort(key=lambda r: -r[1])
        return self.fit_cap(rows[:n or setting("offline_n") or 25])

    EST_BPS = 20_000          # geschätzte Bytes pro Sekunde (Opus ≈ 160 kbit/s), solange die Datei nicht da ist

    def fit_cap(self, rows):
        """Speicherlimit (offline_mb): von der Spitze her auffüllen, was nicht mehr passt, entfällt."""
        cap = (setting("offline_mb") or 0) * 1_000_000
        if not cap:
            return rows
        out = []
        used = sum((self.index.get(v) or {}).get("size") or (t.get("duration") or 240) * self.EST_BPS
                   for v, t in self.pins.items())                 # gemerkte Titel belegen ihren Platz zuerst
        rows = [r for r in rows if r[0]["videoId"] not in self.pins]
        for r in rows:
            vid = r[0]["videoId"]
            size = (self.index.get(vid) or {}).get("size") or (r[0].get("duration") or 240) * self.EST_BPS
            if used + size > cap:
                continue                      # kürzere, weiter hinten liegende Titel dürfen noch hineinpassen
            used += size
            out.append(r)
        return out

    def wanted_ids(self):
        auto = [t["videoId"] for t, _s, _n in self.top()] if setting("offline") else []
        return list(self.pins) + auto

    # ----- von Hand gemerkt („offline speichern“): bleiben, bis man sie wieder entfernt -----
    PIN_MAX = 300

    def is_pinned(self, vid):
        return vid in self.pins

    def pin(self, tracks):
        """Titel dauerhaft offline legen. Gibt die Zahl neu gemerkter Titel zurück."""
        n = 0
        for t in tracks:
            vid = t.get("videoId")
            if not vid or localmusic.is_local(vid) or vid in self.pins or len(self.pins) >= self.PIN_MAX:
                continue
            self.pins[vid] = {k: t.get(k) for k in ("videoId", "title", "artist", "album", "duration", "thumb")}
            n += 1
        if n:
            self._save_pins()
            self.sync()
            self.emit()
        return n

    def unpin(self, vids):
        for vid in vids:
            self.pins.pop(vid, None)
        self._save_pins()
        self.sync()
        self.emit()

    def _save_pins(self):
        try:
            with open(PINS + ".tmp", "w") as f:
                json.dump(self.pins, f, ensure_ascii=False)
            os.replace(PINS + ".tmp", PINS)
        except OSError:
            pass

    def want_all(self):
        """Zu speichernde Titel: erst die gemerkten, dann die meistgehörten (Limit gilt für den Rest)."""
        pinned = list(self.pins.values())
        auto = [t for t, _s, _n in self.top() if t["videoId"] not in self.pins] if setting("offline") else []
        return pinned + auto

    # ----- Dateien -----
    def path(self, vid):
        e = self.index.get(vid)
        if e:
            f = os.path.join(OFFLINE_DIR, e["file"])
            if os.path.exists(f):
                return f
        return None

    def has(self, vid):
        return vid in self.index

    def size(self):
        return sum(e.get("size", 0) for e in self.index.values())

    def emit(self):
        for fn in list(self.listeners):
            GLib.idle_add(lambda f=fn: f() and False)

    def _save_index(self):
        os.makedirs(OFFLINE_DIR, exist_ok=True)
        tmp = os.path.join(OFFLINE_DIR, "index.json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.index, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(OFFLINE_DIR, "index.json"))

    def sync(self):
        """Abgleichen: fehlende laden, herausgefallene löschen (im Hintergrund, einer nach dem anderen)."""
        want = self.want_all()
        with self.lock:
            if self.busy:
                self._again = True               # läuft gerade: danach noch einmal (z. B. neu gemerkt/freigegeben)
                return False
            self.busy = True
        threading.Thread(target=self._sync, args=(want,), daemon=True).start()
        return True

    def _sync(self, want):
        try:
            ids = {t["videoId"] for t in want}
            for vid in [v for v in self.index if v not in ids]:     # aussortieren
                self._remove(vid)
            # Dateien ohne Eintrag (abgebrochene Downloads) aufräumen
            if os.path.isdir(OFFLINE_DIR):
                known = {e["file"] for e in self.index.values()}
                for name in os.listdir(OFFLINE_DIR):
                    if name not in known and name != "index.json":
                        try:
                            os.remove(os.path.join(OFFLINE_DIR, name))
                        except OSError:
                            pass
            todo = [t for t in want if not self.path(t["videoId"]) and self.errors.get(t["videoId"], 0) < time.time()]
            for i, t in enumerate(todo):
                self.status = f"lade {i + 1}/{len(todo)}: {t['title']}"
                self.current = t["videoId"]
                self.emit()
                try:
                    self._download(t)
                except Exception as e:  # noqa: BLE001
                    self.errors[t["videoId"]] = time.time() + 6 * 3600     # später nochmal
                    log(f"offline {t['videoId']}: {str(e)[:160]}")
            self.status = ""
        finally:
            self.current = None
            self.busy = False
            self.emit()
            if self._again:
                self._again = False
                GLib.idle_add(lambda: self.sync() and False)

    def _remove(self, vid):
        e = self.index.pop(vid, None)
        if e:
            try:
                os.remove(os.path.join(OFFLINE_DIR, e["file"]))
            except OSError:
                pass
            self._save_index()

    MIN_FREE = 1_000_000_000      # darunter wird nichts mehr geladen (Platte nicht vollschreiben)

    def _download(self, t):
        import yt_dlp
        os.makedirs(OFFLINE_DIR, exist_ok=True)
        if shutil.disk_usage(OFFLINE_DIR).free < self.MIN_FREE:
            raise RuntimeError("zu wenig freier speicherplatz (unter 1 gb)")
        vid = t["videoId"]
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
                "format": "bestaudio[acodec=opus]/bestaudio/best", "js_runtimes": js_runtimes(),
                "outtmpl": os.path.join(OFFLINE_DIR, f"{vid}.part-dl.%(ext)s"), "ratelimit": 4_000_000}
        if os.path.exists(COOKIES_TXT):
            opts["cookiefile"] = COOKIES_TXT
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://music.youtube.com/watch?v={vid}", download=True)
            got = (info.get("requested_downloads") or [{}])[0].get("filepath") or ydl.prepare_filename(info)
        ext = os.path.splitext(got)[1]
        final = os.path.join(OFFLINE_DIR, vid + ext)
        os.replace(got, final)
        self.index[vid] = {"file": vid + ext, "title": t.get("title"), "artist": t.get("artist"),
                           "size": os.path.getsize(final), "at": time.time(), "abr": info.get("abr")}
        self._save_index()

    def clear(self):
        for vid in list(self.index):
            self._remove(vid)
        self.emit()


class Player:
    """Warteschlange + Wiedergabe. listeners bekommen (was) bei Änderungen:
    'track' (anderer Titel), 'state' (Pause/Laden), 'pos' (Zeit), 'queue', 'volume', 'error:<text>'."""

    def __init__(self):
        self.music = Music()
        self.resolver = Resolver()
        self.lyrics = Lyrics(self.music)
        self.listeners = []
        self.history = History()
        self.offline = Offline(self.history)
        self.stats = Stats(self.history)
        self.locallib = localmusic.Library(os.path.join(HERE, "local.json"))
        self.resolver.local = self.offline.path
        self.queue, self.index = [], -1
        self.pos, self.dur, self.paused, self.loading, self.volume = 0.0, 0.0, True, False, 70
        self.repeat, self.shuffle, self.autoplay = "aus", False, True
        self.stream_info = None
        self.gen = 0
        self._retry_kind = None
        self._fail_streak = 0
        self._retry_n = {}
        self.sleep_end, self.sleep_track, self._sleep_id, self._sleep_faded, self._fade_t = None, False, None, False, 0.0
        self.started = False  # in dieser Sitzung schon etwas geladen?
        self.restore_pos = 0
        self.eq = audiofx.normalize(setting("eq"))
        self.mpv2, self._xf = None, None                  # Standby-mpv + laufende Überblendung
        self.mpv = self._new_mpv(MPV_SOCK)
        self.apply_eq()
        self.load_state()
        self.mpv.set("volume", self.volume)
        self.mpris = Mpris(self)
        if setting("crossfade"):             # Standby-mpv erst nach dem ersten Zeichnen starten
            GLib.timeout_add(2500, lambda: self.ensure_standby() and False)
        if self.current:  # nach dem Start: aktuellen Titel schon vorladen → Play geht sofort.
            # Erst nach dem ersten Zeichnen: der yt-dlp-Import (~0,6 s) hielt sonst das Fenster beim Aufbau auf.
            GLib.timeout_add(1200, lambda: self.prefetch(include_current=True) or False)
        self._save_id = None
        if setting("ytdlp_auto"):
            GLib.timeout_add_seconds(90, lambda: self.update_ytdlp(7 * 86400) and False)

    # ----- zwei mpv-Prozesse: aktiv + Standby (für die Überblendung) -----
    def _new_mpv(self, path):
        box = {}

        def on_event(msg):
            m = box["m"]
            if m is self.mpv:
                self.on_mpv(msg)
            else:
                self._on_standby(m, msg)

        def restarted():
            m = box["m"]
            if m is self.mpv:
                self._mpv_restarted()
            else:
                self._standby_restarted(m)
        box["m"] = Mpv(on_event, restarted, path)
        return box["m"]

    def ensure_standby(self):
        if self.mpv2 is None:
            try:
                self.mpv2 = self._new_mpv(MPV_SOCK2)
                self.mpv2.set("volume", 0)
                self.apply_eq()
            except Exception as e:  # noqa: BLE001 – ohne zweiten mpv gibt es eben keine Überblendung
                log(f"standby-mpv: {e}")
                self.mpv2 = None
        return self.mpv2

    def _on_standby(self, m, msg):
        """Ereignisse des gerade nicht aktiven mpv: nur Eigenschaften merken (Dauer, Position, geladen)."""
        ev = msg.get("event")
        if ev == "property-change" and msg.get("name"):
            m.props[msg["name"]] = msg.get("data")
        elif ev == "file-loaded":
            m.props["loaded"] = True

    def _standby_restarted(self, m):
        m.set("volume", 0)
        self.apply_eq()

    # ----- Equalizer -----
    def set_eq(self, eq):
        self.eq = audiofx.normalize(eq)
        set_setting("eq", self.eq)
        self.apply_eq()
        self.emit("eq")

    def apply_eq(self):
        af = audiofx.build_af(self.eq)
        for m in (self.mpv, self.mpv2):
            if m is not None:
                m.set("af", af)

    # ----- Überblendung: der nächste Titel startet im Standby-mpv unter dem Ende des aktuellen -----
    def set_crossfade(self, secs):
        set_setting("crossfade", int(secs))
        if secs:
            self.ensure_standby()
        else:
            self._xf_cancel()
        self.emit("eq")

    def _xf_candidate(self):
        """(Index, Stream-Daten) des nächsten Titels, wenn jetzt überblendet werden soll – sonst None."""
        n = setting("crossfade") or 0
        if not n or self._xf is not None or self.mpv2 is None or not self.started or self.paused or self.loading:
            return None
        if self.repeat == "eins" or self.sleep_track or not self.dur or self.dur < n * 3:
            return None
        if self.sleep_end and self.sleep_left() < n + 12:
            return None
        if self.dur - self.pos > n + 0.3 or self.pos < 2:
            return None
        nxt = self.index + 1
        if nxt >= len(self.queue):
            if self.repeat != "alle" or len(self.queue) < 2:
                return None
            nxt = 0
        vid = self.queue[nxt]["videoId"]
        try:
            info = self.resolver.local_info(vid) or self.resolver.cached(vid)
        except Exception:  # noqa: BLE001 – z. B. lokale Datei fehlt: normal weiter (meldet dort den Fehler)
            return None
        return (nxt, info) if info else None       # noch nicht aufgelöst → normaler Wechsel

    def _xf_start(self, nxt, info):
        a, b, n = self.mpv, self.mpv2, setting("crossfade")
        t = self.queue[nxt]
        b.props = {}
        b.set("user-agent", info["ua"])
        b.set("volume", 0)
        b.set("pause", False)
        b.loadfile(info["url"])
        b.set("force-media-title", f"{t['artist']} - {t['title']}")
        self._xf = {"idx": nxt, "vid": t["videoId"], "info": info, "t0": time.monotonic(), "len": float(n),
                    "a": a, "b": b, "id": GLib.timeout_add(80, self._xf_tick)}
        self._fade_t = time.monotonic()

    def _xf_tick(self):
        x = self._xf
        if x is None:
            return False
        f = (time.monotonic() - x["t0"]) / x["len"]
        loaded = bool(x["b"].props.get("loaded"))
        if not loaded and f > 0.4:                       # Netz zu langsam: Überblendung fallenlassen
            log("überblendung: nächster Titel nicht rechtzeitig geladen")
            self._xf_cancel()
            return False
        f = min(1.0, f)
        self._fade_t = time.monotonic()
        x["a"].set("volume", round(self.volume * math.cos(f * math.pi / 2), 1))
        x["b"].set("volume", round(self.volume * math.sin(f * math.pi / 2) if loaded else 0, 1))
        if f >= 1.0:
            self._xf_finish()
            return False
        return True

    def _xf_stop_timer(self):
        x = self._xf
        if x and x.get("id"):
            GLib.source_remove(x["id"])
            x["id"] = None

    def _xf_cancel(self):
        """Überblendung abbrechen (Nutzer greift ein): der neue Titel wird still gestoppt, der alte bleibt."""
        x = self._xf
        if x is None:
            return
        self._xf_stop_timer()
        self._xf = None
        x["b"].cmd("stop")
        x["b"].set("volume", 0)
        x["a"].set("volume", self.volume)
        self._fade_t = time.monotonic()

    def _xf_finish(self):
        x = self._xf
        self._xf_stop_timer()
        self._xf = None
        if not (0 <= x["idx"] < len(self.queue)) or self.queue[x["idx"]]["videoId"] != x["vid"]:
            x["b"].cmd("stop")                            # Warteschlange hat sich inzwischen geändert
            x["b"].set("volume", 0)
            x["a"].set("volume", self.volume)
            return
        a, b = x["a"], x["b"]
        self.mpv, self.mpv2 = b, a                        # Rollen tauschen
        a.cmd("stop")
        a.set("volume", 0)
        b.set("volume", self.volume)
        self._fade_t = time.monotonic()
        self.index = x["idx"]
        t = self.current
        self.gen += 1
        self.loading, self.started, self.paused = False, True, False
        self.pos = b.props.get("time-pos") or 0
        self.dur = b.props.get("duration") or t.get("duration") or 0
        self.stream_info = x["info"]
        self._retry_n.clear()
        self._fail_streak = 0
        self.emit("track")
        self.emit("state")
        self._begin_track(t)
        self.prefetch()

    def _begin_track(self, t):
        """Verlauf, YouTube-Meldung und Songtext für einen neu begonnenen Titel vorbereiten (load + Überblendung)."""
        # In den Verlauf erst nach 5 s echter Wiedergabe (Durchskippen zählt nicht) – siehe on_mpv „time-pos“.
        # Hörverlauf in den Einstellungen aus → gar nichts merken.
        self._hist = {"t": t, "played": 0.0, "last": None} if setting("history") else None
        self.yt_end()                 # vorigen Titel bei YouTube abschließen
        self._ytr = {"t": t, "played": 0.0, "last": None, "rep": None, "sent": False, "from": None} \
            if setting("yt_history") and not localmusic.is_local(t) else None
        # Songtext schon jetzt holen (dieser + nächster Titel), nicht erst beim Öffnen von „lyrics“
        nxt = self.queue[self.index + 1] if self.index + 1 < len(self.queue) else None
        self.lyrics.preload([t, nxt])

    def _mpv_restarted(self):
        """mpv war abgestürzt und läuft wieder: Lautstärke setzen, Titel an der alten Stelle fortsetzen."""
        self.mpv.set("volume", self.volume)
        was_playing = not self.paused and self.current is not None and self.started
        self.started, self.restore_pos, self.loading = False, self.pos, False
        self.paused = True
        self.emit("state")
        self.emit("notice:abspielprogramm (mpv) war abgestürzt – neu gestartet")
        if was_playing:
            self.load(resume=self.restore_pos)

    # ----- lokale Musik -----
    def scan_local(self, done=None):
        """Musikordner im Hintergrund einlesen; done(tracks | Exception) im Hauptthread."""
        tui.background(lambda: self.locallib.scan(setting("local_dir")), done=done)

    # ----- yt-dlp aktuell halten -----
    def update_ytdlp(self, min_age=0, quiet=True):
        def done(res):
            if isinstance(res, Exception):
                log(f"yt-dlp-update: {res}")
                self.emit(f"notice:yt-dlp-update fehlgeschlagen: {str(res)[:100]}") if not quiet else None
            elif res is None:
                self.emit("notice:yt-dlp wird schon aktualisiert") if not quiet else None
            else:
                old, new = res
                self.resolver.reset()
                self.emit(f"notice:yt-dlp aktualisiert {old} → {new}" if old != new else
                          ("notice:yt-dlp ist aktuell (" + new + ")" if not quiet else ""))
        tui.background(update_ytdlp, min_age, done=done)

    BREAK_HINTS = ("unable to extract", "sign in to confirm", "nsig", "http error 403", "signature", "player response",
                   "requested format is not available", "unsupported url", "unable to download")

    def maybe_update_for(self, msg):
        """Wiedergabe-Fehler, der nach „YouTube hat etwas geändert“ aussieht → einmal pro 6 h yt-dlp updaten."""
        if setting("ytdlp_auto") and any(h in msg.lower() for h in self.BREAK_HINTS):
            self.update_ytdlp(6 * 3600)

    # ----- Benachrichtigung -----
    def emit(self, what):
        for fn in list(self.listeners):
            fn(what)
        if what in ("track", "state", "queue", "volume"):
            self.mpris.changed(what)
            self.save_soon()

    @property
    def current(self):
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None

    # ----- Steuerung -----
    def play_tracks(self, tracks, start=0, shuffle=False):
        tracks = [t for t in tracks if t]
        if not tracks:
            return
        if shuffle:
            tracks = tracks[:]
            random.shuffle(tracks)
            start = 0
        self.queue, self.index = tracks, start
        self.emit("queue_new")
        self.emit("queue")
        self.load()

    def play_now(self, t):
        """Titel sofort spielen, Rest der Warteschlange bleibt dahinter."""
        if self.current is None:
            self.play_tracks([t])
            return
        self.queue.insert(self.index + 1, t)
        self.index += 1
        self.emit("queue")
        self.load()

    def add(self, t, next_=False):
        if next_ and self.current is not None:
            self.queue.insert(self.index + 1, t)
        else:
            self.queue.append(t)
        if self.current is None:
            self.index = len(self.queue) - 1
            self.load()
        self.emit("queue")
        self.prefetch()

    def remove(self, i):
        if not 0 <= i < len(self.queue):
            return
        del self.queue[i]
        if i < self.index:
            self.index -= 1
        elif i == self.index:
            self.index = min(self.index, len(self.queue) - 1)
            if self.current:
                self.load()
            else:
                self.stop()
        self.emit("queue")

    def move(self, i, j):
        if 0 <= i < len(self.queue) and 0 <= j < len(self.queue):
            t = self.queue.pop(i)
            self.queue.insert(j, t)
            if self.index == i:
                self.index = j
            elif i < self.index <= j:
                self.index -= 1
            elif j <= self.index < i:
                self.index += 1
            self.emit("queue")

    def clear(self, keep_current=True):
        cur = self.current
        self.queue = [cur] if keep_current and cur else []
        self.index = 0 if self.queue else -1
        self.emit("queue")

    def shuffle_queue(self):
        if len(self.queue) > self.index + 2:
            rest = self.queue[self.index + 1:]
            random.shuffle(rest)
            self.queue[self.index + 1:] = rest
            self.emit("queue")

    def jump(self, i):
        if 0 <= i < len(self.queue):
            self.index = i
            self.load()

    def toggle(self):
        self._xf_cancel()
        if not self.started and self.current:  # nach Neustart: gespeicherten Titel erst laden
            self.load(resume=self.restore_pos)
            return
        self.mpv.set("pause", not self.paused)

    def play(self):
        if self.paused:
            self.toggle()

    def pause(self):
        self._xf_cancel()
        if not self.paused:
            self.mpv.set("pause", True)

    # ----- YouTube-Verlauf: nach 10 s echter Wiedergabe melden, dann alle 30 s die gehörte Zeit -----
    YT_AFTER, YT_EVERY = 10, 30

    def yt_tick(self, pos):
        r = getattr(self, "_ytr", None)
        if r is None or self.paused or self.loading or r["t"] is not self.current:
            return
        if r["last"] is not None and 0 < pos - r["last"] < 1.5:
            r["played"] += pos - r["last"]
        else:
            if r["from"] is not None and r["last"] is not None:      # gespult: bisherigen Abschnitt melden
                self._yt_watch(r, r["from"], r["last"])
            r["from"] = pos
        r["last"] = pos
        if not r["sent"] and r["played"] >= self.YT_AFTER:
            r["sent"] = True
            vid = r["t"]["videoId"]

            def done(res):
                if isinstance(res, Exception):
                    log(f"youtube-verlauf: {res}")
                    return
                r["rep"] = res
            tui.background(self.music.report_start, vid, done=done)
        elif r["rep"] and pos - (r["from"] or 0) >= self.YT_EVERY:
            self._yt_watch(r, r["from"], pos)
            r["from"] = pos

    def _yt_watch(self, r, st, et, final=False):
        if r.get("rep") and et > st:
            tui.background(self.music.report_watch, r["rep"], st, et, self.dur or r["t"].get("duration") or et,
                           final, done=lambda res: isinstance(res, Exception) and log(f"youtube-hörzeit: {res}"))

    def yt_end(self):
        r, self._ytr = getattr(self, "_ytr", None), None
        if r and r["rep"] and r["from"] is not None and r["last"] is not None:
            self._yt_watch(r, r["from"], r["last"], final=True)

    def stop(self):
        self._xf_cancel()
        self.yt_end()
        self.mpv.cmd("stop")
        self.started = False
        self.emit("track")

    # ----- Sleep-Timer: nach N Minuten (letzte 10 s leiser werden) oder nach dem laufenden Titel pausieren -----
    SLEEP_FADE = 10

    def set_sleep(self, minutes=None, after_track=False):
        """minutes=None und after_track=False schaltet den Timer aus."""
        self._sleep_stop(restore=True)
        self.sleep_end = time.monotonic() + minutes * 60 if minutes else None
        self.sleep_track = bool(after_track)
        if self.sleep_end:
            self._sleep_id = GLib.timeout_add(500, self._sleep_tick)
        self.emit("sleep")

    def sleep_left(self):
        return max(0, self.sleep_end - time.monotonic()) if self.sleep_end else None

    def _sleep_stop(self, restore=False):
        if self._sleep_id:
            GLib.source_remove(self._sleep_id)
            self._sleep_id = None
        self.sleep_end, self.sleep_track = None, False
        if restore and self._sleep_faded:
            self._sleep_faded = False
            self._fade_t = time.monotonic()
            self.mpv.set("volume", self.volume)

    def _sleep_tick(self):
        left = self.sleep_left()
        if left is None:
            self._sleep_id = None
            return False
        if left <= 0:
            self._sleep_id = None
            self.sleep_end = None
            self.pause()
            self._sleep_faded = False
            self._fade_t = time.monotonic()
            self.mpv.set("volume", self.volume)     # beim nächsten Play wieder normal laut
            self.emit("sleep")
            return False
        if left < self.SLEEP_FADE:
            self._sleep_faded = True
            self._fade_t = time.monotonic()
            self.mpv.set("volume", max(1, self.volume * left / self.SLEEP_FADE))
        self.emit("sleep")
        return True

    def next(self, auto=False):
        if auto and self.sleep_track:                 # „nach diesem Titel“: Ende erreicht → stehen bleiben
            self._sleep_stop()
            if self.index + 1 < len(self.queue):
                self.index += 1
            self.started, self.restore_pos = False, 0
            self.mpv.set("pause", True)
            self.emit("track")
            self.emit("sleep")
            return
        if auto and self.repeat == "eins":
            self.load()
            return
        if self.index + 1 < len(self.queue):
            self.index += 1
            self.load()
        elif self.repeat == "alle" and self.queue:
            self.index = 0
            self.load()
        elif self.autoplay and self.current:
            self.extend_radio(then_next=True)
        else:
            self.mpv.set("pause", True)

    def prev(self):
        if self.pos > 3 or self.index <= 0:
            self.seek(0)
        else:
            self.index -= 1
            self.load()

    def seek(self, sec, relative=False):
        self._xf_cancel()
        self.mpv.cmd("seek", sec, "relative" if relative else "absolute")
        self.pos = max(0, sec if not relative else self.pos + sec)
        self.mpris.seeked()

    def set_volume(self, v):
        self.volume = int(max(0, min(100, v)))
        self.mpv.set("volume", self.volume)
        self.emit("volume")

    def cycle_repeat(self):
        self.repeat = {"aus": "alle", "alle": "eins", "eins": "aus"}[self.repeat]
        self.emit("state")

    def start_radio(self, t=None):
        t = t or self.current
        if not t:
            return
        if localmusic.is_local(t):
            self.emit("notice:radio gibt es nur für youtube-titel")
            return
        tui.background(self.music.radio, t["videoId"], done=lambda res: self._radio_done(res, t))

    def _radio_done(self, res, t):
        if isinstance(res, Exception) or not res:
            self.emit(f"error:radio: {res}")
            return
        rest = [x for x in res if x["videoId"] != t["videoId"]]
        if self.current and self.current["videoId"] == t["videoId"]:
            self.queue = self.queue[:self.index + 1] + rest
            self.emit("queue")
            self.prefetch()
        else:
            self.play_tracks([t] + rest)

    def extend_radio(self, then_next=False):
        cur = self.current
        if cur is not None and localmusic.is_local(cur):
            if then_next:
                self.mpv.set("pause", True)
            return
        if cur is None or (getattr(self, "_extending", None) == cur["videoId"] and not then_next):
            return  # läuft schon (bzw. für diesen Titel schon versucht)
        self._extending = cur["videoId"]
        seen = {x["videoId"] for x in self.queue}

        def done(res):
            if isinstance(res, Exception):
                self.emit(f"error:autoplay: {res}")
                return
            new = [x for x in res if x["videoId"] not in seen]
            self.queue += new[:25]
            self.emit("queue")
            if then_next and self.index + 1 < len(self.queue):
                self.index += 1
                self.load()
        tui.background(self.music.radio, cur["videoId"], done=done)

    def like(self, on=None):
        t = self.current
        if not t:
            return
        if localmusic.is_local(t):
            self.emit("notice:lokale titel lassen sich nicht liken")
            return
        on = (not t.get("liked")) if on is None else on
        t["liked"] = on
        self.emit("track")
        tui.background(self.music.rate, t["videoId"], on,
                       done=lambda r: isinstance(r, Exception) and self.emit(f"error:like: {r}"))

    def rate(self, t, on):
        """Beliebigen Titel liken/entliken (Rechtsklick-Menü); gleiche Titel in der Warteschlange mit."""
        for x in [t] + self.queue:
            if x.get("videoId") == t.get("videoId"):
                x["liked"] = on
        self.emit("track")
        tui.background(self.music.rate, t["videoId"], on,
                       done=lambda r: isinstance(r, Exception) and self.emit(f"error:like: {r}"))

    # ----- Laden -----
    def load(self, resume=0):
        t = self.current
        if not t:
            return
        self._xf_cancel()
        self.gen += 1
        gen = self.gen
        self.loading, self.started = True, True
        self.pos, self.dur = resume, t.get("duration") or 0
        self.stream_info = None
        self.emit("track")
        self.emit("state")
        self._begin_track(t)

        failed, self._retry_kind = self._retry_kind, None

        def done(res):
            if gen != self.gen:  # inzwischen anderer Titel gewählt
                return
            if isinstance(res, LoginRequired):  # nicht weiterspringen, sonst rauscht die ganze Liste durch
                self.loading, self.started = False, False
                self.emit(f"error:{res}")
                self.emit("state")
                return
            if isinstance(res, Exception):
                self.loading = False
                self._fail_streak += 1
                self.emit(f"error:{t['title']}: {explain(res)}")
                self.maybe_update_for(str(res))
                self.emit("state")
                if self._fail_streak >= 3:       # offline o. ä.: nicht die ganze Warteschlange durchrauschen lassen
                    self._fail_streak = 0
                    self.paused = True
                    self.emit("error:3 titel hintereinander gingen nicht – pausiert (internet? mit ▶ nochmal versuchen)")
                    self.emit("state")
                    return
                GLib.timeout_add(1200, lambda: gen == self.gen and self.next(auto=True) and False)
                return
            self.stream_info = res
            self.mpv.set("user-agent", res["ua"])
            self.mpv.loadfile(res["url"], resume)
            self.mpv.set("pause", False)
            if self.paused:                 # mpv meldet „nicht pausiert“ nur bei Änderung – hier selbst nachziehen
                self.paused = False
                self.emit("state")
            self.mpv.set("force-media-title", f"{t['artist']} - {t['title']}")
            self.prefetch()
        tui.background(self.stream_for, t["videoId"], failed, done=done)

    def stream_for(self, vid, failed=None):
        if PLAY_NEEDS_LOGIN and not localmusic.is_local(vid):
            require_login()
        return self.resolver.get(vid, failed)

    def prefetch(self, include_current=False):
        start = self.index if include_current else self.index + 1
        self.resolver.prefetch([t["videoId"] for t in self.queue[max(0, start):self.index + 3]])

    def on_mpv(self, msg):
        ev = msg.get("event")
        if ev == "mpv-dead":
            self.loading = False
            self.emit("error:mpv lässt sich nicht mehr starten – musicalist neu starten (ist mpv installiert?)")
            self.emit("state")
            return
        if ev == "property-change":
            name, val = msg.get("name"), msg.get("data")
            if name == "time-pos" and val is not None:
                self.pos = val
                h = getattr(self, "_hist", None)
                if h is not None and not self.paused and not self.loading:
                    if h["last"] is not None and 0 < val - h["last"] < 1.5:   # Sprünge (Spulen) zählen nicht
                        h["played"] += val - h["last"]
                    h["last"] = val
                    if h["played"] >= 5 and h["t"] is self.current:
                        self._hist = None
                        self.stats.add(h["t"])
                        if self.history.add(h["t"]):
                            self.emit("history")
                        if not localmusic.is_local(h["t"]):
                            self.offline.count(h["t"])
                self.yt_tick(val)
                self.emit("pos")
                if self._xf is None and setting("crossfade"):
                    cand = self._xf_candidate()
                    if cand:
                        self._xf_start(*cand)
            elif name == "duration" and val:
                self.dur = val
                self.emit("pos")
            elif name == "pause" and val is not None:
                if not val and not self.started:
                    return              # leerer mpv (Start/Neustart) meldet „nicht pausiert“ – es läuft aber nichts
                self.paused = val
                self.emit("state")
            elif name == "volume" and val is not None and abs(val - self.volume) >= 1 and not self._sleep_faded and time.monotonic() - self._fade_t > 1.5:
                self.volume = int(val)
                self.emit("volume")
            elif name == "paused-for-cache":
                self.loading = bool(val)
                self.emit("state")
        elif ev == "file-loaded":
            self._retry_n.clear()
            self._fail_streak = 0
            self.loading = False
            self.emit("state")
        elif ev == "end-file":
            if msg.get("reason") == "eof" and self._xf is not None:      # Ende erreicht, während überblendet wird
                if self._xf["b"].props.get("loaded"):
                    self._xf_finish()
                    return
                self._xf_cancel()
            if msg.get("reason") == "eof":
                self.next(auto=True)
            elif msg.get("reason") == "error":
                vid = (self.current or {}).get("videoId")
                self.resolver.cache.pop(vid, None)
                si = self.stream_info or {}
                log(f"mpv end-file error: {msg.get('file_error', '')} (kind={si.get('kind')} codec={si.get('codec')} "
                    f"proto={si.get('proto')} vid={vid})")
                if vid and self._retry_n.get(vid, 0) < 3:   # bis 3× mit anderer Adresse/anderem Format erneut
                    self._retry_n[vid] = self._retry_n.get(vid, 0) + 1
                    self._retry_kind = si.get("kind")
                    self.load(self.pos)
                    return False
                self._retry_n.pop(vid, None)
                self.emit(f"error:wiedergabe fehlgeschlagen ({msg.get('file_error', '')})")
        return False

    # ----- Zustand speichern -----
    def save_soon(self):
        if self._save_id is None:
            self._save_id = GLib.timeout_add_seconds(2, self.save_state)

    def save_state(self):
        self._save_id = None
        # höchstens 300 Titel – als Fenster um den aktuellen, damit der gespeicherte Index stimmt
        lo = max(0, min(self.index - 20, len(self.queue) - 300)) if self.index >= 0 else max(0, len(self.queue) - 300)
        data = {"queue": self.queue[lo:lo + 300], "index": self.index - lo if self.index >= 0 else -1,
                "pos": self.pos, "volume": self.volume,
                "repeat": self.repeat, "autoplay": self.autoplay}
        try:
            with open(STATE + ".tmp", "w") as f:
                json.dump(data, f)
            os.replace(STATE + ".tmp", STATE)
        except OSError:
            pass
        return False

    def load_state(self):
        try:
            d = json.load(open(STATE))
        except (OSError, ValueError):
            return
        self.queue = d.get("queue", [])
        self.index = d.get("index", -1) if self.queue else -1
        self.restore_pos = d.get("pos", 0)
        self.pos = self.restore_pos
        self.dur = (self.current or {}).get("duration", 0)
        self.volume = d.get("volume", 70)
        self.repeat = d.get("repeat", "aus")
        self.autoplay = d.get("autoplay", True)

    def shutdown(self):
        self.yt_end()
        self.save_state()
        self._xf_cancel()
        self.mpv.quit()
        if self.mpv2 is not None:
            self.mpv2.quit()


# ---------- MPRIS ----------
MPRIS_XML = """<node>
<interface name="org.mpris.MediaPlayer2">
 <method name="Raise"/><method name="Quit"/>
 <property name="CanQuit" type="b" access="read"/><property name="CanRaise" type="b" access="read"/>
 <property name="HasTrackList" type="b" access="read"/><property name="Identity" type="s" access="read"/>
 <property name="DesktopEntry" type="s" access="read"/>
 <property name="SupportedUriSchemes" type="as" access="read"/><property name="SupportedMimeTypes" type="as" access="read"/>
</interface>
<interface name="org.mpris.MediaPlayer2.Player">
 <method name="Next"/><method name="Previous"/><method name="Pause"/><method name="PlayPause"/>
 <method name="Stop"/><method name="Play"/>
 <method name="Seek"><arg direction="in" type="x"/></method>
 <method name="SetPosition"><arg direction="in" type="o"/><arg direction="in" type="x"/></method>
 <method name="OpenUri"><arg direction="in" type="s"/></method>
 <signal name="Seeked"><arg type="x"/></signal>
 <property name="PlaybackStatus" type="s" access="read"/><property name="LoopStatus" type="s" access="readwrite"/>
 <property name="Rate" type="d" access="readwrite"/><property name="Shuffle" type="b" access="readwrite"/>
 <property name="Metadata" type="a{sv}" access="read"/><property name="Volume" type="d" access="readwrite"/>
 <property name="Position" type="x" access="read"/><property name="MinimumRate" type="d" access="read"/>
 <property name="MaximumRate" type="d" access="read"/><property name="CanGoNext" type="b" access="read"/>
 <property name="CanGoPrevious" type="b" access="read"/><property name="CanPlay" type="b" access="read"/>
 <property name="CanPause" type="b" access="read"/><property name="CanSeek" type="b" access="read"/>
 <property name="CanControl" type="b" access="read"/>
</interface></node>"""
PATH = "/org/mpris/MediaPlayer2"


class Mpris:
    """Meldet den Player als "musicalist" bei MPRIS an: Waybar-Modul, Medientasten (playerctl) steuern ihn."""

    def __init__(self, player):
        self.p = player
        self.conn = None
        self.on_raise = None
        self.on_quit = None
        if IS_WIN:
            return                                 # kein D-Bus: Medientasten/Sperrbildschirm gibt es hier nicht
        self.info = Gio.DBusNodeInfo.new_for_xml(MPRIS_XML)
        Gio.bus_own_name(Gio.BusType.SESSION, "org.mpris.MediaPlayer2.musicalist", Gio.BusNameOwnerFlags.NONE,
                         self.acquired, None, None)

    def acquired(self, conn, _name):
        self.conn = conn
        for iface in self.info.interfaces:
            conn.register_object(PATH, iface, self.call, self.get, self.set)

    def status(self):
        if not self.p.started or not self.p.current:
            return "Stopped" if not self.p.current else "Paused"
        return "Paused" if self.p.paused else "Playing"

    def metadata(self):
        t = self.p.current
        if not t:
            return {"mpris:trackid": GLib.Variant("o", "/org/mpris/MediaPlayer2/TrackList/NoTrack")}
        return {"mpris:trackid": GLib.Variant("o", "/de/invincible/musicalist/" + (re.sub(r"[^A-Za-z0-9_]", "_", t["videoId"]) if not localmusic.is_local(t)
                                                                else "local_" + format(zlib.crc32(t["videoId"].encode()), "08x"))),
                "xesam:title": GLib.Variant("s", t["title"] or ""), "xesam:artist": GLib.Variant("as", [t["artist"] or ""]),
                "xesam:album": GLib.Variant("s", t["album"] or ""), "mpris:artUrl": GLib.Variant("s", t["thumb"] or ""),
                "mpris:length": GLib.Variant("x", int((self.p.dur or t["duration"] or 0) * 1e6)),
                "xesam:url": GLib.Variant("s", ("file://" + localmusic.path_of(t["videoId"])) if localmusic.is_local(t)
                                           else f"https://music.youtube.com/watch?v={t['videoId']}")}

    def props(self, iface):
        p = self.p
        if iface == "org.mpris.MediaPlayer2":
            return {"CanQuit": GLib.Variant("b", True), "CanRaise": GLib.Variant("b", True),
                    "HasTrackList": GLib.Variant("b", False), "Identity": GLib.Variant("s", "musicalist"),
                    "DesktopEntry": GLib.Variant("s", "de.invincible.Music"),
                    "SupportedUriSchemes": GLib.Variant("as", []), "SupportedMimeTypes": GLib.Variant("as", [])}
        return {"PlaybackStatus": GLib.Variant("s", self.status()),
                "LoopStatus": GLib.Variant("s", {"aus": "None", "alle": "Playlist", "eins": "Track"}[p.repeat]),
                "Rate": GLib.Variant("d", 1.0), "Shuffle": GLib.Variant("b", False),
                "Metadata": GLib.Variant("a{sv}", self.metadata()), "Volume": GLib.Variant("d", p.volume / 100),
                "Position": GLib.Variant("x", int(p.pos * 1e6)), "MinimumRate": GLib.Variant("d", 1.0),
                "MaximumRate": GLib.Variant("d", 1.0),
                "CanGoNext": GLib.Variant("b", bool(p.queue)), "CanGoPrevious": GLib.Variant("b", bool(p.queue)),
                "CanPlay": GLib.Variant("b", bool(p.current)), "CanPause": GLib.Variant("b", True),
                "CanSeek": GLib.Variant("b", True), "CanControl": GLib.Variant("b", True)}

    def get(self, _c, _s, _path, iface, name):
        return self.props(iface).get(name)

    def set(self, _c, _s, _path, _iface, name, value):
        v = value.unpack()
        if name == "Volume":
            self.p.set_volume(v * 100)
        elif name == "LoopStatus":
            self.p.repeat = {"None": "aus", "Playlist": "alle", "Track": "eins"}.get(v, "aus")
            self.p.emit("state")
        return True

    def call(self, _c, _s, _path, _iface, method, params, inv):
        p = self.p
        args = params.unpack()
        act = {"Next": p.next, "Previous": p.prev, "Pause": p.pause, "PlayPause": p.toggle, "Play": p.play,
               "Stop": p.pause, "Raise": lambda: self.on_raise and self.on_raise(), "Quit": lambda: self.on_quit and GLib.idle_add(self.on_quit),
               "OpenUri": lambda: self.open_uri(args[0])}
        if method == "Seek":
            p.seek(args[0] / 1e6, relative=True)
        elif method == "SetPosition":
            p.seek(args[1] / 1e6)
        elif method in act:
            act[method]()
        inv.return_value(None)

    def open_uri(self, uri):
        """playerctl -p musicalist open https://music.youtube.com/watch?v=… → sofort spielen (mit Radio danach)."""
        import re as _re
        m = _re.search(r"(?:v=|youtu\.be/)([\w-]{11})", uri)
        if not m:
            return
        vid = m.group(1)

        def done(res):
            t = res if isinstance(res, dict) else {"videoId": vid, "title": vid, "artist": "", "album": "",
                                                    "duration": 0, "thumb": "", "liked": False}
            self.p.play_now(t)
            if self.p.autoplay:
                self.p.start_radio(t)

        def info():
            d = self.p.music.yt.get_song(vid).get("videoDetails", {})
            return {"videoId": vid, "title": d.get("title", vid), "artist": d.get("author", ""), "album": "",
                    "duration": int(d.get("lengthSeconds") or 0),
                    "thumb": (d.get("thumbnail", {}).get("thumbnails") or [{}])[-1].get("url", ""), "liked": False}
        tui.background(info, done=done)

    def changed(self, what):
        if not self.conn:
            return
        props = self.props("org.mpris.MediaPlayer2.Player")
        keys = {"track": ["Metadata", "PlaybackStatus", "CanPlay"], "state": ["PlaybackStatus", "LoopStatus"],
                "queue": ["CanGoNext", "CanGoPrevious", "CanPlay"], "volume": ["Volume"]}[what]
        self.conn.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                              GLib.Variant("(sa{sv}as)", ("org.mpris.MediaPlayer2.Player",
                                                          {k: props[k] for k in keys}, [])))

    def seeked(self):
        if self.conn:
            self.conn.emit_signal(None, PATH, "org.mpris.MediaPlayer2.Player", "Seeked",
                                  GLib.Variant("(x)", (int(self.p.pos * 1e6),)))
