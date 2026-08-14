from datetime import datetime, timedelta, timezone

from videobuddy import scheduler


def _times():
    start = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=90)
    return start, end


def test_create_job_sets_scheduled_status_and_buffers(make_config):
    config = make_config()
    start, end = _times()

    job = scheduler.create_job(
        config, "ard.de", "Tatort", start, end,
        buffer_before_minutes=3, buffer_after_minutes=12,
    )

    assert job["status"] == "scheduled"
    assert job["channel"] == "ard.de"
    assert datetime.fromisoformat(job["record_start"]) == start - timedelta(minutes=3)
    assert datetime.fromisoformat(job["record_end"]) == end + timedelta(minutes=12)


def test_create_job_is_idempotent_on_double_click(make_config):
    config = make_config()
    start, end = _times()

    first = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    second = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    assert first["id"] == second["id"]
    assert len(scheduler.list_jobs(config)) == 1


def test_create_job_allows_duplicate_after_cancel(make_config):
    config = make_config()
    start, end = _times()

    first = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    scheduler.cancel_job(config, first["id"])
    second = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    assert first["id"] != second["id"]
    assert len(scheduler.list_jobs(config)) == 2


def test_cancel_job_only_works_for_scheduled_status(make_config):
    config = make_config()
    start, end = _times()
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    scheduler.update_job(config, job["id"], status="recording")
    assert scheduler.cancel_job(config, job["id"]) is False
    assert scheduler.get_job(config, job["id"])["status"] == "recording"


def test_cancel_job_returns_false_for_unknown_id(make_config):
    config = make_config()
    assert scheduler.cancel_job(config, "does-not-exist") is False


def test_list_jobs_empty_by_default(make_config):
    config = make_config()
    assert scheduler.list_jobs(config) == []


def test_update_job_merges_fields(make_config):
    config = make_config()
    start, end = _times()
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    updated = scheduler.update_job(config, job["id"], status="recording", pid=1234)

    assert updated["status"] == "recording"
    assert updated["pid"] == 1234
    assert updated["channel"] == "ard.de"
