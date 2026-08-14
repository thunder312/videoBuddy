"""ffmpeg: HLS -> Datei (siehe README-Architekturdiagramm).

Bewusst ohne In-Memory-Prozess-Handle: der Scheduler-Loop prüft Liveness nur
über die in jobs.json gespeicherte PID (os.kill(pid, 0)). Dadurch übersteht
eine laufende Aufnahme einen Neustart des Scheduler-Prozesses - ffmpeg läuft
dank start_new_session als eigene Session weiter, auch wenn entrypoint.sh dem
Scheduler-Prozess SIGTERM schickt.

Ausgabe-Container ist .mkv statt .mp4: "-c copy" von HLS (AAC in ADTS)
funktioniert damit ohne den sonst nötigen aac_adtstoasc-Bitstream-Filter.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone


def _sanitize(text: str) -> str:
    text = re.sub(r"[^\w\-. ]", "", text, flags=re.UNICODE)
    text = text.strip().replace(" ", "_")
    return text[:80] or "aufnahme"


def build_output_path(
    recording_dir: str, channel: str, title: str, record_start: datetime
) -> str:
    os.makedirs(recording_dir, exist_ok=True)
    filename = (
        f"{_sanitize(channel)}_{record_start.strftime('%Y%m%d-%H%M')}_"
        f"{_sanitize(title)}.mkv"
    )
    return os.path.join(recording_dir, filename)


def start_recording(stream_url: str, output_path: str, record_end: datetime) -> int:
    """Startet ffmpeg mit "-t <Sekunden>" (Endzeit ist beim Start schon
    bekannt, kein manuelles Stop-Polling nötig). Gibt die PID zurück."""
    duration_seconds = max(
        1, int((record_end - datetime.now(timezone.utc)).total_seconds())
    )
    log_path = output_path + ".log"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "warning",
        "-i",
        stream_url,
        "-t",
        str(duration_seconds),
        "-c",
        "copy",
        output_path,
    ]
    with open(log_path, "wb") as log_fh:
        process = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process.pid


def is_finished(pid: int | None) -> bool:
    """Liveness-Check rein über die PID, kein Popen-Handle nötig."""
    if pid is None:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def delete_files(output_path: str | None) -> None:
    """Löscht die Aufnahme + das zugehörige ffmpeg-Log, falls vorhanden.
    Wird sowohl vom Scheduler-Loop (Mediathek-Fund) als auch von der
    Weboberfläche (manuelles Löschen) benutzt."""
    if not output_path:
        return
    if os.path.exists(output_path):
        os.remove(output_path)
    log_path = output_path + ".log"
    if os.path.exists(log_path):
        os.remove(log_path)
