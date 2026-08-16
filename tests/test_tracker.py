import httpx
import pytest

import storage
import tracker
from models import City
from scraper import AdDetails, SearchResult

CITY = City("Köln", "Köln", 677.0)


def _patch_search(monkeypatch, results):
    async def fake_fetch_search_results(client, url, limit):
        return results

    monkeypatch.setattr(tracker, "fetch_search_results", fake_fetch_search_results)


def _patch_details(monkeypatch, details_by_id):
    async def fake_fetch_ad_details(client, url):
        return details_by_id[url]

    monkeypatch.setattr(tracker, "fetch_ad_details", fake_fetch_ad_details)


def _patch_notifier(monkeypatch):
    sent = []

    async def fake_send_message(bot_token, chat_id, text, buttons=None):
        sent.append(text)

    monkeypatch.setattr(tracker, "send_message", fake_send_message)
    return sent


@pytest.fixture
def http_client():
    return httpx.AsyncClient()


async def test_matching_ad_triggers_notification_and_is_marked_seen(monkeypatch, conn, http_client):
    result = SearchResult(ad_id="1", url="https://example.test/1", title="Schöne Wohnung")
    _patch_search(monkeypatch, [result])
    _patch_details(monkeypatch, {result.url: AdDetails(kaltmiete=500.0, kaltmiete_note="", wohnflaeche=50.0)})
    sent = _patch_notifier(monkeypatch)

    await tracker.check_city(http_client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert len(sent) == 1
    assert "Schöne Wohnung" in sent[0]
    assert storage.is_seen(conn, "1") is True


async def test_ad_above_price_cap_is_not_notified_but_is_marked_seen(monkeypatch, conn, http_client):
    result = SearchResult(ad_id="2", url="https://example.test/2", title="Teure Wohnung")
    _patch_search(monkeypatch, [result])
    _patch_details(monkeypatch, {result.url: AdDetails(kaltmiete=900.0, kaltmiete_note="", wohnflaeche=50.0)})
    sent = _patch_notifier(monkeypatch)

    await tracker.check_city(http_client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert sent == []
    assert storage.is_seen(conn, "2") is True


async def test_ad_above_size_cap_is_not_notified(monkeypatch, conn, http_client):
    result = SearchResult(ad_id="3", url="https://example.test/3", title="Große Wohnung")
    _patch_search(monkeypatch, [result])
    _patch_details(monkeypatch, {result.url: AdDetails(kaltmiete=500.0, kaltmiete_note="", wohnflaeche=60.0)})
    sent = _patch_notifier(monkeypatch)

    await tracker.check_city(http_client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert sent == []


async def test_ad_with_unknown_kaltmiete_is_not_notified_but_is_marked_seen(monkeypatch, conn, http_client):
    result = SearchResult(ad_id="4", url="https://example.test/4", title="WG Zimmer")
    _patch_search(monkeypatch, [result])
    _patch_details(monkeypatch, {
        result.url: AdDetails(kaltmiete=None, kaltmiete_note="в объявлении только Warmmiete", wohnflaeche=20.0),
    })
    sent = _patch_notifier(monkeypatch)

    await tracker.check_city(http_client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert sent == []
    assert storage.is_seen(conn, "4") is True


async def test_already_seen_ad_is_not_reprocessed(monkeypatch, conn, http_client):
    storage.mark_seen(conn, "5", CITY.name, False, "Alte Anzeige", None, None, None)
    result = SearchResult(ad_id="5", url="https://example.test/5", title="Alte Anzeige")
    _patch_search(monkeypatch, [result])

    async def fail_if_called(client, url):
        raise AssertionError("fetch_ad_details не должен вызываться для уже виденного объявления")

    monkeypatch.setattr(tracker, "fetch_ad_details", fail_if_called)
    sent = _patch_notifier(monkeypatch)

    await tracker.check_city(http_client, conn, CITY, 1.3, 55.0, 10, 0, "token", "chat")

    assert sent == []
