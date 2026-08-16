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
