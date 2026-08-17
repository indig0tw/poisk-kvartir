import httpx

import storage_json
import tracker
from models import City
from scraper import AdDetails, SearchResult

CITY = City("Köln", "Köln", 677.0)


async def test_check_city_works_with_json_storage_backend(monkeypatch, tmp_path):
    """run_once.py (для GitHub Actions) подменяет tracker.storage на
    storage_json вместо SQLite - проверяем, что check_city от этого не
    ломается и дедупликация/уведомления работают так же, как с SQLite
    (см. test_tracker.py)."""
    monkeypatch.setattr(tracker, "storage", storage_json)
    conn = storage_json.connect(str(tmp_path / "seen.json"))

    result = SearchResult(ad_id="1", url="https://example.test/1", title="Schöne Wohnung")

    async def fake_fetch_search_results(client, url, limit):
        return [result]

    async def fake_fetch_ad_details(client, url):
        return AdDetails(kaltmiete=500.0, kaltmiete_note="", wohnflaeche=50.0, description="")

    sent = []

    async def fake_send_message(bot_token, chat_id, text, buttons=None):
        sent.append(text)

    monkeypatch.setattr(tracker, "fetch_search_results", fake_fetch_search_results)
    monkeypatch.setattr(tracker, "fetch_ad_details", fake_fetch_ad_details)
    monkeypatch.setattr(tracker, "send_message", fake_send_message)

    async with httpx.AsyncClient() as client:
        await tracker.check_city(client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")
        # Повторный проход не должен снова отправить то же объявление.
        await tracker.check_city(client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert len(sent) == 1
    assert storage_json.is_seen(conn, "1") is True
