#!/bin/sh
# Startet Scheduler-Loop (Hintergrund) und Webserver (Vordergrund) im selben
# Container und leitet SIGTERM/SIGINT sauber an beide weiter.
set -eu

CONFIG_PATH="${OERR_PVR_CONFIG:-/app/config.yaml}"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "FEHLER: $CONFIG_PATH nicht gefunden." >&2
  echo "config.example.yaml nach config.yaml kopieren, ausfuellen und" >&2
  echo "als Volume einbinden (siehe README.md / docker-compose.yml)." >&2
  exit 1
fi

python -m oerr_pvr.main &
SCHEDULER_PID=$!
echo "Scheduler-Loop gestartet (PID $SCHEDULER_PID)"

term_handler() {
  echo "Signal empfangen, fahre Scheduler und Webserver herunter ..."
  kill -TERM "$SCHEDULER_PID" 2>/dev/null || true
  kill -TERM "$GUNICORN_PID" 2>/dev/null || true
  wait "$SCHEDULER_PID" 2>/dev/null || true
  wait "$GUNICORN_PID" 2>/dev/null || true
  exit 0
}
trap term_handler TERM INT

# --workers 1: bewusst, weil der Scheduler-Loop (nicht der Webserver) die
# einzige Instanz sein muss, die Aufnahmen tatsaechlich startet - fuer den
# Webserver selbst waeren dank der Dateisperre in state.py auch mehrere
# Worker unproblematisch, sind aber fuer den Hausgebrauch unnoetig.
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 4 --timeout 120 \
  "oerr_pvr.webapp:create_app()" &
GUNICORN_PID=$!
echo "Webserver gestartet (PID $GUNICORN_PID), erreichbar auf Port 8080"

wait "$SCHEDULER_PID" "$GUNICORN_PID"
