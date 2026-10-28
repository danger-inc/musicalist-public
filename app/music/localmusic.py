# musicalist – lokale Musikdateien (~/Music): Ordner einlesen, Tags lesen (mutagen, sonst Dateiname).
# Ein lokaler Titel ist ein normaler Titel mit videoId "local:<Pfad>", damit Warteschlange, Zustand und
# Hörverlauf ohne Sonderfälle funktionieren; engine.Resolver spielt ihn direkt aus der Datei.
import json, os, re, time

AUDIO = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma", ".oga", ".mka"}
PREFIX = "local:"


def is_local(t):
    vid = t.get("videoId") if isinstance(t, dict) else t
    return bool(vid) and str(vid).startswith(PREFIX)


def path_of(vid):
    return str(vid)[len(PREFIX):] if str(vid).startswith(PREFIX) else None


def _tags(path):
    """(titel, künstler, album, dauer) – Tags, sonst „Künstler - Titel“ aus dem Dateinamen."""
    name = os.path.splitext(os.path.basename(path))[0]
    title, artist, album, dur = name, "", "", 0
    m = re.match(r"^\s*(?:\d+[\s.\-_]+)?(.+?)\s+-\s+(.+)$", name)
    if m:
        artist, title = m.group(1).strip(), m.group(2).strip()
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is not None:
            first = lambda k: (f.get(k) or [""])[0].strip()
            title = first("title") or title
            artist = first("artist") or first("albumartist") or artist
            album = first("album")
            dur = int(getattr(f.info, "length", 0) or 0)
    except Exception:  # noqa: BLE001 – kaputte/fremde Datei: Dateiname reicht
        pass
    return title, artist, album, dur


def make_track(path, tags):
    title, artist, album, dur = tags
    return {"videoId": PREFIX + path, "title": title or os.path.basename(path), "artist": artist,
            "artistId": None, "albumId": None, "album": album, "duration": dur, "thumb": "",
            "liked": False, "setVideoId": None, "local": True}


class Library:
    """Scannt den Musikordner (im Hintergrund-Thread aufrufen) und merkt sich die Tags (nur geänderte Dateien
    werden neu gelesen)."""

    def __init__(self, cache_file):
        self.cache_file = cache_file
        self.root = None
        self.tracks = []
        try:
            with open(cache_file) as f:
                self.cache = json.load(f)
        except (OSError, ValueError):
            self.cache = {}

    @staticmethod
    def default_root():
        for cand in (os.environ.get("XDG_MUSIC_DIR"), os.path.expanduser("~/Music"), os.path.expanduser("~/Musik")):
            if cand and os.path.isdir(cand):
                return cand
        return os.path.expanduser("~/Music")

    def scan(self, root, limit=20000):
        root = os.path.expanduser(root or self.default_root())
        out, new_cache = [], {}
        if os.path.isdir(root):
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() not in AUDIO or fn.startswith("."):
                        continue
                    path = os.path.join(dirpath, fn)
                    try:
                        mt = os.path.getmtime(path)
                    except OSError:
                        continue
                    hit = self.cache.get(path)
                    tags = hit["tags"] if hit and hit.get("mt") == mt else _tags(path)
                    new_cache[path] = {"mt": mt, "tags": tags}
                    out.append(make_track(path, tags))
                    if len(out) >= limit:
                        break
        out.sort(key=lambda t: ((t["artist"] or "~").lower(), (t["album"] or "").lower(), t["title"].lower()))
        self.root, self.tracks, self.cache = root, out, new_cache
        try:
            with open(self.cache_file + ".tmp", "w") as f:
                json.dump(new_cache, f, ensure_ascii=False)
            os.replace(self.cache_file + ".tmp", self.cache_file)
        except OSError:
            pass
        return out

    def search(self, q):
        q = q.lower().strip()
        if not q:
            return self.tracks
        words = q.split()
        return [t for t in self.tracks
                if all(w in f"{t['title']} {t['artist']} {t['album']}".lower() for w in words)]
