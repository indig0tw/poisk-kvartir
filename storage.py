import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_listings (
    ad_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    city TEXT NOT NULL,
    matched INTEGER NOT NULL,
    title TEXT,
    kaltmiete REAL,
    wohnflaeche REAL,
    url TEXT
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def is_seen(conn: sqlite3.Connection, ad_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_listings WHERE ad_id = ?", (ad_id,)).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, ad_id: str, city: str, matched: bool, title: str | None,
              kaltmiete: float | None, wohnflaeche: float | None, url: str | None) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO seen_listings
           (ad_id, ts, city, matched, title, kaltmiete, wohnflaeche, url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ad_id, datetime.now(timezone.utc).isoformat(), city, int(matched), title, kaltmiete,
         wohnflaeche, url),
    )
    conn.commit()
