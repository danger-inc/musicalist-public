# musicalist – Engine: YouTube Music (ytmusicapi) + Wiedergabe über mpv (JSON-IPC) + MPRIS (Waybar, Medientasten,
# playerctl) + Anmeldung über die Zen-Sitzung. Keine GTK-Widgets hier, nur Logik.
#
# Stream-Adressen löst yt-dlp im Prozess auf (≈1,5 s); der nächste Titel wird schon während des laufenden
# vorgeladen, damit der Wechsel sofort geht. Zustand (Warteschlange, Lautstärke …) liegt in state.json.
import glob, json, os, random, shutil, socket, sqlite3, subprocess, tempfile, threading, time

from gi.repository import Gio, GLib

import tui

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(HERE, "auth")
BROWSER_JSON = os.path.join(AUTH_DIR, "browser.json")   # Anmeldung für ytmusicapi
COOKIES_TXT = os.path.join(AUTH_DIR, "cookies.txt")      # Anmeldung für yt-dlp
STATE = os.path.join(HERE, "state.json")
RUNTIME = GLib.get_user_runtime_dir()
MPV_SOCK = RUNTIME + "/rice-music-mpv.sock"
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


def track(d):
    """Einheitliches Format aus Suche, Playlist, Album, Radio, Verlauf."""
    if not d or not d.get("videoId"):
        return None
    arts = d.get("artists") or []
    thumbs = d.get("thumbnails") or d.get("thumbnail") or []
    if isinstance(thumbs, dict):
        thumbs = thumbs.get("thumbnails", [])
    album = d.get("album")
    return {"videoId": d["videoId"], "title": d.get("title") or "?",
            "artist": ", ".join(a["name"] for a in arts if a.get("name")) or d.get("author", ""),
            "album": album.get("name", "") if isinstance(album, dict) else (album or ""),
            "duration": d.get("duration_seconds") or secs(d.get("duration") or d.get("length") or 0),
            "thumb": thumbs[-1]["url"] if thumbs else "",
            "liked": d.get("likeStatus") == "LIKE"}


# ---------- Anmeldung über Zen ----------
def browser_profiles():
    found = []
    # Zen liegt je nach Version unter ~/.config/zen (XDG) oder ~/.zen, als Flatpak unter ~/.var/app
    for base in ("~/.config/zen", "~/.zen", "~/.var/app/app.zen_browser.zen/.zen",
                 "~/.var/app/app.zen_browser.zen/config/zen", "~/.mozilla/firefox", "~/.librewolf"):
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


def login_from_browser():
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
            raise RuntimeError("kein zen-profil gefunden (gesucht in ~/.config/zen, ~/.zen, flatpak)")
        raise RuntimeError("keine youtube-anmeldung in zen gefunden – dort erst bei music.youtube.com einloggen")
    rows = best[1]
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
    return account_name()


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
        self.authed = False
        self.auth_error = None

    @property
    def yt(self):
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
        flt = {"songs": "songs", "alben": "albums", "playlists": "playlists", "künstler": "artists",
               "videos": "videos"}[kind]
        return self.yt.search(q, filter=flt, limit=40)

    def suggestions(self, q):
        return self.yt.get_search_suggestions(q)

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

    def history(self):
        return [t for t in map(track, self.yt.get_history()) if t]

    def radio(self, vid):
        d = self.yt.get_watch_playlist(videoId=vid, radio=True, limit=40)
        return [t for t in map(track, d.get("tracks", [])) if t]

    def lyrics(self, vid):
        w = self.yt.get_watch_playlist(videoId=vid, limit=1)
        if not w.get("lyrics"):
            return None
        try:
            return self.yt.get_lyrics(w["lyrics"], timestamps=True)
        except Exception:  # noqa: BLE001 – ältere Antworten ohne Zeitstempel
            return self.yt.get_lyrics(w["lyrics"])

    def rate(self, vid, like):
        self.yt.rate_song(vid, "LIKE" if like else "INDIFFERENT")


# ---------- Stream-Adressen ----------
class Resolver:
    """Stream-Adressen über yt-dlp. Zwei getrennte Wege, damit sich nichts gegenseitig blockiert:
    - fast: ohne Anmeldung (~1,5 s, Opus ~130 kbps) – für den Titel, den man gerade anklickt
    - hq:   mit Anmeldung (~4–6 s, Premium-Opus 256 kbps) – nur im Hintergrund zum Vorladen
    Vorgeladene hq-Adressen ersetzen fast-Einträge im Zwischenspeicher (4 h gültig)."""

    def __init__(self):
        self.cache = {}
        self.locks = {"fast": threading.Lock(), "hq": threading.Lock()}
        self.ydls = {}
        self.queue_lock = threading.Lock()
        self.wanted = []
        self.worker = None

    def reset(self):
        self.ydls = {}

    def ydl(self, kind):
        import yt_dlp
        cookies = COOKIES_TXT if kind == "hq" and os.path.exists(COOKIES_TXT) else None
        key = (kind, cookies)
        if key not in self.ydls:
            opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "format": "bestaudio/best",
                    "js_runtimes": {"node": {}}, "skip_download": True}
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
               "kind": kind}
        old = self.cached(vid)
        if not (old and old.get("kind") == "hq" and kind == "fast"):
            self.cache[vid] = (time.time() + 4 * 3600, res)
        return res

    def get(self, vid):
        """Für sofortiges Abspielen: Zwischenspeicher, sonst der schnelle Weg (Notfall: hq)."""
        hit = self.cached(vid)
        if hit:
            return hit
        try:
            return self._extract(vid, "fast")
        except Exception:  # noqa: BLE001 – z. B. altersbeschränkt: mit Anmeldung versuchen
            if not os.path.exists(COOKIES_TXT):
                raise
            return self._extract(vid, "hq")

    def prefetch(self, vids):
        """Im Hintergrund nacheinander vorladen (neueste Wunschliste gewinnt)."""
        kind = "hq" if os.path.exists(COOKIES_TXT) else "fast"
        with self.queue_lock:
            self.wanted = [v for v in vids if not (self.cached(v) and self.cached(v).get("kind") == kind)]
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
class Mpv:
    def __init__(self, on_event):
        self.on_event = on_event
        self.sock = None
        self.lock = threading.Lock()
        try:
            os.unlink(MPV_SOCK)
        except OSError:
            pass
        self.proc = tui.spawn_watch(["mpv", "--idle=yes", "--no-video", "--no-terminal", "--ytdl=no",
                                     "--audio-display=no", f"--input-ipc-server={MPV_SOCK}",
                                     "--audio-client-name=musicalist", "--cache=yes", "--demuxer-max-bytes=64MiB",
                                     "--gapless-audio=weak", "--replaygain=track"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(MPV_SOCK)
                self.sock = s
                break
            except OSError:
                time.sleep(0.03)
        if self.sock is None:
            raise RuntimeError("mpv startet nicht")
        threading.Thread(target=self.read, daemon=True).start()
        for i, p in enumerate(("time-pos", "duration", "pause", "volume", "idle-active", "paused-for-cache")):
            self.cmd("observe_property", i + 1, p)

    def cmd(self, *args):
        data = (json.dumps({"command": list(args)}) + "\n").encode()
        with self.lock:
            try:
                self.sock.sendall(data)
            except OSError:
                pass

    def set(self, prop, value):
        self.cmd("set_property", prop, value)

    def read(self):
        buf = b""
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
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
        self.cmd("quit")


# ---------- Player ----------
class Player:
    """Warteschlange + Wiedergabe. listeners bekommen (was) bei Änderungen:
    'track' (anderer Titel), 'state' (Pause/Laden), 'pos' (Zeit), 'queue', 'volume', 'error:<text>'."""

    def __init__(self):
        self.music = Music()
        self.resolver = Resolver()
        self.listeners = []
        self.queue, self.index = [], -1
        self.pos, self.dur, self.paused, self.loading, self.volume = 0.0, 0.0, True, False, 70
        self.repeat, self.shuffle, self.autoplay = "aus", False, True
        self.stream_info = None
        self.gen = 0
        self.started = False  # in dieser Sitzung schon etwas geladen?
        self.restore_pos = 0
        self.mpv = Mpv(self.on_mpv)
        self.load_state()
        self.mpv.set("volume", self.volume)
        self.mpris = Mpris(self)
        if self.current:  # nach dem Start: aktuellen Titel schon vorladen → Play geht sofort
            self.prefetch(include_current=True)
        self._save_id = None

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
        if not self.started and self.current:  # nach Neustart: gespeicherten Titel erst laden
            self.load(resume=self.restore_pos)
            return
        self.mpv.set("pause", not self.paused)

    def play(self):
        if self.paused:
            self.toggle()

    def pause(self):
        if not self.paused:
            self.mpv.set("pause", True)

    def stop(self):
        self.mpv.cmd("stop")
        self.started = False
        self.emit("track")

    def next(self, auto=False):
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
        on = (not t.get("liked")) if on is None else on
        t["liked"] = on
        self.emit("track")
        tui.background(self.music.rate, t["videoId"], on,
                       done=lambda r: isinstance(r, Exception) and self.emit(f"error:like: {r}"))

    # ----- Laden -----
    def load(self, resume=0):
        t = self.current
        if not t:
            return
        self.gen += 1
        gen = self.gen
        self.loading, self.started = True, True
        self.pos, self.dur = resume, t.get("duration") or 0
        self.stream_info = None
        self.emit("track")
        self.emit("state")

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
                self.emit(f"error:{t['title']}: {str(res).splitlines()[0][:160]}")
                self.emit("state")
                GLib.timeout_add(1200, lambda: gen == self.gen and self.next(auto=True) and False)
                return
            self.stream_info = res
            self.mpv.set("user-agent", res["ua"])
            opts = f"start={resume}" if resume else ""
            self.mpv.cmd("loadfile", res["url"], "replace", -1, opts) if opts else \
                self.mpv.cmd("loadfile", res["url"], "replace")
            self.mpv.set("pause", False)
            self.mpv.set("force-media-title", f"{t['artist']} - {t['title']}")
            self.prefetch()
        tui.background(self.stream_for, t["videoId"], done=done)

    def stream_for(self, vid):
        if PLAY_NEEDS_LOGIN:
            require_login()
        return self.resolver.get(vid)

    def prefetch(self, include_current=False):
        start = self.index if include_current else self.index + 1
        self.resolver.prefetch([t["videoId"] for t in self.queue[max(0, start):self.index + 3]])

    def on_mpv(self, msg):
        ev = msg.get("event")
        if ev == "property-change":
            name, val = msg.get("name"), msg.get("data")
            if name == "time-pos" and val is not None:
                self.pos = val
                self.emit("pos")
            elif name == "duration" and val:
                self.dur = val
                self.emit("pos")
            elif name == "pause" and val is not None:
                self.paused = val
                self.emit("state")
            elif name == "volume" and val is not None and abs(val - self.volume) >= 1:
                self.volume = int(val)
                self.emit("volume")
            elif name == "paused-for-cache":
                self.loading = bool(val)
                self.emit("state")
        elif ev == "file-loaded":
            self.loading = False
            self.emit("state")
        elif ev == "end-file":
            if msg.get("reason") == "eof":
                self.next(auto=True)
            elif msg.get("reason") == "error":
                self.resolver.cache.pop((self.current or {}).get("videoId"), None)
                self.emit(f"error:wiedergabe fehlgeschlagen ({msg.get('file_error', '')})")
        return False

    # ----- Zustand speichern -----
    def save_soon(self):
        if self._save_id is None:
            self._save_id = GLib.timeout_add_seconds(2, self.save_state)

    def save_state(self):
        self._save_id = None
        data = {"queue": self.queue[-300:], "index": self.index, "pos": self.pos, "volume": self.volume,
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
        self.save_state()
        self.mpv.quit()


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
        return {"mpris:trackid": GLib.Variant("o", f"/de/invincible/musicalist/{t['videoId'].replace('-', '_')}"),
                "xesam:title": GLib.Variant("s", t["title"]), "xesam:artist": GLib.Variant("as", [t["artist"]]),
                "xesam:album": GLib.Variant("s", t["album"]), "mpris:artUrl": GLib.Variant("s", t["thumb"]),
                "mpris:length": GLib.Variant("x", int((self.p.dur or t["duration"] or 0) * 1e6)),
                "xesam:url": GLib.Variant("s", f"https://music.youtube.com/watch?v={t['videoId']}")}

    def props(self, iface):
        p = self.p
        if iface == "org.mpris.MediaPlayer2":
            return {"CanQuit": GLib.Variant("b", False), "CanRaise": GLib.Variant("b", True),
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
               "Stop": p.pause, "Raise": lambda: self.on_raise and self.on_raise(), "Quit": lambda: None,
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
