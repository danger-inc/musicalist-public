# musicalist – Auswertung des Hörprotokolls (engine.Journal) für den Tab „analyse“. Reine Rechnung ohne GTK:
# analyse(rows, art, versatz) liefert alles, was die Seite zeigt. art: "w" Woche, "m" Monat, "y" Jahr, "a" gesamt;
# versatz 0 = laufender Zeitraum, -1 = der davor usw.
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

SESSION_GAP = 20 * 60           # mehr Pause → neue Hörsitzung
DAY_SHIFT = 4 * 3600            # ein „Tag“ geht bis 4 Uhr früh (nachts gehört zählt zum Abend davor)
COMEBACK_GAP = 90 * 86400       # so lange nicht gehört → Comeback
MILESTONES = (1, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)
MONTHS = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober",
          "november", "dezember"]
MON = ["jan", "feb", "mär", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez"]
WDAYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
WD = ["mo", "di", "mi", "do", "fr", "sa", "so"]
DAYPARTS = [("morgens", 5, 11), ("mittags", 11, 14), ("nachmittags", 14, 18), ("abends", 18, 23),
            ("nachts", 23, 29)]          # 29 = 5 Uhr am nächsten Tag
SRC_NAMES = {"radio": "radio", "autoplay": "autoplay", "playlist": "playlists", "album": "alben",
             "künstler": "künstlerseiten", "suche": "suche", "verlauf": "verlauf", "bibliothek": "bibliothek",
             "lokal": "lokale musik", "warteschlange": "warteschlange", "jetzt": "jetzt-seite",
             "analyse": "analyse", "liked": "lieblingssongs", "history": "verlauf", "local": "lokale musik",
             "artist": "künstlerseiten", "podcast": "podcasts", "new": "neuheiten",
             "start": "startseite", "entdecken": "entdecken", "jam": "marmelade"}


# ---------- einzelne Einträge ----------
def secs(e):
    """Wirklich gehörte Sekunden (alte Einträge: Titellänge, genauer weiß man es nicht)."""
    if e.get("alt") or "p" not in e:
        return float(e.get("d") or 0)
    return float(e["p"])


def counts(e):
    """Zählt als Wiedergabe: ≥ 30 s gehört oder mindestens die Hälfte (kurze Titel)."""
    if e.get("alt") or "p" not in e:
        return True
    p, d = e["p"], e.get("d") or 0
    return p >= 30 or (d > 0 and p >= d * 0.5)


def detailed(e):
    """Hat Angaben zum Hörverhalten (neues Protokoll)."""
    return not e.get("alt") and "why" in e


def skipped(e):
    d = e.get("d") or 0
    return e.get("why") == "skip" and (not d or e.get("p", 0) < d * 0.8)


def complete(e):
    d = e.get("d") or 0
    return e.get("why") == "ende" or (d > 0 and e.get("mx", 0) >= d * 0.9)


def artists(e):
    return [a.strip() for a in (e.get("a") or "").split(",") if a.strip()] or ["unbekannt"]


def end_ts(e):
    return e.get("end") or e["at"] + secs(e) + e.get("ps", 0)


def day_key(ts):
    """Kalendertag mit Tageswechsel um 4 Uhr."""
    return date.fromtimestamp(ts - DAY_SHIFT)


# ---------- Zeiträume ----------
def _ts(d):
    return time.mktime(datetime(d.year, d.month, d.day).timetuple()) + DAY_SHIFT


def _add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def bounds(art, offset=0, now=None, first=None):
    """(beginn, ende, titel, untertitel) eines Zeitraums. Grenzen liegen um 4 Uhr früh (wie day_key)."""
    now = now or time.time()
    today = day_key(now)
    if art == "w":
        mon = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        sun = mon + timedelta(days=6)
        iso = mon.isocalendar()
        span = (f"{mon.day}.–{sun.day}. {MON[sun.month - 1]} {sun.year}" if mon.month == sun.month else
                f"{mon.day}. {MON[mon.month - 1]} – {sun.day}. {MON[sun.month - 1]} {sun.year}")
        return _ts(mon), _ts(sun + timedelta(days=1)), f"kw {iso[1]} · {iso[0]}", span
    if art == "m":
        a = _add_months(date(today.year, today.month, 1), offset)
        b = _add_months(a, 1)
        return _ts(a), _ts(b), f"{MONTHS[a.month - 1]} {a.year}", f"{(b - a).days} tage"
    if art == "y":
        y = today.year + offset
        return _ts(date(y, 1, 1)), _ts(date(y + 1, 1, 1)), str(y), "jahresrückblick"
    lo = _ts(day_key(first)) if first else _ts(today)
    since = day_key(first) if first else today
    return lo, _ts(today + timedelta(days=1)), "gesamt", f"seit {since.day}. {MON[since.month - 1]} {since.year}"


def buckets(art, lo, hi):
    """Einteilung für den Verlauf: [(kurz, lang, beginn, ende)]."""
    a, b = day_key(lo), day_key(hi - 1)
    out = []
    if art in ("w", "m"):
        d = a
        while d <= b:
            short = WD[d.weekday()] if art == "w" else str(d.day)
            out.append((short, f"{WDAYS[d.weekday()]}, {d.day}. {MON[d.month - 1]}", _ts(d),
                        _ts(d + timedelta(days=1))))
            d += timedelta(days=1)
        return out
    months = (b.year - a.year) * 12 + b.month - a.month + 1
    if art == "y" or months <= 36:
        m = date(a.year, a.month, 1)
        while m <= b:
            n = _add_months(m, 1)
            out.append((MON[m.month - 1] if art == "y" else f"{MON[m.month - 1]}{str(m.year)[2:]}",
                        f"{MONTHS[m.month - 1]} {m.year}", max(lo, _ts(m)), min(hi, _ts(n))))
            m = n
        return out
    for y in range(a.year, b.year + 1):
        out.append((str(y), str(y), max(lo, _ts(date(y, 1, 1))), min(hi, _ts(date(y + 1, 1, 1)))))
    return out


# ---------- Auswertung ----------
def _pct(a, b):
    return a / b * 100 if b else 0.0


def _delta(cur, prev):
    """Veränderung in % (None: kein Vergleich möglich)."""
    if prev is None or not prev:
        return None
    return (cur - prev) / prev * 100


def _clock(sec_of_day):
    sec_of_day = int(sec_of_day) % 86400
    return f"{sec_of_day // 3600}:{sec_of_day % 3600 // 60:02d}"


def _median(vals):
    vals = sorted(vals)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def _basic(rows):
    """Kennzahlen eines Zeitraums (auch für den Vergleich mit dem davor)."""
    played = [e for e in rows if counts(e)]
    total = sum(secs(e) for e in rows)
    det = [e for e in rows if detailed(e)]
    return {
        "secs": total, "plays": len(played), "starts": len(rows),
        "tracks": len({e["id"] for e in played}),
        "artists": len({a for e in played for a in artists(e)}),
        "albums": len({e.get("alid") or e.get("al") for e in played if e.get("al")}),
        "days": len({day_key(e["at"]) for e in rows}),
        "skip": _pct(sum(1 for e in det if skipped(e)), len(det)) if det else None,
        "complete": _pct(sum(1 for e in det if complete(e)), len(det)) if det else None,
        "detailed": len(det),
    }


def analyse(rows, art="w", offset=0, now=None):
    now = now or time.time()
    first = rows[0]["at"] if rows else None
    lo, hi, title, sub = bounds(art, offset, now, first)
    P = [e for e in rows if lo <= e["at"] < hi]
    before = [e for e in rows if e["at"] < lo]
    res = {"art": art, "offset": offset, "title": title, "sub": sub, "lo": lo, "hi": hi,
           "running": lo <= now < hi, "empty": not P, "total_rows": len(rows),
           "older": bool(before) and art != "a", "newer": hi <= now and art != "a"}
    if not P:
        return res
    elapsed_hi = min(hi, now)
    span_days = max(1, round((elapsed_hi - lo) / 86400 + 0.49))
    base = _basic(P)
    prev = None
    if art != "a":
        plo, phi, ptitle, _ = bounds(art, offset - 1, now, first)
        if art == "w" or art == "m" or art == "y":
            # laufender Zeitraum: fair vergleichen – nur bis zur gleichen Stelle des Vorzeitraums
            cut = phi if not res["running"] else plo + (now - lo)
            Q = [e for e in rows if plo <= e["at"] < min(phi, cut)]
            # Vorzeitraum nur, wenn das Protokoll ihn ganz abdeckt (sonst wären es Scheinzuwächse)
            if first is not None and first <= plo + 86400:
                prev = _basic(Q)
                prev["title"] = ptitle
                prev["partial"] = res["running"]
    res["base"], res["prev"], res["span_days"] = base, prev, span_days
    res["deltas"] = {k: _delta(base[k], prev[k]) if prev else None
                     for k in ("secs", "plays", "tracks", "artists", "albums", "days")}
    res["per_day"] = base["secs"] / span_days
    res["per_active_day"] = base["secs"] / max(1, base["days"])

    # ----- Titel / Künstler / Alben -----
    tr = {}
    ar = defaultdict(lambda: {"secs": 0.0, "plays": 0, "starts": 0, "skips": 0, "det": 0, "tracks": set(),
                              "aid": None, "days": set(), "first": None})
    al = {}
    for e in P:
        s, c = secs(e), counts(e)
        t = tr.setdefault(e["id"], {"id": e["id"], "t": e.get("t"), "a": e.get("a"), "d": e.get("d") or 0,
                                    "al": e.get("al"), "alid": e.get("alid"), "aid": e.get("aid"),
                                    "secs": 0.0, "plays": 0, "starts": 0, "skips": 0, "det": 0, "full": 0,
                                    "days": set(), "first": e["at"], "last": e["at"]})
        t["secs"] += s
        t["plays"] += c
        t["starts"] += 1
        t["days"].add(day_key(e["at"]))
        t["last"] = e["at"]
        if detailed(e):
            t["det"] += 1
            t["skips"] += skipped(e)
            t["full"] += complete(e)
        names = artists(e)
        for i, name in enumerate(names):
            x = ar[name]
            x["secs"] += s / len(names)
            x["plays"] += c
            x["starts"] += 1
            x["tracks"].add(e["id"])
            x["days"].add(day_key(e["at"]))
            if x["first"] is None:
                x["first"] = e["at"]
            if i == 0 and e.get("aid"):
                x["aid"] = e["aid"]
            if detailed(e):
                x["det"] += 1
                x["skips"] += skipped(e)
        if e.get("al"):
            k = e.get("alid") or e["al"]
            y = al.setdefault(k, {"al": e["al"], "alid": e.get("alid"), "a": names[0], "secs": 0.0, "plays": 0,
                                  "tracks": set()})
            y["secs"] += s
            y["plays"] += c
            y["tracks"].add(e["id"])
    first_track, first_artist, last_artist_before = {}, {}, {}
    for e in rows:
        first_track.setdefault(e["id"], e["at"])
        for a in artists(e):
            first_artist.setdefault(a, e["at"])
            if e["at"] < lo:
                last_artist_before[a] = e["at"]
    # „neu“ sagt nur etwas, wenn vor dem Zeitraum schon protokolliert wurde (sonst wäre im ersten alles neu)
    know_new = art != "a" and bool(before)
    res["know_new"] = know_new
    for t in tr.values():
        t["new"] = know_new and first_track.get(t["id"], 0) >= lo
        t["ndays"] = len(t.pop("days"))
    total = base["secs"] or 1
    art_rows = []
    for name, x in ar.items():
        art_rows.append({"name": name, "aid": x["aid"], "secs": x["secs"], "plays": x["plays"],
                         "starts": x["starts"], "share": x["secs"] / total * 100, "tracks": len(x["tracks"]),
                         "ndays": len(x["days"]), "new": know_new and first_artist.get(name, 0) >= lo,
                         "skip": _pct(x["skips"], x["det"]) if x["det"] else None, "det": x["det"],
                         "first": x["first"]})
    res["tracks"] = sorted(tr.values(), key=lambda t: (-t["plays"], -t["secs"]))
    res["tracks_time"] = sorted(tr.values(), key=lambda t: -t["secs"])
    res["artists"] = sorted(art_rows, key=lambda x: -x["secs"])
    res["albums"] = sorted(({"al": y["al"], "alid": y["alid"], "a": y["a"], "secs": y["secs"], "plays": y["plays"],
                             "tracks": len(y["tracks"])} for y in al.values()), key=lambda y: -y["secs"])

    # ----- Verlauf -----
    bl = buckets(art, lo, hi)
    tl = []
    for short, long_, blo, bhi in bl:
        sub_rows = [e for e in P if blo <= e["at"] < bhi]
        topa = Counter()
        topt = Counter()
        for e in sub_rows:
            for a in artists(e):
                topa[a] += secs(e) / len(artists(e))
            topt[(e.get("t"), e.get("a"))] += secs(e)
        tl.append({"short": short, "long": long_, "secs": sum(secs(e) for e in sub_rows),
                   "plays": sum(1 for e in sub_rows if counts(e)), "future": blo > now,
                   "now": blo <= now < bhi, "artist": topa.most_common(1)[0][0] if topa else None,
                   "track": topt.most_common(1)[0][0] if topt else None})
    res["timeline"] = tl
    days = defaultdict(float)
    for e in P:
        days[day_key(e["at"])] += secs(e)
    res["days"] = {d.isoformat(): v for d, v in days.items()}
    best_day = max(days.items(), key=lambda kv: kv[1])
    res["best_day"] = (best_day[0], best_day[1])

    # ----- Entdeckungen -----
    new_tracks = [t for t in tr.values() if t["new"]]
    res["new_tracks"] = sorted(new_tracks, key=lambda t: -t["secs"])
    res["new_artists"] = [x for x in res["artists"] if x["new"]]
    res["new_share"] = sum(t["secs"] for t in new_tracks) / total * 100
    res["comebacks"] = [x for x in res["artists"]
                        if not x["new"] and x["name"] in last_artist_before
                        and x["first"] - last_artist_before[x["name"]] >= COMEBACK_GAP]
    perday = Counter((e["id"], day_key(e["at"])) for e in P if counts(e))
    if perday:
        (vid, d), n = perday.most_common(1)[0]
        res["obsession"] = (tr[vid], d, n) if n >= 3 else None
    else:
        res["obsession"] = None
    res["evergreen"] = max(tr.values(), key=lambda t: (t["ndays"], t["plays"])) if tr else None
    # Ohrwurm: längste Folge aufeinanderfolgender Tage mit demselben Titel
    best = (0, None)
    by_track = defaultdict(set)
    for (vid, d) in perday:
        by_track[vid].add(d)
    for vid, ds in by_track.items():
        run = longest = 0
        prev_d = None
        for d in sorted(ds):
            run = run + 1 if prev_d and (d - prev_d).days == 1 else 1
            longest = max(longest, run)
            prev_d = d
        if longest > best[0]:
            best = (longest, vid)
    res["earworm"] = (tr[best[1]], best[0]) if best[0] >= 2 else None

    # ----- Gewohnheiten -----
    heat = [[0.0] * 24 for _ in range(7)]
    hours = [0.0] * 24
    for e in P:
        lt = time.localtime(e["at"])
        heat[lt.tm_wday][lt.tm_hour] += secs(e)
        hours[lt.tm_hour] += secs(e)
    res["heat"], res["hours"] = heat, hours
    res["wdays"] = [sum(r) for r in heat]
    parts = []
    for name, a, b in DAYPARTS:
        v = sum(hours[h % 24] for h in range(a, b))
        parts.append((name, v, v / total * 100))
    res["dayparts"] = parts
    peak = max(range(24), key=lambda h: hours[h])
    res["peak_hour"] = peak
    night = sum(hours[h] for h in (23, 0, 1, 2, 3, 4)) / total * 100
    morning = sum(hours[h] for h in range(5, 10)) / total * 100
    res["chronotype"] = ("nachteule" if night >= 25 else "frühaufsteher·in" if morning >= 25 else
                         "abendmensch" if sum(hours[h] for h in range(18, 23)) / total >= 0.45 else "tagsüber")
    firsts, lasts = defaultdict(lambda: 10 ** 12), defaultdict(float)
    for e in P:
        d = day_key(e["at"])
        firsts[d] = min(firsts[d], e["at"])
        lasts[d] = max(lasts[d], end_ts(e))
    sod = lambda ts, d: ts - _ts(d) + DAY_SHIFT        # Sekunden seit Mitternacht (über 24 h = nach Mitternacht)
    res["typ_first"] = _clock(_median([sod(firsts[d], d) for d in firsts]))
    res["typ_last"] = _clock(_median([sod(lasts[d], d) for d in lasts]))
    earliest_d = min(firsts, key=lambda d: sod(firsts[d], d))
    latest_d = max(lasts, key=lambda d: sod(lasts[d], d))
    res["earliest"] = (earliest_d, _clock(sod(firsts[earliest_d], earliest_d)))
    res["latest"] = (latest_d, _clock(sod(lasts[latest_d], latest_d)))
    wk = [0.0, 0.0]
    n_days = [0, 0]
    d = day_key(lo)
    last_d = day_key(elapsed_hi - 1)
    while d <= last_d:
        n_days[d.weekday() >= 5] += 1
        wk[d.weekday() >= 5] += days.get(d, 0.0)
        d += timedelta(days=1)
    res["workday_avg"] = wk[0] / n_days[0] if n_days[0] else None
    res["weekend_avg"] = wk[1] / n_days[1] if n_days[1] else None

    # ----- Sitzungen + Serien -----
    sess = []
    for e in P:
        if sess and e["at"] - sess[-1]["end"] <= SESSION_GAP:
            s = sess[-1]
            s["end"] = max(s["end"], end_ts(e))
            s["secs"] += secs(e)
            s["n"] += 1
        else:
            sess.append({"start": e["at"], "end": end_ts(e), "secs": secs(e), "n": 1})
    res["sessions"] = len(sess)
    res["session_avg"] = sum(s["secs"] for s in sess) / len(sess)
    res["session_tracks"] = sum(s["n"] for s in sess) / len(sess)
    res["session_longest"] = max(sess, key=lambda s: s["secs"])
    res["session_hist"] = [sum(1 for s in sess if a <= s["secs"] < b) for a, b in
                           ((0, 600), (600, 1800), (1800, 3600), (3600, 7200), (7200, 10 ** 9))]
    active = sorted(days)
    longest_run, run, start_run, best_run = 0, 0, None, (None, None)
    for i, d in enumerate(active):
        if i and (d - active[i - 1]).days == 1:
            run += 1
        else:
            run, start_run = 1, d
        if run > longest_run:
            longest_run, best_run = run, (start_run, d)
    res["streak"] = (longest_run, *best_run)
    all_days = sorted({day_key(e["at"]) for e in rows})
    cur = 0
    today = day_key(now)
    if all_days and (today - all_days[-1]).days <= 1:
        cur = 1
        for i in range(len(all_days) - 1, 0, -1):
            if (all_days[i] - all_days[i - 1]).days == 1:
                cur += 1
            else:
                break
    res["streak_now"] = cur if res["running"] else None
    gaps = [(active[i] - active[i - 1]).days - 1 for i in range(1, len(active))]
    res["longest_gap"] = max(gaps) if gaps else 0

    # ----- Hörverhalten -----
    det = [e for e in P if detailed(e)]
    res["det_n"] = len(det)
    if det:
        sk = [e for e in det if skipped(e)]
        res["skip_rate"] = _pct(len(sk), len(det))
        res["early_skip"] = _pct(sum(1 for e in sk if e.get("p", 0) < 10), len(det))
        res["skip_after"] = _median([e.get("p", 0) for e in sk]) if sk else None
        res["complete_rate"] = _pct(sum(1 for e in det if complete(e)), len(det))
        res["back_rate"] = _pct(sum(1 for e in det if e.get("why") == "zurück"), len(det))
        res["seeks"] = sum(e.get("sk", 0) for e in det) / len(det)
        res["pauses"] = sum(e.get("pa", 0) for e in det)
        res["pause_secs"] = sum(e.get("ps", 0) for e in det)
        res["errors"] = sum(1 for e in det if e.get("why") == "fehler")
        res["most_skipped"] = sorted((t for t in tr.values() if t["skips"] >= 2),
                                     key=lambda t: (-t["skips"], -t["starts"]))[:8]
        res["skip_artists"] = sorted((x for x in art_rows if x["det"] >= 5 and x["skip"] is not None),
                                     key=lambda x: -x["skip"])[:5]
        res["loyal_artists"] = sorted((x for x in art_rows if x["det"] >= 5 and x["skip"] is not None),
                                      key=lambda x: (x["skip"], -x["secs"]))[:5]
        vol = [(e.get("v"), secs(e)) for e in det if e.get("v") is not None]
        res["volume"] = sum(v * s for v, s in vol) / max(1, sum(s for _v, s in vol)) if vol else None
        res["liked_share"] = sum(secs(e) for e in det if e.get("lk")) / max(1, sum(secs(e) for e in det)) * 100
        res["xf_n"] = sum(1 for e in det if e.get("xf"))
        res["shuffle_share"] = _pct(sum(1 for e in det if e.get("sh")), len(det))
    repeats = sum(1 for i in range(1, len(P)) if P[i]["id"] == P[i - 1]["id"])
    res["repeats"] = repeats
    res["avg_len"] = sum(t["d"] for t in tr.values() if t["d"]) / max(1, sum(1 for t in tr.values() if t["d"]))
    full = [t for t in tr.values() if t["d"] and t["full"]]
    res["longest_full"] = max(full, key=lambda t: t["d"]) if full else None

    # ----- Quellen + Geräte -----
    def shares(key, names=None):
        c = Counter()
        for e in det:
            c[e.get(key) or "?"] += secs(e)
        tot = sum(c.values()) or 1
        return [((names or {}).get(k, k), v, v / tot * 100) for k, v in c.most_common()]
    if det:
        res["sources"] = shares("src", SRC_NAMES)
        named = Counter()
        for e in det:
            if e.get("sn") and e.get("src") in ("playlist", "album", "künstler", "radio", "suche"):
                named[(e["src"], e["sn"])] += secs(e)
        res["named_sources"] = [(SRC_NAMES.get(s, s), n, v) for (s, n), v in named.most_common(8)]
        res["kinds"] = shares("k")
        res["outputs"] = shares("out")
    # ----- Vielfalt -----
    sa = [x["secs"] for x in art_rows if x["secs"] > 0]
    if len(sa) > 1:
        tot = sum(sa)
        h = -sum(v / tot * math.log(v / tot) for v in sa)
        res["diversity"] = h / math.log(len(sa)) * 100
    else:
        res["diversity"] = 0.0
    res["top5_share"] = sum(x["share"] for x in res["artists"][:5])
    res["top1_share"] = res["artists"][0]["share"] if res["artists"] else 0
    plays_by = Counter(e["id"] for e in P if counts(e))
    res["repeat_share"] = _pct(sum(n for n in plays_by.values() if n >= 3), max(1, sum(plays_by.values())))
    res["one_off"] = sum(1 for n in plays_by.values() if n == 1)

    # ----- Meilensteine -----
    ms = []
    n = 0
    goals = iter(MILESTONES)
    goal = next(goals)
    for e in rows:
        if not counts(e):
            continue
        n += 1
        while goal is not None and n >= goal:
            if lo <= e["at"] < hi:
                ms.append((goal, e))
            goal = next(goals, None)
        if goal is None:
            break
    res["milestones"] = ms
    hours_total = 0.0
    hour_ms = []
    for e in rows:
        before_h = hours_total
        hours_total += secs(e) / 3600
        for g in (10, 50, 100, 250, 500, 1000, 2500, 5000):
            if before_h < g <= hours_total and lo <= e["at"] < hi:
                hour_ms.append((g, e))
    res["hour_milestones"] = hour_ms
    res["first"], res["last"] = P[0], P[-1]
    res["story"] = story(res)
    return res


# ---------- Text ----------
def dur(sec, short=False):
    sec = int(sec or 0)
    h, m = divmod(sec // 60, 60)
    if h >= 100:
        return f"{h}h"
    if h:
        return (f"{h}h {m}min" if m else f"{h}h") if not short else f"{h}h{m:02d}"
    if sec < 60:
        return f"{sec}s"
    return f"{m}min"


def delta_text(p):
    if p is None:
        return ""
    if abs(p) < 0.5:
        return "±0 %"
    return f"{'▲' if p > 0 else '▼'} {abs(p):.0f} %"


def story(r):
    """Ein paar Sätze Zusammenfassung – wie ein Rückblick, aber aus den echten Zahlen."""
    b = r["base"]
    word = {"w": "woche", "m": "monat", "y": "jahr", "a": "zeit"}[r["art"]]
    this = {"w": "diese woche", "m": "diesen monat", "y": "dieses jahr", "a": "insgesamt"}[r["art"]]
    if not r["running"] and r["art"] != "a":
        this = {"w": "in dieser woche", "m": "in diesem monat", "y": "in diesem jahr"}[r["art"]]
    out = []
    s = f"{this} hast du {dur(b['secs'])} musik gehört: {b['plays']} wiedergaben, {b['tracks']} verschiedene titel."
    d = r["deltas"].get("secs")
    if d is not None and r["prev"]:
        cmp = "bis zum gleichen zeitpunkt " if r["prev"].get("partial") else ""
        s += f" das sind {abs(d):.0f} % {'mehr' if d >= 0 else 'weniger'} als {cmp}{'in der' if r['art'] == 'w' else 'im'} " \
             f"vor{word if r['art'] != 'w' else 'woche'}."
    out.append(s)
    if r["artists"]:
        a = r["artists"][0]
        out.append(f"nr. 1 bei den künstlern: {a['name']} mit {dur(a['secs'])} ({a['share']:.0f} % deiner hörzeit"
                   f"{', neu entdeckt' if a['new'] else ''}).")
    if r["tracks"]:
        t = r["tracks"][0]
        out.append(f"meistgehörter titel: „{t['t']}“ – {t['plays']}× gehört.")
    if r.get("obsession"):
        t, d, n = r["obsession"]
        out.append(f"am {d.day}. {MON[d.month - 1]} lief „{t['t']}“ {n}× an einem tag.")
    if r["new_tracks"] and r["art"] != "a":
        na = len(r["new_artists"])
        out.append(f"neu für dich: {len(r['new_tracks'])} titel"
                   + (f" und {na} künstler" if na else "") + f" ({r['new_share']:.0f} % der hörzeit).")
    d, v = r["best_day"]
    out.append(f"stärkster tag: {WDAYS[d.weekday()]}, {d.day}. {MON[d.month - 1]} mit {dur(v)}. "
               f"meistens hörst du {DAYPARTS_TEXT.get(max(r['dayparts'], key=lambda p: p[1])[0], '')} "
               f"– am liebsten um {r['peak_hour']} uhr.")
    if r.get("skip_rate") is not None and r["det_n"] >= 10:
        out.append(f"{r['skip_rate']:.0f} % der titel hast du übersprungen, {r['complete_rate']:.0f} % bis zum ende gehört.")
    return out


DAYPARTS_TEXT = {"morgens": "morgens", "mittags": "mittags", "nachmittags": "nachmittags", "abends": "abends",
                 "nachts": "nachts"}
