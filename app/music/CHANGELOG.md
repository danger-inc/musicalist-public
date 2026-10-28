# musicalist – Änderungen

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
