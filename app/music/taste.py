"""Geschmack aus dem Überspringverhalten (Gegenstück zu Taste.kt am Handy): Radio/Autoplay schlagen nichts vor, was du bei
dieser Künstler·in oder diesem Titel zuletzt oft übersprungen hast, und bevorzugen, was du oft zu Ende hörst. Reine Rechnung.
Kein einzelnes Überspringen zählt (man ist manchmal nur nicht in Stimmung): erst ab 2 Skips mit hoher Quote wird abgewertet,
ab 3 ausgelassen. Mit „genre“ hat das nichts zu tun – die Ähnlichkeit kommt vom Radio, das Hörverhalten sortiert nur aus."""
import time

WINDOW = 30 * 86400          # so weit zurück zählt das Hörprotokoll
AHEAD = 5                    # so viele Radio-/Autoplay-Titel liegen voraus (kurze Warteschlange)
BATCH = 8                    # höchstens so viele werden beim Nachfüllen übernommen


def akey(t):
    """Künstler·in eines Titels (erster Name, klein – Protokoll und Vorschläge haben nicht immer dieselbe Kennung)."""
    return (t.get("artist") or t.get("a") or "").split(",")[0].strip().lower()


def _is_skip(e):
    if e.get("why") == "skip":
        d = e.get("d") or 0
        return (e.get("p") or 0) < 30 and (not d or (e.get("p") or 0) < d * 0.6)
    return False


def _is_full(e):
    d = e.get("d") or 0
    return e.get("why") == "ende" or (d > 0 and (e.get("p") or 0) >= d * 0.85)


class Taste:
    def __init__(self, rows=(), now=None):
        now = now or time.time()
        self.art = {}                # Künstler → [Skips, ganz gehört]
        self.trk = {}                # Titel-ID → Skips
        self.sess = {}               # Künstler → Skips in dieser Sitzung
        for e in rows:
            if now - e.get("at", 0) > WINDOW:
                continue
            k = akey(e)
            if not k:
                continue
            a = self.art.setdefault(k, [0, 0])
            if _is_skip(e):
                a[0] += 1
                self.trk[e.get("id")] = self.trk.get(e.get("id"), 0) + 1
            elif _is_full(e):
                a[1] += 1

    def skipped(self, t):
        """Gerade übersprungen (Live-Anpassung, vor dem Schreiben ins Protokoll)."""
        k = akey(t)
        if k:
            self.sess[k] = self.sess.get(k, 0) + 1
        vid = t.get("videoId")
        if vid:
            self.trk[vid] = self.trk.get(vid, 0) + 1

    def score(self, t):
        """< 0 abwerten, 0 neutral, > 0 bevorzugen; None = auslassen."""
        if self.trk.get(t.get("videoId"), 0) >= 2:
            return None
        k = akey(t)
        sk, full = self.art.get(k, [0, 0])
        sk += self.sess.get(k, 0)
        tot = sk + full
        rate = sk / tot if tot else 0
        if sk >= 3 and rate >= 0.75:
            return None
        if sk >= 2 and rate >= 0.6:
            return -1.0
        if full >= 2 and rate <= 0.2:
            return 1.0
        return 0.0

    def rank(self, cands):
        """Kandidaten sortieren (Bevorzugte nach vorn, Abgewertete nach hinten, Ausgelassene weg); sonst Reihenfolge des Radios."""
        scored = [(self.score(t), i, t) for i, t in enumerate(cands)]
        scored = [x for x in scored if x[0] is not None]
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [t for _s, _i, t in scored]
