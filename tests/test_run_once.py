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


async def test_main_pushes_only_newly_found_ids(monkeypatch, tmp_path):
    """Раньше состояние коммитилось через git внутри workflow и падало при
    гонке с sync.py локального бота ("rejected (fetch first)"), потому что
    оба пишут в один и тот же cloud_seen.json. Теперь run_once.py сам
    отправляет только вновь найденные за этот прогон id через тот же
    safe-merge API, что и sync.py - проверяем, что в push уходит именно
    diff, а не всё содержимое conn.seen_ids (включая то, что уже было в
    файле до этого прогона)."""
    import run_once

    # main() сам делает "tracker.storage = storage_json" (сырое присвоение,
    # не через monkeypatch) - без этой строки оно бы утекло в остальные
    # тесты, которые рассчитывают на SQLite-бэкенд по умолчанию.
    monkeypatch.setattr(tracker, "storage", storage_json)

    state_path = tmp_path / "cloud_seen.json"
    state_path.write_text('["existing"]', encoding="utf-8")
    monkeypatch.setattr(run_once, "CLOUD_STATE_PATH", str(state_path))
    monkeypatch.setattr(run_once.config, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(run_once.config, "CITIES", [CITY])

    async def fake_check_one(client, conn, city):
        conn.seen_ids.add("new-1")

    monkeypatch.setattr(run_once, "_check_one", fake_check_one)

    pushed = {}

    def fake_push(new_ids, token, *args, **kwargs):
        pushed["new_ids"] = new_ids
        pushed["token"] = token

    monkeypatch.setattr(run_once.sync, "push_new_ids", fake_push)

    await run_once.main()

    assert pushed["new_ids"] == {"new-1"}
    assert pushed["token"] == "token"


async def test_main_skips_push_without_github_token(monkeypatch, tmp_path):
    import run_once

    monkeypatch.setattr(tracker, "storage", storage_json)

    state_path = tmp_path / "cloud_seen.json"
    state_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(run_once, "CLOUD_STATE_PATH", str(state_path))
    monkeypatch.setattr(run_once.config, "GITHUB_TOKEN", None)
    monkeypatch.setattr(run_once.config, "CITIES", [CITY])

    async def fake_check_one(client, conn, city):
        pass

    monkeypatch.setattr(run_once, "_check_one", fake_check_one)

    called = []
    monkeypatch.setattr(run_once.sync, "push_new_ids", lambda *a, **k: called.append(True))

    await run_once.main()

    assert called == []
