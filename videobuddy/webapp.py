"""Weboberfläche (siehe README "Benutzung"): zeigt EPG-Kandidaten, nimmt die
Auswahl entgegen, zeigt den Status laufender/erledigter Jobs, verwaltet
Einstellungen. Bewusst ohne Login (siehe README "Sicherheitshinweis")."""

from __future__ import annotations

import os
import re
import secrets
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

from . import epg, recorder, scheduler
from .candidates import build_candidates
from .config import Config, load_config
from .settings import load_settings, save_settings

BERLIN = ZoneInfo("Europe/Berlin")
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

STATUS_LABELS = {
    "scheduled": "geplant",
    "recording": "läuft",
    "recorded": "aufgenommen",
    "ready": "bereit (nicht hochgeladen)",
    "uploading": "wird hochgeladen",
    "uploaded": "hochgeladen",
    "discarded": "verworfen (in Mediathek gefunden)",
    "canceled": "storniert",
    "deleted": "gelöscht",
    "failed": "fehlgeschlagen",
}

# Status-Badges zeigen nur noch ein Icon (Platzersparnis in der Tabelle) -
# die Bedeutung steckt im title/aria-label-Attribut (Mouseover) bzw. in der
# Legende, die auf schmalen Bildschirmen eingeblendet wird (siehe
# dashboard.html). Icons selbst liegen als <symbol> im SVG-Sprite in
# base.html.
STATUS_ICONS = {
    "scheduled": "icon-clock",
    "recording": "icon-dot",
    "recorded": "icon-check",
    "ready": "icon-alert",
    "uploading": "icon-cloud-upload",
    "uploaded": "icon-cloud-check",
    "discarded": "icon-trash",
    "canceled": "icon-cancel",
    "deleted": "icon-trash",
    "failed": "icon-warning",
}

# In diesen Status-Werten bietet das Dashboard zusaetzlich "Hochladen" an -
# der Dropbox-Upload ist bewusst kein Automatismus, siehe README. "recorded"
# ist bewusst dabei: die Datei ist direkt nach der Aufnahme schon vollstaendig
# und hochladbar, der Mediathek-Check (der "recorded" -> "ready" schaltet)
# ist nur ein informativer Marker und keine Voraussetzung fuers Hochladen.
MANUAL_ACTION_STATUSES = ("recorded", "ready", "failed")

# In diesen Status-Werten liegt garantiert noch eine vollstaendige Datei auf
# der Platte - "Direkt" (Download aufs aufrufende Geraet) und "Loeschen"
# bleiben deshalb hier verfuegbar, unabhaengig davon, ob schon zu Dropbox
# hochgeladen wurde. main.py loescht die Datei nach einem erfolgreichen
# Upload bewusst nicht mehr automatisch, siehe README "Speicherbedarf im
# Blick behalten".
FILE_ACTION_STATUSES = ("recorded", "ready", "failed", "uploaded")

# Standardmäßig ausgeblendet (Checkbox "Stornierte/Gelöschte einblenden"),
# es sei denn im Status-Filter wird gezielt genau danach gefiltert.
HIDDEN_BY_DEFAULT_STATUSES = ("canceled", "deleted")

DASHBOARD_SORT_OPTIONS = [
    ("sendezeit", "Sendezeit (nächste Aufnahme zuerst)"),
    ("sender", "Sender"),
    ("titel", "Titel"),
]


def _local_time(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")


def _time_only(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(BERLIN).strftime("%H:%M")


def _date_only(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(BERLIN).strftime("%d.%m.%Y")


def _status_icon(status: str) -> str:
    return STATUS_ICONS.get(status, "icon-alert")


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _date_label(d) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.strftime('%d.%m.%Y')}"


def _channel_name(stream_title: str) -> str:
    """Zeigt Sendernamen ohne den "Livestream"-Zusatz aus streams.py an.
    Nur fürs Anzeigen - config.channel_map selbst bleibt unverändert, weil
    main.py den exakten Wert für die Stream-URL-Zuordnung braucht."""
    return re.sub(r"\s+", " ", stream_title.replace("Livestream", "")).strip()


def _dashboard_sort_key(config: Config, sort_key: str):
    if sort_key == "sender":
        return lambda j: _channel_name(config.channel_map.get(j["channel"], j["channel"])).lower()
    if sort_key == "titel":
        return lambda j: j["title"].lower()
    return lambda j: j.get("record_start", "")


def _duration_label(seconds) -> str:
    if not seconds or seconds <= 0:
        return ""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} Sek"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} Min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} Std {minutes} Min"


def _known_upload_speed_bps(all_jobs: list[dict]) -> float | None:
    """Letzte tatsächlich gemessene Upload-Geschwindigkeit über alle Jobs
    hinweg (main.py schreibt sie nach jedem erfolgreichen Dropbox-Upload
    weg) - genauer als ein synthetischer Speedtest, weil es der echte Pfad
    zu Dropbox von genau diesem Server aus ist. None, solange noch nie ein
    Upload durchgelaufen ist."""
    measured = [
        j
        for j in all_jobs
        if j.get("upload_speed_bps") and j.get("upload_speed_measured_at")
    ]
    if not measured:
        return None
    return max(measured, key=lambda j: j["upload_speed_measured_at"])["upload_speed_bps"]


def _dashboard_job_view(job: dict, known_upload_speed_bps: float | None) -> dict:
    """Reichert einen Job um rein für die Anzeige berechnete Felder an
    (Dateigröße, geschätzte Uploadzeit, Restzeit bei laufendem Upload) -
    wird nicht zurück nach jobs.json geschrieben."""
    view = dict(job)

    file_size = None
    if job.get("file_path") and os.path.exists(job["file_path"]):
        try:
            file_size = os.path.getsize(job["file_path"])
        except OSError:
            file_size = None
    view["file_size"] = file_size

    view["estimated_upload_seconds"] = None
    if (
        file_size
        and known_upload_speed_bps
        and job["status"] in ("recorded", "ready", "failed")
    ):
        view["estimated_upload_seconds"] = file_size / known_upload_speed_bps

    view["upload_eta_seconds"] = None
    if (
        job["status"] == "uploading"
        and job.get("upload_progress")
        and job.get("upload_total")
        and job.get("upload_started_at")
    ):
        started_at = datetime.fromisoformat(job["upload_started_at"])
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        if elapsed > 0:
            live_bps = job["upload_progress"] / elapsed
            remaining_bytes = job["upload_total"] - job["upload_progress"]
            if live_bps > 0:
                view["upload_eta_seconds"] = remaining_bytes / live_bps

    return view


def _build_table_rows(candidates, show_day_separators: bool) -> list[dict]:
    """Baut die Zeilenliste für die Sendungen-Tabelle. Bei "Alle Tage" wird
    vor der ersten Sendung eines neuen Kalendertags ein Trenner eingefügt -
    candidates ist bereits nach Startzeit sortiert (siehe candidates.py)."""
    rows: list[dict] = []
    last_date = None
    for c in candidates:
        local_date = c.start.astimezone(BERLIN).date()
        if show_day_separators and local_date != last_date:
            rows.append({"type": "separator", "label": _date_label(local_date)})
            last_date = local_date
        rows.append({"type": "candidate", "candidate": c})
    return rows


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.jinja_env.filters["local_time"] = _local_time
    app.jinja_env.filters["time_only"] = _time_only
    app.jinja_env.filters["date_only"] = _date_only
    app.jinja_env.filters["status_label"] = _status_label
    app.jinja_env.filters["status_icon"] = _status_icon
    app.jinja_env.filters["channel_name"] = _channel_name
    app.jinja_env.filters["duration"] = _duration_label

    # fetched_at startet bei -inf statt 0.0: time.monotonic() misst Zeit seit
    # irgendeinem beliebigen Bezugspunkt (unter Linux typischerweise seit
    # Systemstart, NICHT seit der Unix-Epoche) - mit 0.0 als Startwert würde
    # der allererste Abruf faelschlich als "noch frisch" gelten, solange die
    # System-Uptime kleiner als epg_refresh_minutes ist (z. B. kurz nach
    # einem Neustart), und "Sendungen wählen" bliebe dauerhaft leer.
    epg_cache: dict[str, object] = {"entries": [], "fetched_at": float("-inf")}

    def get_epg_entries():
        now = time.monotonic()
        ttl_seconds = config.epg_refresh_minutes * 60
        if now - epg_cache["fetched_at"] > ttl_seconds:
            try:
                epg_cache["entries"] = epg.fetch_epg(config.epg_urls)
                epg_cache["fetched_at"] = now
            except Exception:
                app.logger.exception(
                    "EPG-Abruf fehlgeschlagen, zeige zuletzt geladene Daten"
                )
        return epg_cache["entries"]

    def _dashboard_redirect():
        return redirect(
            url_for(
                "dashboard",
                status=request.values.get("status") or None,
                sortierung=request.values.get("sortierung") or None,
                alle_status=request.values.get("alle_status") or None,
            )
        )

    @app.route("/")
    def dashboard():
        selected_status = request.args.get("status") or ""
        show_hidden = request.args.get("alle_status") == "1"
        sort_key = request.args.get("sortierung") or "sendezeit"
        if sort_key not in dict(DASHBOARD_SORT_OPTIONS):
            sort_key = "sendezeit"

        all_jobs = scheduler.list_jobs(config)
        jobs = all_jobs
        if selected_status:
            jobs = [j for j in jobs if j["status"] == selected_status]
        elif not show_hidden:
            jobs = [j for j in jobs if j["status"] not in HIDDEN_BY_DEFAULT_STATUSES]
        jobs.sort(key=_dashboard_sort_key(config, sort_key))
        known_upload_speed_bps = _known_upload_speed_bps(all_jobs)
        jobs = [_dashboard_job_view(j, known_upload_speed_bps) for j in jobs]

        return render_template(
            "dashboard.html",
            has_any_jobs=bool(all_jobs),
            show_hidden=show_hidden,
            jobs=jobs,
            channel_map=config.channel_map,
            status_options=STATUS_LABELS,
            selected_status=selected_status,
            sort_options=DASHBOARD_SORT_OPTIONS,
            sort_key=sort_key,
            has_active_upload=any(j["status"] == "uploading" for j in all_jobs),
            manual_action_statuses=MANUAL_ACTION_STATUSES,
            file_action_statuses=FILE_ACTION_STATUSES,
        )

    @app.route("/jobs/<job_id>/cancel", methods=["POST"])
    def cancel(job_id):
        if scheduler.cancel_job(config, job_id):
            flash("Aufnahme storniert.", "success")
        else:
            flash("Konnte nicht storniert werden (evtl. läuft sie schon).", "error")
        return _dashboard_redirect()

    @app.route("/jobs/<job_id>/upload", methods=["POST"])
    def upload(job_id):
        job = scheduler.get_job(config, job_id)
        if job is None or job["status"] not in MANUAL_ACTION_STATUSES:
            flash("Konnte Upload nicht anstoßen.", "error")
            return _dashboard_redirect()
        # Setzt nur den Status - der eigentliche Upload läuft im
        # Scheduler-Loop (main.py), damit der Webrequest nicht für die
        # ganze Dauer des Uploads blockiert.
        scheduler.update_job(
            config,
            job_id,
            status="uploading",
            error=None,
            upload_progress=None,
            upload_total=None,
            upload_started_at=datetime.now(timezone.utc).isoformat(),
        )
        flash(f'"{job["title"]}" wird im Hintergrund zu Dropbox hochgeladen.', "success")
        return _dashboard_redirect()

    @app.route("/jobs/<job_id>/direkt")
    def direkt(job_id):
        job = scheduler.get_job(config, job_id)
        # Absolut machen, bevor os.path.exists/send_file ihn sehen: ein
        # relativer file_path (config.recording_dir z.B. "./recordings")
        # ist zwar korrekt relativ zum Arbeitsverzeichnis (/app) - aber
        # Flasks send_file() loest relative Pfade stattdessen gegen
        # current_app.root_path auf (das videobuddy-Paketverzeichnis,
        # /app/videobuddy), nicht gegen das Arbeitsverzeichnis. Ohne
        # os.path.abspath() sucht send_file() also am falschen Ort
        # (/app/videobuddy/recordings/... statt /app/recordings/...) und
        # wirft FileNotFoundError, obwohl die Datei existiert.
        file_path = os.path.abspath(job["file_path"]) if job and job.get("file_path") else None
        if (
            job is None
            or job["status"] not in FILE_ACTION_STATUSES
            or not file_path
            or not os.path.exists(file_path)
        ):
            flash("Datei nicht (mehr) verfügbar.", "error")
            return _dashboard_redirect()
        return send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path),
        )

    @app.route("/jobs/<job_id>/delete", methods=["POST"])
    def delete_recording(job_id):
        job = scheduler.get_job(config, job_id)
        if job is None or job["status"] not in FILE_ACTION_STATUSES:
            flash("Konnte nicht gelöscht werden.", "error")
            return _dashboard_redirect()
        recorder.delete_files(job["file_path"])
        scheduler.update_job(config, job_id, status="deleted")
        flash(f'"{job["title"]}" gelöscht.', "success")
        return _dashboard_redirect()

    @app.route("/sendungen")
    def sendungen():
        settings_data = load_settings(config)
        only_suggestions = request.args.get("nur_vorschlaege") == "1"
        selected_date = request.args.get("datum") or ""
        selected_channel = request.args.get("sender") or ""

        entries = get_epg_entries()
        candidates = build_candidates(entries, settings_data)
        if only_suggestions:
            candidates = [c for c in candidates if c.is_suggestion]

        available_dates = sorted(
            {c.start.astimezone(BERLIN).date() for c in candidates}
        )
        date_options = [
            {"value": d.isoformat(), "label": _date_label(d)} for d in available_dates
        ]

        if selected_date:
            candidates = [
                c
                for c in candidates
                if c.start.astimezone(BERLIN).date().isoformat() == selected_date
            ]
        if selected_channel:
            candidates = [c for c in candidates if c.channel == selected_channel]

        channel_options = {
            channel_id: config.channel_map[channel_id]
            for channel_id in settings_data["watched_channels"]
            if channel_id in config.channel_map
        }

        table_rows = _build_table_rows(candidates, show_day_separators=not selected_date)

        return render_template(
            "sendungen.html",
            candidates=candidates,
            table_rows=table_rows,
            only_suggestions=only_suggestions,
            date_options=date_options,
            selected_date=selected_date,
            channel_options=channel_options,
            selected_channel=selected_channel,
        )

    @app.route("/sendungen/aufnehmen", methods=["POST"])
    def aufnehmen():
        settings_data = load_settings(config)
        title = request.form["title"]
        scheduler.create_job(
            config,
            channel=request.form["channel"],
            title=title,
            epg_start=datetime.fromisoformat(request.form["epg_start"]),
            epg_end=datetime.fromisoformat(request.form["epg_end"]),
            buffer_before_minutes=settings_data["buffer_before_minutes"],
            buffer_after_minutes=settings_data["buffer_after_minutes"],
        )
        flash(f'"{title}" eingeplant.', "success")
        return redirect(
            url_for(
                "sendungen",
                nur_vorschlaege=request.form.get("nur_vorschlaege") or None,
                datum=request.form.get("datum") or None,
                sender=request.form.get("sender_filter") or None,
            )
        )

    @app.route("/sendungen/alle-uebernehmen", methods=["POST"])
    def alle_uebernehmen():
        settings_data = load_settings(config)
        entries = get_epg_entries()
        suggestions = [c for c in build_candidates(entries, settings_data) if c.is_suggestion]
        for candidate in suggestions:
            scheduler.create_job(
                config,
                channel=candidate.channel,
                title=candidate.title,
                epg_start=candidate.start,
                epg_end=candidate.stop,
                buffer_before_minutes=settings_data["buffer_before_minutes"],
                buffer_after_minutes=settings_data["buffer_after_minutes"],
            )
        flash(f"{len(suggestions)} Vorschläge eingeplant.", "success")
        return redirect(url_for("sendungen", nur_vorschlaege="1"))

    @app.route("/einstellungen", methods=["GET", "POST"])
    def einstellungen():
        if request.method == "POST":
            film_keywords = [
                line.strip()
                for line in request.form.get("film_keywords", "").splitlines()
                if line.strip()
            ]
            save_settings(
                config,
                {
                    "watched_channels": request.form.getlist("watched_channels"),
                    "film_keywords": film_keywords,
                    "min_duration_minutes": int(request.form["min_duration_minutes"]),
                    "buffer_before_minutes": int(request.form["buffer_before_minutes"]),
                    "buffer_after_minutes": int(request.form["buffer_after_minutes"]),
                },
            )
            flash("Einstellungen gespeichert.", "success")
            return redirect(url_for("einstellungen"))

        settings_data = load_settings(config)
        return render_template(
            "einstellungen.html", settings=settings_data, channel_map=config.channel_map
        )

    return app
