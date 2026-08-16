import json

import storage_json


def test_fresh_state_has_nothing_seen(tmp_path):
    conn = storage_json.connect(str(tmp_path / "seen.json"))
    assert storage_json.is_seen(conn, "1") is False


def test_mark_seen_then_is_seen(tmp_path):
    conn = storage_json.connect(str(tmp_path / "seen.json"))
    storage_json.mark_seen(conn, "1", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    assert storage_json.is_seen(conn, "1") is True


def test_save_and_reload_persists_state(tmp_path):
    path = tmp_path / "seen.json"
    conn = storage_json.connect(str(path))
    storage_json.mark_seen(conn, "1", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    storage_json.save(conn)

    assert json.loads(path.read_text(encoding="utf-8")) == ["1"]

    reloaded = storage_json.connect(str(path))
    assert storage_json.is_seen(reloaded, "1") is True
