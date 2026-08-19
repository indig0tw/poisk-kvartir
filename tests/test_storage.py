import storage


def test_unseen_ad_is_not_seen(conn):
    assert storage.is_seen(conn, "123") is False


def test_marked_ad_is_seen(conn):
    storage.mark_seen(conn, "123", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    assert storage.is_seen(conn, "123") is True


def test_mark_seen_is_idempotent():
    conn = storage.connect(":memory:")
    storage.mark_seen(conn, "123", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    # Повторная отметка того же ad_id не должна падать (INSERT OR IGNORE)
    storage.mark_seen(conn, "123", "Köln", False, "Другой заголовок", None, None, None)
    row = conn.execute("SELECT title FROM seen_listings WHERE ad_id = '123'").fetchone()
    assert row[0] == "Titel"


def test_get_all_ids_returns_everything_marked_seen(conn):
    storage.mark_seen(conn, "123", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    storage.mark_seen(conn, "iw:abc", "Essen", False, "Titel 2", None, None, None)
    assert storage.get_all_ids(conn) == {"123", "iw:abc"}


def test_get_all_ids_empty_when_nothing_seen(conn):
    assert storage.get_all_ids(conn) == set()


def test_mark_seen_bulk_makes_ids_seen(conn):
    storage.mark_seen_bulk(conn, {"ip:1", "ip:2"})
    assert storage.is_seen(conn, "ip:1") is True
    assert storage.is_seen(conn, "ip:2") is True
    assert storage.is_seen(conn, "ip:3") is False


def test_mark_seen_bulk_does_not_override_existing_metadata(conn):
    storage.mark_seen(conn, "123", "Köln", True, "Titel", 500.0, 50.0, "https://example.test/1")
    # Bulk-импорт того же id (например, из cloud_seen.json) не должен затирать
    # уже собранные локально метаданные (INSERT OR IGNORE).
    storage.mark_seen_bulk(conn, {"123"})
    row = conn.execute("SELECT title FROM seen_listings WHERE ad_id = '123'").fetchone()
    assert row[0] == "Titel"


def test_mark_seen_bulk_with_empty_set_does_nothing(conn):
    storage.mark_seen_bulk(conn, set())
    assert storage.get_all_ids(conn) == set()
