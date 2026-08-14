import threading

from videobuddy.state import JsonFileStore


def test_modify_is_race_free_under_concurrent_threads(tmp_path):
    """Stellvertreter fuer die zwei echten Prozesse (Scheduler + Webserver):
    20 Threads haengen gleichzeitig einen Eintrag an - am Ende muessen alle
    20 Eintraege da sein, keiner darf durch ein verlorenes Update fehlen."""
    store = JsonFileStore(str(tmp_path / "jobs.json"), default=[])

    def worker(n: int) -> None:
        store.modify(lambda data: data + [n])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = store.read()
    assert sorted(result) == list(range(20))


def test_read_returns_default_when_file_missing(tmp_path):
    store = JsonFileStore(str(tmp_path / "settings.json"), default={"a": 1})
    assert store.read() == {"a": 1}


def test_modify_persists_across_new_store_instances(tmp_path):
    path = str(tmp_path / "jobs.json")
    JsonFileStore(path, default=[]).modify(lambda data: data + ["x"])

    reopened = JsonFileStore(path, default=[])
    assert reopened.read() == ["x"]
