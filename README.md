# videoBuddy

Persönlicher Videorecorder für die Live-TV-Streams der deutschen
öffentlich-rechtlichen Sender, mit Weboberfläche zur Sendungsauswahl. Zeichnet
per `ffmpeg` auf, prüft nach ein paar Tagen, ob der Film inzwischen regulär in
der Mediathek verfügbar ist, und lädt ihn nur dann zu Dropbox hoch, wenn das
**nicht** der Fall ist.

Der komplette Code (Scheduler-Loop, Weboberfläche, alle Module aus dem
Architekturdiagramm) ist implementiert und getestet, siehe „Was schon
getestet ist" unten. Zwei Stellen brauchen vor dem produktiven Einsatz noch
deine Handarbeit — siehe „Offene Punkte" unten.

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
        lokal löschen   dropbox_upload.py → Dropbox, dann lokal löschen
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

`config.yaml` und `data/` liegen als Volumes außerhalb des Images (siehe
`docker-compose.yml`) — ein `docker compose up -d --build` nach einem
`git pull` verliert weder Zugangsdaten noch den Aufnahmeplan.

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
   Aufnahmen, geplante Aufnahmen lassen sich stornieren.

## Offene Punkte, bevor das produktiv laufen sollte

1. **EPG-Quelle festlegen und `channel_map` bauen.** `epg.py` versteht das
   XMLTV-Standardformat und funktioniert grundsätzlich mit jeder passenden
   Quelle (z. B. free-epg.de, epg-plus.com, oder ein dedizierter ARD-Scraper
   wie https://projects.webvoss.de/2019/04/14/legal-epg-scraper-for-ard-tv-stations-to-use-with-tvheadend-external-xmltv-grabber/).
   Ich konnte in dieser Sitzung keine konkrete, aktuell funktionierende
   XMLTV-URL verifizieren — das musst du einmal ausprobieren und die
   `channel`-IDs aus dem Feed in `config.yaml` unter `channel_map` den
   Sendernamen aus `streams.py` zuordnen (die IDs unterscheiden sich von
   Quelle zu Quelle, z. B. `daserste.de` vs. `ard.de`).
2. **`film_keywords` nachschärfen.** Über „Einstellungen" in der
   Weboberfläche jederzeit ohne Neustart änderbar — nach den ersten echten
   EPG-Daten einmal durchsehen, welche Genre-Tags die Sender tatsächlich
   benutzen.
3. **Dockerfile/entrypoint.sh sind nicht in einer echten Docker-Umgebung
   gebaut/getestet worden** (in dieser Sitzung stand kein Docker-Daemon zur
   Verfügung). Die Python-Logik dahinter (State-Store, Scheduler, Webapp-
   Routen) ist getestet, aber `docker compose up --build` einmal selbst
   durchlaufen lassen und die Logs prüfen, bevor du dich darauf verlässt.
4. **`recorder.py` (ffmpeg) und `dropbox_upload.py` nicht live getestet.**
   Beides braucht einen echten HLS-Stream bzw. einen echten Dropbox-Account
   mit gültigem Refresh-Token — nicht Teil dieser Sitzung. Vor dem
   produktiven Einsatz einmal eine kurze Testaufnahme über die
   Weboberfläche anstoßen und den kompletten Ablauf bis zum Dropbox-Upload
   (oder Verwerfen, falls in der Mediathek gefunden) beobachten
   (`journalctl -u videobuddy -f` bzw. `docker compose logs -f`).

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
- **`webapp.py`**: alle Routen zusätzlich zu den Unit-Tests (Flask-
  Testclient mit gemockten EPG-Kandidaten) manuell end-to-end gegen den
  laufenden `flask run`-Dev-Server durchgespielt: Aufnahme über
  „Sendungen wählen" anlegen, im Dashboard sehen, stornieren, Einstellungen
  speichern und persistiert in `data/settings.json` wiederfinden.
- **Nicht getestet** (siehe „Offene Punkte"): `recorder.py` gegen einen
  echten Stream, `dropbox_upload.py` gegen einen echten Account, und der
  komplette Docker-Build.

Insgesamt 31 automatisierte Tests, ausführbar mit:

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
