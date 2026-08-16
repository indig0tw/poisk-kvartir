import json
from pathlib import Path


class JsonConn:
    """Дублирует интерфейс storage.py (connect/is_seen/mark_seen), но
    хранит состояние в обычном JSON-файле вместо SQLite. Нужен для GitHub
    Actions: там нет постоянного диска между запусками, поэтому файл
    состояния коммитится обратно в репозиторий после каждого прогона -
    для этого проще обычный JSON, чем бинарный SQLite (нормально диффится
    в git, не разрастается)."""

    def __init__(self, path: str):
        self.path = Path(path)
        if self.path.exists():
            self.seen_ids: set[str] = set(json.loads(self.path.read_text(encoding="utf-8")))
        else:
            self.seen_ids = set()


def connect(path: str) -> JsonConn:
    return JsonConn(path)


def is_seen(conn: JsonConn, ad_id: str) -> bool:
    return ad_id in conn.seen_ids


def mark_seen(conn: JsonConn, ad_id: str, city: str, matched: bool, title: str | None,
              kaltmiete: float | None, wohnflaeche: float | None, url: str | None) -> None:
    conn.seen_ids.add(ad_id)


def save(conn: JsonConn) -> None:
    conn.path.write_text(json.dumps(sorted(conn.seen_ids)), encoding="utf-8")
