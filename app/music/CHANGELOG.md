# musicalist – Änderungen

## 1.44.2 (2026-11-10)
- **Freunde sahen sich nicht mehr:** Der Relay ntfy.sh erlaubt je Internetanschluss nur 60 Anfragen / 5 min und 250 Nachrichten / Tag; musicalist fragte je Freund einzeln ab und sendete bei jedem Titelwechsel doppelt – das Limit war schnell voll (Fehler 429), Stände kamen nicht mehr an. Jetzt: eine einzige Anfrage für alle Freunde, Abfrage alle 60 s (Chat-Eingang 12 s), nach 429 90 s Pause ohne den alten Stand zu verlieren, ein neuer Titel wird erst nach 5 s gemeldet (eine statt zwei Nachrichten), unveränderter Stand wird nicht erneut gesendet, Herzschlag alle 4 min.

## 1.44.1 (2026-11-09)
- **Nutzername festlegen:** „keine verbindung – bitte später nochmal“ kam oft schon bei kurzer Überlast des Relays (ntfy.sh, 429). Anfragen werden jetzt mehrfach wiederholt, und bei echtem Scheitern steht der Grund da (überlastet / Serverfehler / kein Internet).

## 1.44.0 (2026-11-09)
- **Rückblick-Bilder (PNG 1080 × 1350):** Jeden Sonntagabend (ab 20 Uhr) entsteht ein Wochenbild im Terminal-Stil, am Monatsletzten ein Monatsplakat, am 31. Dezember ein Jahresbild (Mischung aus beidem). Die Farbe ist die Akzentfarbe der Person mit der meisten Hörzeit, das Cover gehört zu ihrem meistgespielten Lied, dazu die Ranglisten hörzeit / titel / künstler·innen aus deiner Freundesliste (nur was geteilt wird, Incognito fehlt). Hinweis ganz oben im Freunde-Tab, Desktop-Benachrichtigung, Seite „󰄨 rückblicke“ mit allen bisherigen Bildern (ansehen, herunterladen nach ~/Pictures/musicalist, Ordner öffnen).
- **Einstellungen → Freunde:** „bilder automatisch herunterladen“ (Standard aus) und „wochenbild jetzt testweise“.
- Das Profil des PCs enthält jetzt Akzentfarbe, Lied-Kennung und Monats-/Jahressummen, damit PC-Nutzer auch in den Bildern der Handy-App richtig erscheinen.

## 1.43.0 (2026-11-09)
- **Nutzername in den Einstellungen ändern** (Einstellungen → Freunde → „✎ ändern“). Gekoppelte Geräte übernehmen den neuen Namen beim nächsten Abgleich.
- **Top-Liste als Auswahl:** Die Rubrik wählst du per Dropdown; in der Auswahl steht je Rubrik rechts die Person auf Platz 1, gewählt wird die ganze Rangliste gezeigt.
- **Geräteliste eindeutig:** Gekoppelte Geräte stehen als „nutzername (gerätename)“, z. B. „anna (laptop)“, damit klar ist, was Name und was Gerät ist.

## 1.42.1 (2026-11-09)
- **Beim Namen-Zwang koppeln:** Im Fenster „wähle deinen nutzernamen“ gibt es jetzt „ich habe musicalist schon auf einem anderen gerät“ → Adresse und Code des anderen Geräts eintragen, koppeln übernimmt dessen Nutzernamen (gekoppelte Geräte teilen denselben Namen). Dafür gleichen sich Freunde und Name jetzt auch ab, wenn der PC das andere Gerät abfragt bzw. das Handy vom PC abgefragt wird (bisher nur Handy → PC).

## 1.42.0 (2026-11-09)
- **Nutzername statt Code:** Beim nächsten Start musst du einmal einen Nutzernamen festlegen (3–20 Zeichen, gespeichert lokal). Freunde findest du nur noch über den Namen: Namen eingeben → Anfrage → die Person bestätigt (annehmen/ablehnen); erst dann tauschen die Geräte verschlüsselt ihre Schlüssel aus. Der Code ist aus der Oberfläche verschwunden, bestehende Freunde bleiben. Namen sind „wer zuerst kommt“ (ohne Server nur bestmöglich). Gekoppelte Geräte (PC + Handy) teilen denselben Namen; bei Streit gilt der zuletzt geänderte.
- **Gekoppelte Geräte gelten als eine Person:** Läuft am PC Musik und das Handy ist ruhig, sehen Freunde jetzt die laufende Musik (je Gerät zählt die letzte Meldung, spielendes Gerät gewinnt; Incognito eines Geräts gilt für alle). Beide Geräte und die Freunde brauchen dafür die neue Version.
- **Update-Popup:** musicalist sieht ab und an (alle 30 min, Abfrage höchstens alle 6 h) nach Updates und zeigt bei einer neuen Version ein Popup („später“ / „jetzt aktualisieren“), höchstens einmal je 24 h und Version.

## 1.41.0 (2026-11-09)
- **Chat im Telegram-Stil:** Uhrzeit klein in der Blase statt in einer eigenen Zeile, gleiche Person kurz hintereinander rückt zusammen, Tagestrenner („heute“, „gestern“). Das Bild im Chat-Kopf liegt auf einer Kachel in der Hintergrundfarbe und ist damit auch bei „hört gerade“ (Akzentfüllung) sichtbar.
- **Nachricht genauer ansehen:** Rechtsklick oder lange drücken auf eine Nachricht zeigt gesendet/gelesen-Zeiten und Aktionen (kopieren, abspielen, einreihen, zurücknehmen).
- **Größeres Eingabefeld:** mehrzeilig, wächst mit dem Text bis ca. 6 Zeilen; Enter sendet, Umschalt+Enter = neue Zeile.
- **Gelesen-Markierungen:** ○ gesendet, ● gelesen (am Handy und PC; abschaltbar unter Einstellungen → Freunde → „lesebestätigungen senden“).
- **Profil:** listet alle Musikempfehlungen zwischen euch („von dir empfohlen“, „hat dir empfohlen“).

## 1.40.0 (2026-11-09)
- **Chat überarbeitet:** Chat und Profil einer Person sind jetzt eigene Seiten im Zurück-Stapel – 2-Finger-Zurück zeigt beim Verlassen die gewohnte Animation. Eigene Nachrichten stehen rechts gefüllt (Akzentfarbe), fremde links mit Rahmen; Lieder sind entsprechend umrahmt.
- **„󰝚 musik“-Knopf** (statt „󰝚“) öffnet ein Menü: aktueller Song oder anderer Song (Suche direkt im Menü). Feld, „musik“ und „senden“ sind gleich hoch.
- **Nachricht zurücknehmen:** Bis 5 Minuten nach dem Senden erscheint „󰕌 zurücknehmen“; die Nachricht verschwindet auch beim anderen (neue Version nötig).
- **Hörprofil grafisch** und mit größerer Schrift: große Hörzeit, Balken für Künstler und Titel, Meter für Kennzahlen.
- **Incognito** (Einstellungen → Freunde): 15 min, 30 min oder bis du es ausschaltest. Andere sehen weder Lied noch „zuletzt gehört“ noch Profil, aber „󰗹 incognito“ (mit Ende). Der **Umfang** wird nur noch in den Einstellungen gewählt.
- **Wer gerade hört** ist in der Liste und im Chat-Kopf mit umgekehrten Farben hervorgehoben (Füllung in der Akzentfarbe, Schrift in der Hintergrundfarbe).

## 1.39.0 (2026-11-09)
- **Chat mit Freund·innen:** In der Freunde-Liste (Hörverlauf → freunde) steht unter der Top-Liste für jede Person ein Container mit Name und aktuellem Lied (ohne Bild). Antippen öffnet den Chat: oben Name und aktuelles Lied mit Bild (anklicken → Profil mit allen Angaben: empfiehlt, zuletzt gehört, Hörprofil, entfernen), darunter der Verlauf, unten Eingabe, „󰝚“ schickt den laufenden Titel. Lied-Empfehlungen („direkt an …“) landen jetzt ebenfalls im Chat und bleiben dort stehen; ungelesene Nachrichten zeigen „n neu“. Gleiches verschlüsseltes Protokoll wie in der Handy-App (0.25.0); ältere Versionen sehen Lieder weiter im Eingang, reine Texte nicht.
- **Zeitangaben** überall als „2h 16min“ statt Dezimalstunden (Analyse, Hörprofil und Top-Liste der Freunde).

## 1.38.1 (2026-11-09)
- **Podcasts überarbeitet:** Ein Klick auf den „Künstler“ einer Podcast-Folge öffnet jetzt den Podcast (YouTube hat für Podcasts keine Künstlerseite). Der Album-Knopf (Steuerung, Fernseher-Modus) und das Titelmenü führen bei Folgen zum Podcast statt zur Fehlermeldung „zu diesem titel ist kein album bekannt“. „An freund·in empfehlen“ gilt für Folgen wie für Songs. Podcast-Folgen, die jemand von der Handy-App empfiehlt, spielen jetzt auch am PC (direkt aus dem Feed, ohne YouTube-Funktionen wie Liken oder Radio).

## 1.38.0 (2026-11-09)
- **Abgleich mit weiteren Geräten, nicht nur Rechnern:** Unter „handy-app“ → „weiteres gerät“ verbindest du dich jetzt auch mit **musicalist auf einem anderen Handy** (dort „koppeln lassen“ drücken, Adresse und Code hier eintragen) – oder mit weiteren Rechnern wie bisher. Beliebig viele Geräte, Ketten funktionieren (Handy – PC – Handy). Neue Hörprotokoll-Einträge tragen den Gerätenamen (`dn`) für die Analyse.

## 1.37.0 (2026-11-09)
- **Mehrere Rechner verknüpfen:** Einstellungen → „handy-app“ → **weiterer rechner**. Am einen Rechner „handy koppeln“ drücken (Adresse + Code erscheinen), am anderen Adresse und Code eintragen → „verbinden“. Danach gleichen sich die Hörprotokolle im WLAN alle 5 Minuten (und per „jetzt“) in beide Richtungen ab, sodass Hörzeit, Analyse und Rückblick auf jedem Gerät alles zusammenrechnen. Es läuft auch über Ketten (Handy – PC 1 – PC 2): jedes Gerät gibt auch Einträge anderer weiter; doppelte werden übersprungen. Gleiches verschlüsseltes Protokoll wie beim Handy, Port 37526/tcp muss am Rechner mit dem Code offen sein. Neue Einträge tragen eine Gerätemarke (`dev`).

## 1.36.0 (2026-11-09)
- **Spotify-Import:** Einstellungen → „von spotify importieren“. Den Datenexport von Spotify (Privatsphäre → „Deine Daten herunterladen“, Kontodaten) als ZIP/Ordner wählen; Playlists und gespeicherte Titel werden gelesen, jeder Titel in YouTube Music gesucht (Abgleich von Titel und Künstler) und als private Playlist angelegt. Gleichnamige vorhandene Playlists werden nur ergänzt, Treffer werden gemerkt (Abbruch/Wiederholung ist schnell), nicht gefundene Titel stehen in `spotify_nicht_gefunden.txt`. Braucht die Anmeldung.

## 1.35.0 (2026-11-09)
- **Freunde: gekoppelte Geräte sind eine Person.** Sind Handy und PC gekoppelt, senden beide ihren Stand an beide Freundes-Codes; wer nur einen Code hat, sieht trotzdem die gemeinsame Hörzeit (aus dem zusammengeführten Hörprotokoll) und das gemeinsame „zuletzt gehört“. Bestehende Codes bleiben gültig, der eigene zweite Code taucht nicht in der Freundesliste auf. Wirkt, sobald beide Geräte die neue Version haben und einmal abgeglichen haben.
- **Top-Liste am Wochenanfang:** Freunde, die diese Woche (seit Montag 4 Uhr) noch nichts gesendet haben, stehen unter „ohne Angabe“ statt mit den Stunden der Vorwoche – deine eigene Zeit wird ja ebenfalls zurückgesetzt.

## 1.34.2 (2026-11-08)
- **QR-Code der Marmelade überarbeitet:** Er ließ sich nicht scannen (helle Module auf dunklem Grund und nur 1 Modul Rand). Jetzt immer dunkle Module auf heller Fläche mit vollem Rand, aber in den Farben des Designs statt auf reinem Weiß (die hellere von Vordergrund/Hintergrund ist die Fläche). Gilt für Marmelade-Kasten und Fernseher-Modus; mit einem QR-Leser gegengeprüft.

## 1.34.1 (2026-11-08)
- **Laufzeiten in „als nächstes“ und in der Warteschlange:** Titel, die ohne Länge hereinkommen (z. B. Empfehlungen von Freund·innen, Links, manche Radio-Treffer), bekommen sie jetzt im Hintergrund nachgetragen – die Zeit erscheint kurz nach dem Einreihen.

## 1.34.0 (2026-11-08)
- **Marmelade: Ultra-Gäste** dürfen jetzt auch die **Lautstärke** des Gastgebers ändern (Regler überall in der App, im Browser ein Schieberegler) und unter „warteschlange“ die **Reihenfolge** ändern (ziehen, ↑/↓, „vorziehen“; im Browser ↑ ↓). Alle anderen Gäste sehen die Lautstärke, ändern sie aber nicht. Protokoll: `ctl`-Befehle `volume` und `move`, im Stand `vol`.
- **Fernseher-Modus: „als nächstes“** zeigt bis zu 25 Titel und ist scrollbar; der Kasten samt Rand ist immer vollständig zu sehen (nichts wird mehr unten abgeschnitten).
- **Lautstärke/Zeitleiste:** Der kleine Strich unter dem Regler nach dem Anklicken ist weg.

## 1.33.0 (2026-11-08)
- **Lyrics:** Die Quellenangabe „lrclib“ unter dem Songtext ist weg (Fernseher-Modus und Lyrics-Seite); nur Hinweise wie „ohne zeitstempel“ oder der Versatz bleiben.
- **Marmelade: Ultra-Modus.** Der Gastgeber kann jedem Gast neben „rechte“ auch „󰓎 ultra“ geben: alle Rechte des Gastgebers fürs Abspielen. Ultra-Gäste spielen einen angeklickten Titel (Suche, Bibliothek, Playlists) **sofort beim Gastgeber** statt ihn nur einzureihen, springen in der Warteschlange mit einem Klick zu einem Titel und dürfen weiter überspringen, pausieren, spulen und entfernen. Gilt nur für die laufende Marmelade. Normale Gäste reihen wie bisher ein.
- Browser-Gäste mit Ultra sehen „▶ jetzt“ bei Suchergebnissen und „▶“ in der Warteschlange. Protokoll: `ctl`-Befehle `play` und `jump`, im Stand `you.ultra` bzw. `ultras` (ältere Handy-Apps ignorieren das, bleiben aber kompatibel).

## 1.32.3 (2026-11-08)
- **Fernseher-Modus: Lyrics** liegen in einem festen Ausschnitt, der nie seine Größe ändert. Beim Wechsel zur nächsten Zeile scrollt die aktuelle Zeile weich in die Mitte, statt zu springen; alle Zeilen haben dieselbe Schriftgröße.
- **Nie scrollbar:** Der Modus passt sich der Fensterhöhe an (bei Platzmangel wird alles etwas kleiner) und lässt sich auch mit Mausrad/Touchpad nicht verschieben – alles steht auf einen Blick da.
- **„andere quellen“** gibt es im Fernseher-Modus nicht mehr.

## 1.32.2 (2026-11-08)
- **Live-Spektrum auf Ubuntu repariert:** Ubuntu 24.04 liefert cava 0.7.4, das die Eingabe „pipewire“ nicht kennt und sofort abbricht – musicalist wechselt jetzt selbst auf „pulse“ (läuft auch unter PipeWire) und merkt sich, was funktioniert. Das Spektrum sieht damit überall gleich aus statt der Ersatzrechnung über mpv.
- **Fernseher-Modus:** Beim Wechsel in/aus dem Vollbild konnte eine zweite Spektrum-Leiste erscheinen – behoben.
- **Spektrum im Energiesparmodus** bleibt standardmäßig sichtbar (Schalter in den Einstellungen).
- **Installer** installiert cava einzeln nach, falls es fehlt (auch beim Update; Ubuntu: „universe“ wird bei Bedarf eingeschaltet).

## 1.32.1 (2026-11-08)
- **Fernseher-Modus: Leiste bearbeiten** (Stift oben oder Rechtsklick auf die Leiste): Kästen per Haken ein-/ausblenden und mit ← → ordnen. Zusätzlich wählbar: Schlaf-Timer, Klang/Mixer, Autoplay, Künstler, Album, empfehlen. „zurücksetzen“ stellt die Standardleiste her.

## 1.32.0 (2026-11-08)
- **Fernseher-Modus im Look der Handy-App:** Zurück / Play (gefüllt) / Weiter als drei große gleich breite Kästen, darunter eine Reihe gleich breiter Symbol-Kästen (mischen, wiederholen, gefällt mir, gefällt mir nicht, Playlist, Radio, Browser, Menü, Raster); aktive Kästen sind gefüllt. Die Seite passt sich der Fensterbreite an (kein Überlaufen mehr, auch bei 1366 × 768).
- **Hören · Freunde:** „freunde“ ist kein eigener Tab mehr, sondern mit dem Hörverhalten (Analyse) in Tab 7 zusammengelegt – oben wählst du zwischen „hörverhalten“ und „freunde“.
- **Raster einstellen:** Rechtsklick (oder langes Drücken) auf den Raster-Knopf öffnet wie am Handy die Einstellungen: Vorschau, Presets (fein, punktraster, gameboy, 8-bit farbig, zeitung), Form, Auflösung, Punktgröße, Farbe, Kontrast, Helligkeit ausgleichen, umkehren, Rasterung. Gilt für alle Titelbilder.

## 1.31.0 (2026-11-08)
- **Freunde ist jetzt ein eigener Tab** (⁸ freunde, Alt+8), nicht mehr in der Bibliothek.
- **Raster / Foto** wie in der Handy-App: Knopf 󱗼 in der Leiste unter „steuerung“ (unter Anpassen an-/abschaltbar) und im Fernseher-Modus schaltet alle Titelbilder gleichzeitig zwischen Punktraster und echtem Foto um.
- **Schnellauswahl** im Look der App: Punktraster-Kacheln mit Rahmen und Hover (bzw. Fotos bei ausgeschaltetem Raster).
- Fernseher-Modus: Steuerung im gleichen Stil wie auf „jetzt“ (nur größer), Lautstärke oben rechts im Kasten „läuft“, „als nächstes“ genau so hoch wie „lyrics“.
- Die Steuerung im normalen Modus ist wieder wie vorher (Änderung aus 1.30 zurückgenommen).

## 1.30.0 (2026-11-08)
- **Fernseher-Modus** (Knopf 󰔂 in der Kopfzeile, Taste `t`, `musicalist tv`): Vollbild mit derselben Oberfläche wie „jetzt“, nur groß – Cover, Titel, alle Knöpfe (gefällt mir / gefällt mir nicht, Playlist, Radio, Browser, Titel-Menü), Zeitleiste, Zurück/Play/Weiter, mischen, wiederholen, Sleep-Timer, Klang, Autoplay, Lautstärke, mitlaufende Lyrics, „als nächstes“, andere Quellen und das Spektrum über die ganze Breite. Passt sich der Auflösung an (720 p bis 4K), Meldungen erscheinen oben, der Bildschirm bleibt wach. Zurück mit `t`, Esc, einer Zifferntaste oder dem Knopf oben rechts.
- **Spektrum läuft jetzt überall:** fehlt cava (Windows, GNOME ohne PipeWire …) oder liefert es nichts, misst mpv selbst (18 Frequenzbänder per Audiofilter, automatische Empfindlichkeit). Der Wechsel passiert von allein nach 3 s; erzwingen unter einstellungen („spektrum ohne cava berechnen“). Mit Überblenden zeigt es beide Titel.
- **Gefällt mir nicht** (Knopf 󰔒 auf „jetzt“, Taste `d`, Titelmenü): der Titel wird übersprungen, kommt nicht mehr in Radio/Autoplay und wird bei YouTube Music als Daumen runter gemeldet (wie in der Handy-App; ohne Anmeldung nur lokal gemerkt). Herz und Daumen runter schließen sich aus.
- Fernseher-Modus: Knopf „marmelade“ oben (startet eine Marmelade und zeigt Code, QR-Code, Gäste, Anklopfen; beenden/verlassen), Lautstärke oben rechts, Sleep-Timer/Klang/Autoplay weggelassen, die Kästen unten gehen bis zum Spektrum.
- Steuerung auf „jetzt“ wie in der Handy-App: Zeitleiste oben, darunter drei gleich breite Kästen, Play gefüllt.
- Fix: das eingebaute Spektrum kam in Blöcken von mehreren Sekunden an (gepufferte Pipe) und ruckelte – jetzt zeilenweise über das mpv-Log, 20 Bilder/s, weniger Rechenzeit.
- Fix: Stift-Menü (Anpassen) schnitt unten Kästen ab (feste Höhe passend zum Fenster); Stift mit mehr Abstand zu ¹ jetzt; Spektrum unten niedriger, damit mehr „als nächstes“ passt.
- Fix: nach einem mpv-Neustart fehlten Equalizer/Filter.

## 1.29.0 (2026-11-08)
- **Freunde: Wochen-Topliste** ganz oben: du und deine Freunde, nach Rubrik (hörzeit, wiederholungen eines Titels, titel, künstler, lieblingskünstler, durchhörer). Neue Rubriken vielfalt, entdecker, serie (nur bei umfang „mehr“, das zusätzlich Chronotyp, Vielfalt, Anteil Lieblingskünstler, Wiederholer-Anteil, neue Künstler, Durchhör-Quote und Serie in die Analyse-Zeile legt – gleich viele Titel wie „normal“). Gerechnet wird nur aus dem, was geteilt wird; wer nur „minimal“ teilt, erscheint nur bei hörzeit.

## 1.28.0 (2026-11-08)
- **Freunde → ich → umfang:** was Freunde von dir sehen, stellst du auf minimal (läuft gerade, letzte 5 Titel, gehörte Stunden der Woche), normal oder mehr (Standard; längere Listen) ein. Die Karte „so sehen dich freunde“ zeigt immer genau das Gesendete.

## 1.27.0 (2026-11-08)
- **Anpassen** (Stift oben links neben dem Logo): Leiste unter „steuerung“ (Knöpfe an/aus, ↑ ↓ ordnen; neu: lyrics, künstler, album, empfehlen, titel-menü), Reihenfolge der Bibliothek-Kästen und Anzahl der Schnellauswahl; Link zum Klang-Mixer.
- **Schnellauswahl** in der Bibliothek: nur Titelbilder (Anzahl 5 bis 50, die Spalten folgen der Fensterbreite), Klick = spielen, Rechtsklick = Titelmenü, „neu“ mischt neu. Geht auch ohne Anmeldung.

## 1.26.0 (2026-11-08)
- **Herz auch ohne Anmeldung:** „gefällt mir“ merkt sich den Titel lokal (Bibliothek → „lieblingssongs (nur hier)“). Beim Anmelden werden die Herzen zu YouTube Music übernommen.
- **Analyse:** bei „top titel“ gibt es „top 50 spielen“, „mischen“ und „als playlist“ (Playlist in YouTube Music).
- **Rückgängig:** Nach dem Entfernen aus der Warteschlange erscheint 3 Sekunden lang „rückgängig“.
- **Liedtext-Symbol:** Mikrofon statt Übersetzungs-Zeichen.

## 1.25.0 (2026-11-08)
- **Freunde werden mit dem Handy abgeglichen** (beim Handy-Abgleich): Freunde, die du nur am Handy hast, erscheinen am PC und umgekehrt; Entfernen gilt auf beiden Geräten.
- **Freundschaft ist beidseitig:** Wer deinen Code hinzufügt, ist automatisch auch dein Freund (er meldet sich in deinem Thema, du siehst „… hat dich hinzugefügt“).

## 1.24.0 (2026-11-08)
- **Freunde: „so sehen dich freunde“** zeigt genau, was gesendet wird. Neu im Stand: kurzes **Wochenprofil** (Stunden, Titel, Künstler, Top 5 Künstler, Top 3 Titel, Lieblingsstunde); bei Freunden unter „hörprofil“.
- **Empfehlung direkt an einen Freund** (Titelmenü → „direkt an …“); er sieht sie unter „für dich empfohlen“. „an alle freunde empfehlen“ wie bisher.
- „Stand teilen“ ist jetzt **standardmäßig an** und steht auch in den Einstellungen.
- Erneut auf den Tab „suchen“ klicken leert die Suchleiste.

## 1.23.0 (2026-11-07)
- **Freunde** (Bibliothek → freunde): Jeder hat einen eigenen Code. Mit dem Code deines Freundes siehst du, was er gerade hört (live), zuletzt gehört und seine Empfehlungen – und umgekehrt. Nur wer den Code kennt, kann lesen (Ende-zu-Ende verschlüsselt, wie die Marmelade; auch zwischen PC und Handy-App 0.9.0).
- Geteilt wird nur, wenn du „meinen stand teilen“ einschaltest (Default aus). „Neuer code“ sperrt alle bisherigen Freunde aus.
- Im Titelmenü: **freunden empfehlen**.
- **Gekoppelte Geräte haben in der Marmelade immer Rechte:** Dein Handy darf am PC (und der PC am Handy) ohne Nachfragen steuern.

## 1.22.0 (2026-11-07)
- **Marmelade im WLAN anklicken = beitreten.** Ohne Code klopfst du an: Beim Gastgeber (PC oder Handy) erscheint „… möchte beitreten“ mit „reinlassen“. Gemerkte Geräte kommen sofort rein. Mit eingetipptem Code geht es wie bisher direkt.
- Als Gastgeber siehst du Anklopfende oben im Marmeladen-Kasten, auch wenn er eingeklappt ist.
- **Cover-Raster bei hellem Design** ist kein Negativ mehr: Die Punkte zeigen jetzt die dunklen Stellen, wenn die Akzentfarbe dunkler als der Hintergrund ist.

## 1.21.0 (2026-11-07)
- **Marmelade: alle sehen dasselbe.** Als Gast zeigen „jetzt“, die Warteschlange, die Vorschau und MPRIS, was beim Gastgeber läuft, mit mitlaufender Zeit. Deine eigene Wiedergabe pausiert solange und ist nach dem Verlassen wieder da.
- **Steuern als Gast:** Mit Gastgeber-Rechten steuern Zurück, Play/Pause, Weiter und die Zeitleiste die Marmelade. Ohne Rechte sind die Knöpfe ausgegraut.
- **Farben je Person:** Titel von Gästen haben ein Namensschild in einer festen Farbe, auch in der Gästeliste und auf der Browser-Seite. Am Handy hat dieselbe Person dieselbe Farbe.
- **Beitreten im WLAN klappt zuverlässiger:** Es werden alle Adressen des Gastgebers probiert, nicht nur die erste. Geht es weder im WLAN noch übers Internet, steht da, woran es lag.
- **Keine doppelten Lieder mehr in Radio und Autoplay**, wenn dasselbe Lied mit anderem Künstler, als feat.-Fassung, Remaster oder Musikvideo vorkommt.

## 1.20.0 (2026-11-07)
- **Jam heißt jetzt Marmelade** 🍓: überall in der Oberfläche und auf der Browser-Seite für Gäste. Technisch bleibt alles gleich: Ältere Versionen finden die Marmelade weiter und treten mit dem Code bei.
- **Jam: Rechte für Gäste.** Als Gastgeber kannst du jedem Gast in der Jam-Liste Gastgeber-Rechte geben. Wer Rechte hat, kann überspringen, zurückgehen, pausieren und Titel aus der Warteschlange nehmen, aus der App, vom PC oder im Browser.
- **Geräte merken:** Ein gemerktes Gerät hat in jeder deiner Jams sofort Rechte.
- **Gäste entfernen:** Ein entfernter Gast kann bis zum Ende dieser Jam nicht wieder beitreten.
- **Jam umbenennen** (Stift-Knopf): Gäste sehen den neuen Namen sofort, auch in der Jam-Suche im WLAN.
- Der Jam-Kasten lässt sich einklappen. Als Gast mit Rechten bleiben die Steuerknöpfe dann sichtbar.
- Gleiches Protokoll wie die Handy-App 0.6.0. Ältere Versionen können weiter beitreten, aber keine Rechte bekommen.

## 1.19.0 (2026-11-07)
- **Jam auch übers Internet**: Klappt jetzt auch in WLANs, die Geräte voneinander trennen (Uni, Hotel, Gäste-WLAN), und über mobile Daten. Die Jam läuft dann zusätzlich über den Relay-Dienst ntfy.sh – Ende-zu-Ende verschlüsselt, Schlüssel und Thema kommen nur aus dem Jam-Code, der Dienst sieht nur Kauderwelsch.
- **Ein Code für alles** (6 Zeichen statt 4 Ziffern): im selben WLAN direkt, sonst automatisch übers Internet. Browser-Gäste ohne App (QR-Code) gehen weiterhin nur im selben WLAN. Geht der Port im WLAN nicht (Firewall), läuft die Jam trotzdem übers Internet.

## 1.18.0 (2026-11-07)
- **Jam im WLAN** (wie Spotify Jam, gleich wie in der Handy-App): In der Warteschlange gibt es den Kasten „jam“. „jam starten“ zeigt einen 4-stelligen Code, die Adresse und einen QR-Code. Andere treten mit der Handy-App bei (die Jam wird im WLAN gefunden), mit musicalist auf einem anderen PC („jam beitreten“) oder ohne App im Browser (QR-Code scannen). Gäste sehen, was läuft, suchen und fügen Titel hinzu; sie können nicht überspringen oder pausieren. Ihre Titel landen vor Radio/Autoplay, mit ihrem Namen.
- Als Gast schicken „abspielen“, „als nächstes“ und „+“ den Titel an den Gastgeber, statt ihn selbst zu spielen. Der Kasten zeigt, was dort läuft und als Nächstes kommt.
- **Anhängen** reiht jetzt vor Radio/Autoplay ein (wie „Warteschlange“ bei Spotify), statt hinter 25 Radio-Titel.
- Der Gastgeber braucht Port 37530/tcp in der Firewall (z. B. `sudo ufw allow 37530/tcp`; NixOS: `programs.musicalist.openFirewall = true`). Neues Paket `qrcode` für den QR-Code (ohne geht alles, nur ohne Bild).
- Analyse: Quellen „entdecken“ und „jam“ (aus der Handy-App) haben eigene Namen.

## 1.17.0 (2026-11-07)
- **Abgleich mit der Handy-App im WLAN**: In den Einstellungen gibt es den neuen Kasten „handy-app“. Ein Klick auf „handy koppeln“ zeigt einen Code und die Adresse für 3 Minuten. Danach werden die Hörprotokolle von Handy und PC zusammengeführt, und die Analyse zeigt alles, was du irgendwo gehört hast. Auf Wunsch übernimmt das Handy die YouTube-Anmeldung von hier.
- Gekoppelt wird per Schlüsseltausch mit Code-Bestätigung, danach ist jeder Abgleich verschlüsselt und signiert. Nur gekoppelte Geräte bekommen Antwort, und ein falscher Code beendet die Kopplung. Der Abgleich läuft erst, nachdem einmal gekoppelt wurde, und braucht Port 37526/tcp in der Firewall (z. B. `sudo ufw allow 37526/tcp`; NixOS: `programs.musicalist.openFirewall = true`). Ist `zeroconf` installiert, findet das Handy den PC von selbst, sonst tippt man die Adresse ein.
- Analyse: Die Quelle „startseite“ (Titel von der YouTube-Music-Startseite) hat jetzt einen eigenen Namen.

## 1.16.0 (2026-11-06)
- **Neuer Tab 7 „analyse“**: dein Hörverhalten im Detail, für eine **Woche, einen Monat, ein Jahr oder insgesamt**. Mit ‹ › (Bild↑/Bild↓) blätterst du zurück, `w` `m` `j` `g` wählen den Zeitraum. Verglichen wird mit dem Zeitraum davor, bei laufenden Zeiträumen fair bis zum gleichen Zeitpunkt.
  Zu sehen sind: Zusammenfassung in Sätzen, Kennzahlen mit Veränderung, Verlauf als Säulen und Kalender-Heatmap, Top-Titel (nach Wiedergaben oder Hörzeit), Top-Künstler und Top-Alben (anklickbar), Entdeckungen und Comebacks, Obsession, Ohrwurm und Dauerbrenner, eine Heatmap Wochentag × Uhrzeit, Tageszeiten, typischer Start und typisches Ende, Sitzungen und Serien, Überspringen, Spulen und Pausen, Quellen (Radio, Playlists …) und Geräte (Kopfhörer, Lautsprecher, Bluetooth), Vielfalt, Geschmack im Verlauf und Meilensteine. Über jedem Diagramm zeigt ein Tooltip die genauen Werte.
- **Rückblicke**: Ist eine Woche, ein Monat oder ein Jahr vorbei, meldet die Statuszeile „dein …rückblick ist da“. Tab 7 öffnet dann direkt diesen Zeitraum.
- **Genaues Hörprotokoll** (`hoerprotokoll.jsonl`, nur lokal, nur bei eingeschaltetem Hörverlauf, im Tab löschbar): Jeder angespielte Titel wird festgehalten, auch kurz übersprungene. Dazu kommen die echte Hörzeit ohne Spulen und Pausen, wie er endete, Quelle, Album, Like, Lautstärke und Ausgabegerät. Die Einträge des bisherigen Rückblicks werden übernommen. Der Rückblick in der Bibliothek führt jetzt zum neuen Tab.
- Windows-Installer: Das Hörprotokoll bleibt bei Updates erhalten.

## 1.15.1 (2026-11-06)
- **NixOS**: musicalist gibt es jetzt als Nix-Flake (`flake.nix` im Repo) mit Paket, home-manager-Modul (`programs.musicalist.enable`, optional `autostart` als Benutzerdienst) und NixOS-Modul. Damit gehört musicalist zur Konfiguration und überlebt jeden Rebuild. Anleitung im README unter „nixos / nix“.
- Liegt das Programm schreibgeschützt (wie im Nix-Store), speichert musicalist Anmeldung, Einstellungen und Verlauf in `~/.local/share/musicalist`, und yt-dlp aktualisiert sich nach `~/.local/share/musicalist/pylibs`. Bei der normalen Installation ändert sich nichts, alles bleibt am alten Ort.
- Geprüft: Build mit nixpkgs 26.05 und unstable (Python 3.13/3.14), Start, Suche, Abspielen, yt-dlp-Update sowie beide Module.

## 1.15.0 (2026-11-01)
- **Scroll-Ende**: Wer am Ende einer Seite weiterscrollt, sieht aus der Kante einen Verlauf aus ░ ▒ ▓ █ aufsteigen, am Mauszeiger am höchsten. Die Liste bewegt sich dabei nicht und der Effekt läuft ohne Überschwingen aus. Er erscheint nur, wenn kein umgebendes Scroll-Fenster mehr weiterscrollen kann. Abschalten: `"scroll_end": false` in ~/.config/rice-apps/settings.json oder Energiesparmodus.

## 1.14.1 (2026-10-28)
- **Absturz in der Warteschlange behoben**: Beim ersten Überfahren einer Zeile mit der Maus stürzte musicalist ab (GTK-Absturz, weil sich ein Maus-Controller mitten in seinem eigenen Signal entfernte). Das Anhängen der Zieh-Funktion und die „weitere anzeigen“-Knöpfe laufen jetzt im Leerlauf. Der Fehler kam mit 1.13.0 (Drag&Drop erst beim Überfahren anhängen) und wurde mit echter Mausbewegung nachgestellt.

## 1.14.0 (2026-10-28)
- **Überblendung (Crossfade)**: Der nächste Titel startet unter dem Ende des aktuellen (gegenläufig aus- und eingeblendet, gleiche Lautstärke wie du sie eingestellt hast). Auswahl 2, 4, 6, 8 oder 12 Sekunden im neuen Klang-Menü, Standard aus. Es läuft ein zweiter mpv im Hintergrund. Der Wechsel bleibt normal, wenn der nächste Titel noch nicht geladen ist, bei „Wiederholen: eins“, beim Sleep-Timer „nach diesem Titel“ und bei sehr kurzen Titeln. Pause, Springen und Spulen brechen eine Überblendung sauber ab.
- **Equalizer** (Knopf 󰓃 auf „jetzt“, Taste `e`): zehn Bänder von 31 Hz bis 16 kHz (±12 dB), Vorverstärker und Presets (flach, bass+, höhen+, stimme, loudness, rock, elektro, akustik). Wirkt sofort, wird gespeichert und gilt auch bei der Überblendung. Anhebungen senken den Gesamtpegel etwas, ein Limiter verhindert Übersteuern.
- **Fix: Fortsetzen nach dem Neustart ging mit mpv 0.37 nicht** (Ubuntu 24.04, Linux Mint 22): mpv lehnte die Startposition als „invalid parameter“ ab, und der gespeicherte Titel startete gar nicht. Die Befehlsform wird jetzt nach der mpv-Version gewählt (ab 0.38 anders). Gleiches galt nach einem mpv-Absturz.
- **Windows-Installer**: Beim Aktualisieren/Entfernen bleiben jetzt auch `listens.json` (Rückblick) und `offline_pins.json` erhalten; `mutagen` (Tags lokaler Dateien) wird mitinstalliert.
- Geprüft: Windows (Wine, MSYS2: Named-Pipe-IPC mit zwei mpv, Absturz-Neustart, lokale Musik) und Ubuntu 24.04 mit GTK 4.14 / mpv 0.37 (alle UI-Tests).

## 1.13.0 (2026-10-28)
- **Schneller Start**: Das Fenster steht in ~70 ms statt ~300 ms. Das Aufwärmen von yt-dlp (~0,6 s Import) beginnt erst nach dem ersten Zeichnen, und die yt-dlp-Version in den Einstellungen wird aus einer Datei gelesen, statt das ganze Paket zu importieren. mpv wird schneller abgefragt.
- **Lange Listen ruckeln nicht mehr**: Die Warteschlange baut nur ein Fenster um den laufenden Titel (100 Zeilen, „↓ N weitere anzeigen“ / „↑ N bereits gespielt anzeigen“), Playlists, Alben und Podcasts erscheinen portionsweise (60, dann je 100). 300 Titel brauchen so etwa ein Drittel der Zeit und ~30 MB weniger Arbeitsspeicher.
- **Ziehen in der Warteschlange kostet nichts mehr, solange man nicht zieht**: Die Drag-Controller hängen erst beim ersten Überfahren einer Zeile an (−35 % je Zeile).
- **Aufgeräumter Code**: `ui.py` von 3240 auf ~1400 Zeilen. Einstellungen, Warteschlange, Suche, Bibliothek und Songtexte liegen in eigenen Dateien (`settings_page.py`, `queue_page.py`, `search_page.py`, `library_page.py`, `lyrics_page.py`), gemeinsame Bausteine in `rows.py` und `widgets.py`. Verhalten unverändert.
- Kleinere Caches (Stream-Adressen, Titelbilder) räumen sich jetzt selbst auf.

## 1.12.1 (2026-10-28)
- **Abgestürztes mpv startet neu**: Stirbt das Abspielprogramm (Absturz, Speichermangel, beendet), startet musicalist es von allein neu und setzt den Titel an der alten Stelle fort (war er pausiert, bleibt er pausiert). Nach 3 Abstürzen in 2 Minuten gibt es eine klare Meldung statt Endlosschleife. Vorher blieb die Oberfläche auf „Play“ stehen, ohne dass je wieder Ton kam.
- **Kein Durchrauschen ohne Internet**: Gehen 3 Titel hintereinander nicht, pausiert musicalist mit einer Meldung, statt die ganze Warteschlange mit Fehlern abzuarbeiten.
- **Warteschlange nach Neustart**: Bei mehr als 300 Titeln zeigte der gespeicherte Index auf einen falschen Titel. Gespeichert wird jetzt ein Fenster um den aktuellen Titel.
- **Play-Symbol beim Start**: Das leere mpv meldete „nicht pausiert“, daher stand nach dem Start fälschlich „spielt“. Behoben.
- **Offline**: Unter 1 GB freiem Platz wird nichts mehr geladen. **Hinweisleiste** passt sich in kompakten Fenstern wieder an (eine doppelte Funktion hatte die erste überschrieben).
- **Kleiner**: Fehlermeldungen unterscheiden „Anmeldung nötig“ sauberer, die Anmeldung der Suchfunktionen wird nicht mehr von mehreren Threads gleichzeitig aufgebaut, und die GTK-Warnung „gtk-interface-color-scheme“ im Log ist weg (`istheme.py`, gilt für alle -ist-Apps).

## 1.12.0 (2026-10-28)
- **Offline nach Wahl**: Im Rechtsklick-Menü „󰇚 offline speichern“ für einen Titel, auf Playlist-, Album- und Podcast-Seiten „󰇚 offline speichern (N)“ für die ganze Liste (bis 300 Titel). Gemerkte Titel bleiben, bis du sie wieder freigibst, zählen aber zum MB-Limit. In den Einstellungen stehen sie in eigener Liste mit „✕“.
- **Rückblick** (Bibliothek → „󰄨 rückblick“): wie viel du in 7 Tagen, 30 Tagen, einem Jahr oder insgesamt gehört hast, meistgehörte Titel und Künstler mit Balken (Klick spielt ab), Tageszeit und Wochentag als Verlaufsgrafik. Das Protokoll liegt nur auf deinem Rechner und lässt sich mit „protokoll löschen“ leeren; beim ersten Start wird es aus dem Hörverlauf vorbelegt.
- **Suche „meine“**: durchsucht ohne Netz deine Playlists, alles, was du gehört oder gemerkt hast (auch lange her), und die lokalen Dateien.
- Offline-Abgleich merkt sich jetzt, wenn er gerade lädt, dass sich etwas geändert hat, und läuft danach noch einmal.

## 1.11.0 (2026-10-28)
- **Eigene Playlists verwalten**: In einer eigenen Playlist gibt es „✎ umbenennen“, „󰆴 löschen“ (mit Rückfrage) und bei jedem Titel „✕“ zum Entfernen. In der Sammlung legt „󰐒 neue playlist“ eine leere Playlist an.
- **Künstler abonnieren**: Auf der Künstlerseite steht „abonnieren“ / „abonniert“. Die Sammlung hat neu „abonnierte künstler“ und „neu von deinen künstlern“ (die neuesten Alben und Singles deiner Abos, neuestes Jahr zuerst).
- **Podcasts**: Suchfilter „podcasts“, Folgen einer Sendung öffnen und abspielen, „podcasts“ in der Sammlung zeigt deine gespeicherten Sendungen.
- **Lokale Musik**: mp3, flac, ogg, opus, m4a, wav und mehr aus `~/Music` (Ordner in den Einstellungen wählbar). Eigener Abschnitt in der Bibliothek mit Filter, Suchfilter „lokal“, Tags (sonst „Künstler - Titel“ aus dem Dateinamen), Songtexte werden trotzdem gesucht. Lokale Titel haben kein Radio, keine Likes und keinen YouTube-Verlauf. „Zufällig“ mischt die ganze Sammlung (300 Titel pro Mal in der Warteschlange).
- **Teilen**: „󰆏 link“ bei Playlists, Alben, Künstlern und Podcasts kopiert den YouTube-Music-Link.
- Fix: Titel-IDs mit Sonderzeichen ergaben einen ungültigen MPRIS-Pfad (Waybar/playerctl bekamen kein Update).

## 1.10.0 (2026-10-28)
- **Sleep-Timer** (Knopf 󰒲 neben „mischen“, Taste `s`): nach 15 / 30 / 45 / 60 / 90 Minuten oder „nach diesem Titel“ pausieren. Die letzten 10 Sekunden werden leiser, danach ist die Lautstärke wieder normal.
- **Warteschlange per Maus umsortieren**: Zeile ziehen und auf eine andere fallen lassen, eine Linie zeigt die Zielstelle.
- **yt-dlp bleibt aktuell**: Prüfung beim Start (höchstens wöchentlich) und sofort, wenn ein Titel wegen einer YouTube-Änderung nicht mehr geht. Neues Feld „wiedergabe-motor“ in den Einstellungen mit Version und „jetzt aktualisieren“.
- **Anmeldung abgelaufen**: musicalist sieht erst im Browserprofil nach, ob du dort noch angemeldet bist, und meldet sich sonst klar mit Hinweis und Knopf „neu einlesen“ (Kopfleiste zeigt „󰀄 !“).
- **Verständliche Fehlermeldungen**: statt Rohtext steht dort z. B. „keine verbindung zum internet“, „youtube verlangt anmeldung“ oder „titel nicht verfügbar“.
- **Offline-Limit in MB** (500 MB bis 10 GB oder unbegrenzt, Standard 2 GB): die meistgehörten Titel werden von oben aufgefüllt, bis der Platz voll ist.
- Fix: Titel ohne Cover oder Album brachen das Medien-Update (MPRIS) ab.

## 1.9.0 (2026-10-27)
- **Wechsel-Animation**: Der Wechsel zwischen Hell und Dunkel (und zwischen Designs) läuft als Scanbalken über den ganzen Bildschirm. Alle Fenster, die Leiste und das Terminal wechseln darunter im selben Moment, hinter dem Balken steht das neue Design. An/aus und Dauer (Standard 1,5 s) stehen in der Designauswahl der Einstellungen.

## 1.8.0 (2026-10-26)
- **Design wählbar**: In den Einstellungen gibt es die Designauswahl wie in notist (Automatisch + 9 Designs). Die Wahl gilt für alle -ist-Apps zugleich und wirkt sofort. Bei „Automatisch“ (Desktop-Farben) kannst du zwischen **Dunkel** und **Hell** umschalten.

## 1.7.11 (2026-10-25)
- **Windows: nie mehr mehrere Instanzen.** Der Startport wird jetzt belegt, bevor das Fenster aufgebaut wird; jeder weitere
  Start übergibt nur „show“ an die laufende Instanz und endet (vorher starteten schnelle Mehrfachstarts je eine eigene).
- **„Wiedergabe fehlgeschlagen (loading failed)“**: bis zu dreimal automatisch erneut – erst mit Anmeldung, dann als
  AAC (m4a) statt Opus. mpv schreibt unter Windows zusätzlich `%TEMP%\rice-mpv.log` (Ursache der Ablehnung).

## 1.7.10 (2026-10-25)
- **Anmeldung klappt jetzt auch ohne bereits geöffneten Browser**: Findet „anmelden“ keine gültige Anmeldung, öffnet sich die
  Google-Anmeldeseite für YouTube Music; musicalist wartet bis zu 4 Minuten, übernimmt die Anmeldung und nennt in der
  Statuszeile, worauf es wartet bzw. woran es scheitert. Fehlendes `ytmusicapi`/`yt-dlp` wird selbst nachinstalliert.
- **Sehr viele Browser-Cookies** (Firefox unter Windows: ~90) ließen Google mit „413 Request Entity Too Large“ antworten
  („Expecting value“, leere Lyrics). Es werden nur noch die nötigen Cookies übernommen; Verbindungsabbrüche werden wiederholt.
- **„Wiedergabe fehlgeschlagen (loading failed)“**: mpv versucht den Titel einmal automatisch mit der anderen Adressart
  (mit/ohne Anmeldung); der Grund steht im Log.
- **Windows**: Beenden räumt auf (mpv und Prozess enden sicher); ein zweiter Start zeigt das laufende Fenster. Fehler
  landen in `%TEMP%\rice-music.log`.

## 1.7.1 (2026-10-25)
- **Künstler anklickbar in „als nächstes“** (und in der Warteschlange, den Albumzeilen und dem besten Treffer): Der Klick
  auf den Künstlernamen startete bisher nur den Titel, weil der Name als Knopf im Zeilen-Knopf steckte und nie einen
  Klick bekam. Titel, Künstler und Dauer sind jetzt getrennte Flächen; die Zeile leuchtet weiterhin als Ganzes auf.

## 1.7.0 (2026-10-25)
- **Alben in der Suche**: Unter „bester treffer“ stehen bei der Titelsuche jetzt bis zu fünf passende Alben, deutlich
  mit „ALBUM“ gekennzeichnet (Künstler, Typ, Jahr); Klick öffnet das Album.
- **Künstler überall klickbar**: Klick auf einen Künstlernamen öffnet die Künstlerseite – jetzt auch im „besten
  Treffer“, in Album-Ergebnissen und im Rechtsklick-Menü jedes Titels (auch ohne gespeicherte Künstler-ID).
- **Playlist: „a“, dann Enter**: Die zuletzt benutzte Playlist ist in der Auswahl vorausgewählt (bleibt auch nach
  einem Neustart gemerkt).
- **„Bereits in Playlist“**: Vor dem Hinzufügen wird die Playlist abgeglichen; Doppelte werden nicht noch einmal
  eingefügt, die Meldung nennt sie („3 titel bereits in …“).
- **Windows (Kernfunktionen)**: Player, Suche, Bibliothek, Warteschlange, Lyrics und Verlauf laufen jetzt auch unter
  Windows (install-windows.bat). Ohne Hover-Vorschau, Spektrum und Medientasten.

## 1.6.1 (2026-10-25)
- **Update-Knopf**: Neben der Versionsnummer steht „󰑐“ – Klick sucht sofort nach einem Update. Gibt es eine neuere
  Version, wird daraus „󰚰 update“; ein Klick lädt und installiert sie (Linux und Windows), danach heißt er „󰑓 neu starten“.
- **Rückmeldung bei Umschalt-Knöpfen**: „An“ (z. B. „Ton behalten“) ist jetzt auch unter dem Mauszeiger zu sehen,
  Drücken färbt sofort – man muss die Maus nicht mehr wegbewegen, um zu sehen, ob der Klick angekommen ist.
- **2 Finger auch vorwärts**: Nach einem Zurück-Wischen bringt das Wischen in die andere Richtung zur verlassenen
  Seite zurück.
- **Windows: echte Titelleiste** – das Fenster lässt sich verschieben, in der Größe ändern, minimieren und
  maximieren.

## 1.6.0 (2026-10-22)
- **Meistgehörte offline**: musicalist zählt, wie oft du einen Titel hörst, und speichert die meistgehörten
  (Standard: top 25, einstellbar 10/25/50/100) als Datei. Die spielen sofort und auch ohne Internet; in Listen
  zeigt „󰇚“ sie an. Was du länger nicht mehr hörst, rutscht von allein raus und wird wieder gelöscht (Abgleich
  beim Start, alle 6 h und sobald ein Titel neu in die Spitze kommt). Einstellungen (⚙) → „offline · meistgehört“
  mit Liste und „jetzt abgleichen“. Die Zählung startet mit deinem bisherigen Hörverlauf.
- **Fortschrittsbalken**: mit zwei Fingern spult jetzt nur noch Wischen nach links/rechts. Senkrechtes Scrollen
  über dem Balken ändert die Stelle im Lied nicht mehr (gilt im Player, in der Vorschau-Karte und bei visuals).

## 1.5.0 (2026-10-22)
- **Künstlerseite**: Ein Klick auf den Künstlernamen in einer Liste (oder unter dem Titel in „jetzt“) öffnet seine
  Seite mit Top-Titeln, Alben, Singles und ähnlichen Künstlern, dazu „radio“ und „alle titel“. Der Rest der Zeile
  spielt wie bisher den Titel.
- **YouTube-Statistik**: musicalist meldet Wiedergaben jetzt wie die Website an YouTube – nach 10 s landet ein Titel
  im YouTube-Verlauf, die gehörte Zeit wird mitgeschickt. So zählen deine Stunden für „diesen Monat gehört“,
  Rückblick und Empfehlungen. Abschaltbar unter Einstellungen; nur mit Anmeldung.
- **Anzeige auf dem Hintergrund**: Die Karte aus der Vorschau kann dauerhaft auf dem Hintergrundbild liegen (unter
  den Fenstern), Position wählbar – Einstellungen → „anzeige immer auf dem hintergrundbild“.
- **Alt+1 … Alt+6** wechselt die Tabs überall, auch während du im Suchfeld tippst.
- Die Vorschau-Karte war manchmal höher als ihr Inhalt (leerer Rest unten) – behoben.

## 1.4.0 (2026-10-21)
- **Rechtsklick auf jeden Titel** (jetzt, warteschlange, suche, bibliothek, hörverlauf): abspielen, als nächstes, anhängen, radio, **zu playlist hinzufügen**, gefällt mir, künstler/album öffnen, link kopieren – in der Warteschlange auch verschieben und entfernen.
- **Zu Playlist hinzufügen** geht jetzt überall: Knopf **󰐒 playlist** beim laufenden Titel, Taste `a`, 󰐒 in jeder Suchzeile, „󰐒 als playlist“ für die ganze Warteschlange. Die zuletzt benutzte Playlist steht oben, neue Playlists lassen sich direkt anlegen.
- **Suche schneller**: Ergebnisse kommen schon beim Tippen (eine Anfrage statt zwei, ~0,4 s statt ~1,6 s) und bleiben 10 Minuten gemerkt. Darunter erscheinen **Vorschläge – der erste groß**, `Tab` übernimmt ihn. Oben steht der **beste Treffer** als großer Kasten.
- **Schneller abspielen**: Liegt die Maus kurz auf einem Titel, wird er schon vorbereitet – der Klick spielt dann sofort.
- **Lyrics passen jetzt zum Gesang**: Songtexte kommen zuerst von LRCLIB mit Zeitstempeln, die zur Länge genau dieses Titels passen (YouTubes Zeitstempel lagen teils mehrere Sekunden daneben). Texte ohne Zeitstempel werden nicht mehr „geraten“ markiert. Feinjustieren mit `[` und `]`.
- **Lyrics laden vorab**: beim Titelwechsel (auch für den nächsten Titel), nicht erst beim Klick auf ⁴ lyrics.
- **Kein Rauschen mehr in Kopfhörern**: Das Spektrum hielt den Audio-Ausgang auch bei Pause wach – es läuft jetzt nur noch, solange Musik spielt.
- **Visuals „linien“ und „matrix“ laufen flüssig**: linien wandern stufenlos statt in Sprüngen, matrix zeichnet rund 10× schneller.
- **Hörverlauf abschaltbar** (einstellungen → hörverlauf führen) und dort auch löschbar.
- **Tastenhinweise auch im halben Fenster**, `?` zeigt die komplette Liste aller Tasten.
- **Steuern, auch wenn musicalist zu ist**: `Super+Alt+N` / `Super+Alt+P` = weiter/zurück, `Super+Alt+Leertaste` = play/pause. In der Hover-Vorschau gehen jetzt auch `n` / `p`.

## 1.3.0 (2026-10-20)
- **Neue Seite ⁵ visuals**: große Live-Visualisierung zur Musik, im Look der Suite – *orbit* (Cover als Punktraster mit Spektrum-Strahlen), *säulen*, *linien* und *matrix*. `v` wechselt den Modus, `f` = Vollbild (Esc zurück).
- **Hörverlauf-Leiste**: Maus an den linken Fensterrand → einzeilige Zeitachse der zuletzt gehörten Titel, nach Tagen sortiert. Ein Titel landet dort nach 5 s Wiedergabe. Klick spielt, + / » hängt an. Mit 󰐃 anheften, `h` öffnet und schließt sie.
- **Kopfleiste neu sortiert** (wie notist): Der aktive Tab zeigt seinen Namen, rechts sitzen ein Chip mit dem laufenden Titel, die Version und die umrandeten Knöpfe **󰀄 konto** und **󰒓 einstellungen** (`,`).
- **Tabs neu sortiert**: jetzt · warteschlange · bibliothek · lyrics · visuals · suchen.
- **Einstellungen** beginnen mit dem Konto: Status, „anmeldung neu einlesen“, abmelden.
- **Kontomenü**: anmelden/neu einlesen, lieblingssongs, playlists, hörverlauf, browser, abmelden. Dein Kontoname wird weiterhin nirgends angezeigt.
- **Zwei Finger zurück** (oder die Zurück-Taste der Maus) geht Seite für Seite zurück und endet immer auf ¹ jetzt.
- **Kein Ruckeln mehr in kleinen Kacheln**: musicalist passt jetzt auch in eine Achtel-Kachel (ab ~360 px Breite). Vorher war es mindestens ~530 px breit, Fenstermanager und App stritten um die Größe.

## 1.2.0 (2026-10-19)
- **Changelog**: oben rechts steht jetzt die Version – Klick darauf zeigt, was sich geändert hat. Nach einem
  Update ist sie hervorgehoben und die Statuszeile sagt einmal Bescheid.
- **✕ / q beendet musicalist ganz** (Musik stoppt). Wer es lieber im Hintergrund weiterspielen lässt: Tab 6
  „einstellungen“ → im Hintergrund weiterlaufen.
- GNOME: Das Fenster ließ sich nur einmal öffnen – behoben.
- Ältere GTK-Versionen (Ubuntu 24.04): Knopfreihen ragen nicht mehr aus ihren Kästen.
- Installer: installiert fehlende Systempakete auch beim Update nach (z. B. nach einem abgebrochenen ersten
  Versuch), `pactl` wird mitinstalliert, gtk4-layer-shell wird auch selbst gebaut gefunden.
- Startgröße passt auf kleine Bildschirme (z. B. 1366×768).
- Weniger Speicherverbrauch auf Dauer: entfernte Zeilen und Listen werden jetzt wirklich freigegeben.

## 1.1.0 (2026-10-18)
- **Neuer Name: musicalist** (vorher „musicminus“), Befehl `musicalist`.
- Hover-Vorschau am unteren Bildschirmrand ist jetzt eine Einstellung (Tab 6, standardmäßig aus).
- Esc schließt den Player nicht mehr aus Versehen (q oder ✕ schon).
- Robusterer Installer, README.

## 1.0.0 (2026-10-18)
- Erste Veröffentlichung: YouTube Music im TUI-Look – Suche, Warteschlange, Bibliothek, Songtexte (mitlaufend),
  Spektrum, Radio/Autoplay.
- Anmeldung über die Cookies deines Browsers, Wiedergabe über mpv, Steuerung per MPRIS (Medientasten, playerctl).
- Hover-Vorschau-Karte unten mit Cover, Fortschritt und anderen gerade spielenden Quellen.
