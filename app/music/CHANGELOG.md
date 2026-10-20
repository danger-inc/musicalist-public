# musicalist – Änderungen

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
