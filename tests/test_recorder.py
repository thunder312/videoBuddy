import sys
from datetime import datetime, timezone

import pytest

from videobuddy import recorder


def test_build_output_path_uses_ts_extension(tmp_path):
    """.ts statt .mkv: bleibt bis zum Abbruchpunkt gueltig, falls der
    ffmpeg-Prozess mitten in der Aufnahme hart gekillt wird (z. B. durch
    einen Docker-Container-Neustart), siehe recorder.py-Docstring."""
    output_path = recorder.build_output_path(
        str(tmp_path), "Tatort", datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    )

    assert output_path.endswith(".ts")
    assert "Tatort" in output_path
    assert "20260601" in output_path


def test_build_output_path_creates_recording_dir(tmp_path):
    target_dir = tmp_path / "not-yet-created"
    recorder.build_output_path(
        str(target_dir), "Titel", datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    )
    assert target_dir.is_dir()


def test_build_output_path_sanitizes_title():
    output_path = recorder.build_output_path(
        ".", 'Titel/mit:komischen*Zeichen?', datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    )
    filename = output_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    assert "/" not in filename
    assert ":" not in filename
    assert "*" not in filename
    assert "?" not in filename


def test_build_output_path_appends_time_on_collision(tmp_path):
    """Zwei Ausstrahlungen desselben Titels am selben Tag (z. B. Erst- und
    Wiederholungssendung) duerfen sich nicht denselben Dateinamen teilen -
    sonst ueberschreibt die zweite Aufnahme die erste (ffmpeg laeuft mit
    "-y")."""
    start1 = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    start2 = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)

    first_path = recorder.build_output_path(str(tmp_path), "Tatort", start1)
    open(first_path, "w").close()  # simuliert bereits vorhandene Aufnahme
    second_path = recorder.build_output_path(str(tmp_path), "Tatort", start2)

    assert first_path != second_path
    assert first_path.endswith("20260601_Tatort.ts")
    assert second_path.endswith("20260601_Tatort_2300.ts")


def test_is_finished_true_for_none_pid():
    assert recorder.is_finished(None) is True


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="os.kill(pid, 0)-Liveness-Check ist ein POSIX-Pattern (Linux-Zielplattform)",
)
def test_is_finished_true_for_nonexistent_pid():
    # PID, die mit an Sicherheit grenzender Wahrscheinlichkeit nicht existiert.
    assert recorder.is_finished(2**30) is True


def test_delete_files_removes_recording_and_log(tmp_path):
    output_path = tmp_path / "aufnahme.ts"
    output_path.write_text("fake")
    log_path = tmp_path / "aufnahme.ts.log"
    log_path.write_text("log")

    recorder.delete_files(str(output_path))

    assert not output_path.exists()
    assert not log_path.exists()


def test_delete_files_handles_missing_file_gracefully(tmp_path):
    recorder.delete_files(str(tmp_path / "does-not-exist.ts"))
    recorder.delete_files(None)
