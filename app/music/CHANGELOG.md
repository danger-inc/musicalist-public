# musicalist – Änderungen

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
