# videoBuddy

Persönlicher Videorecorder für die Live-TV-Streams der deutschen
öffentlich-rechtlichen Sender, mit Weboberfläche zur Sendungsauswahl. Zeichnet
per `ffmpeg` auf und prüft nach ein paar Tagen, ob der Film inzwischen regulär
in der Mediathek verfügbar ist — falls ja, wird die Aufnahme automatisch
verworfen. Falls nicht, wartet sie in der Aufnahmen-Liste auf eine manuelle
Entscheidung: **Hochladen** (zu Dropbox) oder **Löschen**. Es gibt bewusst
keinen automatischen Dropbox-Upload — viele Aufnahmen schaut man sich genau
einmal an und löscht sie danach wieder.

Der komplette Code (Scheduler-Loop, Weboberfläche, alle Module aus dem
Architekturdiagramm) ist implementiert und getestet, `config.yaml` ist mit
einer echten, funktionierenden EPG-Quelle ausgefüllt — siehe „Was schon
getestet ist" unten. Ein paar Stellen brauchen vor dem produktiven Einsatz
noch deine Handarbeit — siehe „Offene Punkte" unten.

## Architektur

```
                         EPG-Feed(s) (XMLTV)
                                │
                                ▼
                          candidates.py    (Kandidatenliste: Dauer + Genre → "Vorschlag")
                                │
                    ┌───────────┴────────────┐
                    ▼                        ▼
             Weboberfläche              (nur lesend, kein Auto-Scheduling mehr)
          "Sendungen wählen"
                    │  Klick auf "Aufnehmen"
                    ▼
           scheduler.create_job() ──────▶ data/jobs.json  ◀──── state.py (Dateisperre,
                    │                     (geteilter Zustand)      cross-prozess-sicher)
                    │                            ▲
                    │                            │ liest/aktualisiert Status
                    ▼                            │
           Scheduler-Loop (eigener Prozess) ─────┘
                    │
                    ▼
             recorder.py  (ffmpeg: HLS → Datei)
                    │
              nach X Tagen
                    ▼
            mediathek.py  (Abgleich gegen MediathekViewWeb-API)
                 │      │
           gefunden      nicht gefunden
              │               │
        lokal löschen      Status "ready" - wartet in der Aufnahmen-Liste
        (automatisch)      auf Klick "Hochladen" oder "Löschen"
                                │              │
                     dropbox_upload.py    recorder.delete_files()
                     → Dropbox, dann      (sofort, keine Bestätigung
                     lokal löschen         durch die Weboberfläche)
```

Zwei Python-Prozesse teilen sich denselben `data/`-Ordner:

- **Scheduler-Loop** (`python -m videobuddy.main`) — führt nur bereits
  ausgewählte Aufnahmen zur richtigen Zeit aus, fragt selbst kein EPG ab.
- **Webserver** (`gunicorn videobuddy.webapp:create_app()`) — zeigt EPG-Kandidaten,
  nimmt deine Auswahl entgegen, zeigt den Status laufender/erledigter Jobs,
  verwaltet Einstellungen (Sender, Suchbegriffe, Aufnahmepuffer).

`streams.py` lädt die aktuellen HLS-Stream-URLs live von der Liste, die das
MediathekView-Projekt selbst pflegt — die musst du nicht selbst warten.

### config.yaml vs. Einstellungen in der Weboberfläche

Zwei getrennte Ablagen mit Absicht:

- **`config.yaml`** — Infrastruktur/Geheimnisse (Dropbox-Zugangsdaten,
  EPG-Quelle, Pfade, verfügbare Sender/Channel-Mapping). Wird einmal beim
  Setup ausgefüllt, danach selten angefasst.
- **`data/settings.json`** — deine laufenden Vorlieben (welche der in
  config.yaml verfügbaren Sender aktuell beobachtet werden, Suchbegriffe für
  Spielfilm-Vorschläge, Mindestlänge, Aufnahmepuffer). Wird ausschließlich
  über „Einstellungen" in der Weboberfläche geändert, beim ersten Start mit
  Defaults aus config.yaml angelegt.

## Setup mit Docker (empfohlen)

```bash
git clone <dein-repo> videoBuddy && cd videoBuddy
cp config.example.yaml config.yaml
# config.yaml ausfüllen, siehe Kommentare darin und "Offene Punkte" unten
docker compose up -d --build
```

Weboberfläche danach unter `http://athene:8080` (oder wie auch immer Athene
in deinem Netz erreichbar ist). Logs: `docker compose logs -f`.

`config.yaml`, `data/` (jobs.json/settings.json) und `recordings/` liegen
als eigene Volumes außerhalb des Images (siehe `docker-compose.yml`) — ein
`docker compose up -d --build` nach einem `git pull` verliert weder
Zugangsdaten noch den Aufnahmeplan. `recordings/` ist bewusst ein eigenes
Volume, getrennt von `data/`: dort landen die (teils mehrere GB großen)
Videodateien während der Aufnahme, bevor sie — erst nach dem
Mediathek-Check, nie live während der Aufnahme — zu Dropbox hochgeladen
werden. Zeig es in `docker-compose.yml` auf eine Platte mit genug Platz,
z. B. `/mnt/storage/videobuddy-recordings:/app/recordings`.

## Bare-Metal statt Docker

Falls du keinen Docker auf Athene willst:

```bash
sudo apt install ffmpeg python3-venv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # ausfüllen

# Testlauf von Hand, in zwei Terminals:
python -m videobuddy.main                                    # Scheduler
gunicorn --bind 0.0.0.0:8080 "videobuddy.webapp:create_app()" # Weboberfläche
```

Für den Dauerbetrieb zwei systemd-Units (beide im `systemd/`-Ordner,
Platzhalter für User/Pfad darin anpassen):

```bash
sudo cp systemd/videobuddy.service systemd/videobuddy-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now videobuddy videobuddy-web
journalctl -u videobuddy -u videobuddy-web -f
```

## Benutzung

1. **Einstellungen** — welche Sender beobachtet werden sollen, Suchbegriffe
   für die automatische Spielfilm-Erkennung, Aufnahmepuffer.
2. **Sendungen wählen** — Liste der kommenden Sendungen aus dem EPG. Treffer
   auf deine Suchbegriffe sind blau als „Vorschlag" markiert, du kannst aber
   jede beliebige Sendung per Klick auf „Aufnehmen" einplanen — auch wenn sie
   nicht als Vorschlag markiert ist. Mit „Alle Vorschläge übernehmen" lassen
   sich alle aktuell erkannten Vorschläge auf einmal einplanen.
3. **Aufnahmen** (Startseite) — Status aller geplanten/laufenden/erledigten
   Aufnahmen, geplante Aufnahmen lassen sich stornieren. Fertige Aufnahmen,
   die nicht in der Mediathek gefunden wurden (Status „bereit (nicht
   hochgeladen)"), zeigen zwei Buttons: **Hochladen** (läuft im Hintergrund
   im Scheduler-Loop, blockiert die Weboberfläche nicht) und **Löschen**
   (sofort, ohne Rückfrage). Bei einem fehlgeschlagenen Upload bleiben
   beide Buttons erhalten, um es erneut zu versuchen oder aufzugeben.

## Offene Punkte, bevor das produktiv laufen sollte

1. **Dockerfile/entrypoint.sh sind nicht in einer echten Docker-Umgebung
   gebaut/getestet worden** (auf keiner der Maschinen, auf denen dieses
   Projekt bisher bearbeitet wurde, stand ein Docker-Daemon zur Verfügung —
   auch kein WSL als Ausweichmöglichkeit). Die Python-Logik dahinter
   (State-Store, Scheduler, Webapp-Routen, EPG-Parsing) ist getestet, aber
   `docker compose up --build` einmal selbst durchlaufen lassen und die
   Logs prüfen, bevor du dich darauf verlässt. Ersatzweise wurde der
   `pip install -r requirements.txt`-Schritt aus dem Dockerfile isoliert in
   einer frischen venv nachgestellt (installiert sauber) und
   `entrypoint.sh` auf Shell-Syntaxfehler geprüft (`sh -n entrypoint.sh`,
   OK).
2. **`recorder.py` (ffmpeg) und `dropbox_upload.py` nicht live getestet.**
   Beides braucht einen echten HLS-Stream bzw. einen echten Dropbox-Account
   mit gültigem Refresh-Token — nicht Teil dieser Sitzung. Vor dem
   produktiven Einsatz einmal eine kurze Testaufnahme über die
   Weboberfläche anstoßen und den kompletten Ablauf bis zum Dropbox-Upload
   (oder Verwerfen, falls in der Mediathek gefunden) beobachten
   (`journalctl -u videobuddy -f` bzw. `docker compose logs -f`).
3. **Dropbox-Zugangsdaten in `config.yaml` sind noch Platzhalter.**
   `refresh_token`/`app_key`/`app_secret` müssen aus deinem eigenen
   Dropbox-Account stammen (siehe Kommentar in `config.example.yaml`) —
   das kann niemand für dich vorausfüllen.
4. **`film_keywords` ggf. weiter nachschärfen.** Die aktuellen Defaults
   (`film`, `drama`, `komödie`, `krimi`, `thriller`) sind gegen echte
   Kategorie-Tags der `epg_urls`-Quelle unten geprüft und treffen bewusst
   eher zu viel als zu wenig — z. B. werden auch Krimi-Serienfolgen mit
   ≥70 Minuten Länge als „Vorschlag" markiert. Über „Einstellungen" in der
   Weboberfläche jederzeit ohne Neustart anpassbar.

## Was schon getestet ist (und wie)

- **`streams.py`**: live gegen die echte, aktuelle `live-streams.json` von
  MediathekView getestet (`fetch_live_streams()`, Stand 2026-08-14) — 44
  Sender gefunden, alle `channel_map`-Werte aus `config.example.yaml` lösen
  korrekt zu echten HLS-URLs auf (z. B. ARD →
  `daserste-live.ard-mcdn.de/.../master.m3u8`). Der in der Datei enthaltene
  Sonderfall (derselbe JSON-Key `"X"` mehrfach im Root-Objekt — ein naives
  `json.loads()` würde dabei fast alle Sender stillschweigend verlieren) ist
  zusätzlich per Unit-Test mit einem echten Auszug der Datei abgesichert
  (`tests/test_streams.py`).
- **`mediathek.py`**: live gegen die echte MediathekViewWeb-API getestet
  (`python -m videobuddy.mediathek "Tagesschau" "ARD"` lieferte reale,
  aktuelle Treffer). Anfrage-/Antwortformat sind damit bestätigt richtig.
- **`epg.py`**: XMLTV-Parsing, Zeitzonenumrechnung und Spielfilm-Erkennung
  gegen eine handgebaute Beispieldatei verifiziert (`tests/test_epg.py`).
  Zusätzlich live gegen die echte, aktuelle `epg_urls`-Quelle
  (`epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz`, Stand 2026-08-14)
  getestet: 26.635 Sendungen über alle Sender geladen, alle 15
  `channel_map`-Einträge aus `config.example.yaml` lösen zu echten
  EPG-Channel-IDs auf (z. B. ARD → `Das.Erste.de`, 136 Sendungen im
  geladenen Zeitraum). Diese Quelle liefert nur `.xml.gz` ohne
  `Content-Encoding`-Header — `epg.py` erkennt und entpackt das jetzt
  automatisch (Magic-Bytes-Check, `tests/test_epg.py`). `film_keywords`
  wurden anhand der echten (sehr granularen, zusammengesetzten)
  Genre-Tags dieser Quelle neu kalibriert — die alten Default-Werte
  („Spielfilm" etc.) kamen in den echten Daten kein einziges Mal vor und
  hätten nie einen Vorschlag erzeugt.
- **`state.py`**: `JsonFileStore.modify()` unter 20 parallelen Threads
  race-frei getestet (Stellvertreter für die zwei echten Prozesse
  Scheduler + Webserver), inklusive plattformübergreifendem Datei-Lock
  (`fcntl` auf Linux, `msvcrt`-Fallback für lokale Windows-Entwicklung).
- **`scheduler.py`**: `create_job` (inkl. Idempotenz bei Doppel-Klick und
  erneutem Anlegen nach Stornierung), `cancel_job` (inkl. Ablehnung für
  bereits laufende Jobs), `list_jobs`, `update_job` per Unit-Tests
  abgedeckt.
- **`candidates.py`**: Filter auf beobachtete Sender, Ausschluss
  vergangener Sendungen, Vorschlags-Erkennung über Mindestlänge + Schlagwort
  in Titel/Kategorie per Unit-Tests abgedeckt.
- **`main.py`** (die Statuswechsel-Logik, nicht ffmpeg/Dropbox selbst):
  `_process_recorded` (Mediathek-Fund → automatisch verwerfen, kein Fund →
  Status "ready" statt Auto-Upload) und `_process_uploading` (Erfolg →
  "uploaded" + Datei gelöscht, Fehler → "failed" + Datei bleibt erhalten)
  per Unit-Tests mit gemocktem `mediathek`/`dropbox_upload` abgedeckt
  (`tests/test_main.py`).
- **`webapp.py`**: alle Routen zusätzlich zu den Unit-Tests (Flask-
  Testclient mit gemockten EPG-Kandidaten) manuell end-to-end gegen den
  laufenden `flask run`-Dev-Server durchgespielt: Aufnahme über
  „Sendungen wählen" anlegen, im Dashboard sehen, stornieren, Einstellungen
  speichern und persistiert in `data/settings.json` wiederfinden. Zusätzlich
  einmal komplett mit der echten, ausgefüllten `config.yaml` (echte
  EPG-Quelle, echte `channel_map`) durchlaufen: `/sendungen` zeigte reale,
  aktuelle Sendungen mit plausiblen Spielfilm-Vorschlägen (z. B. „Der
  talentierte Mr. Ripley", „Papillon") aus allen 15 beobachteten Sendern.
- **Nicht getestet** (siehe „Offene Punkte"): `recorder.py` gegen einen
  echten Stream, `dropbox_upload.py` gegen einen echten Account, und der
  komplette Docker-Build (kein Docker-Daemon in dieser Umgebung verfügbar).

Insgesamt 41 automatisierte Tests, ausführbar mit:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Rechtliches (kurz)

Für den rein privaten Gebrauch ist das Aufnehmen von Live-TV-Sendungen nach
§ 53 UrhG als Privatkopie zulässig — die Livestreams der ÖRR sind
unverschlüsseltes HLS ohne Kopierschutz, § 95a UrhG (Umgehungsverbot) greift
also nicht. Wichtig bleibt: Aufnahmen nur privat nutzen, nicht öffentlich
teilen oder verbreiten (ein privater Dropbox-Ordner ist unproblematisch, ein
öffentlicher Freigabelink an Dritte nicht mehr).

## Sicherheitshinweis zur Weboberfläche

Die Weboberfläche hat bewusst kein Login (Hausgebrauch im eigenen Netzwerk).
Wenn Athene auch von außerhalb deines Netzwerks erreichbar ist (Port-Forwarding,
VPN mit Splitt-Tunneling o. ä.), unbedingt einen Reverse-Proxy mit Basic-Auth
oder ein VPN davorsetzen, bevor Port 8080 nach außen geht.

## Speicherbedarf im Blick behalten

Ein zweistündiger Film in ordentlicher Qualität liegt schnell bei mehreren
GB. Über „Nur Vorschläge zeigen" plus eine bewusst kleine Senderauswahl in
den Einstellungen lässt sich die Menge an Aufnahmen gut im Rahmen halten.
`recordings/` (siehe oben, eigenes Volume) sollte deshalb auf eine Platte
mit ausreichend Platz zeigen — dort liegen die Aufnahmen zwischen
Aufnahmeende und Dropbox-Upload bzw. Verwerfen.
