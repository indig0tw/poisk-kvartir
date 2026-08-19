import main
from scraper import SearchResult


class _FakeSentMessages(list):
    async def __call__(self, bot_token, chat_id, text, **kwargs):
        self.append(text)


def _patch_results(monkeypatch, counts: list[int]):
    """Подменяет fetch_search_results так, чтобы i-й вызов вернул counts[i]
    штук фиктивных результатов (по числу проверочных городов)."""
    call = {"n": 0}

    async def fake_fetch(client, url, limit):
        n = counts[call["n"]] if call["n"] < len(counts) else 0
        call["n"] += 1
        return [SearchResult(ad_id=str(i), url="https://example.test", title="t") for i in range(n)]

    monkeypatch.setattr(main, "fetch_search_results", fake_fetch)


async def test_health_check_alerts_when_all_sample_cities_empty(monkeypatch):
    monkeypatch.setattr(main, "_health_alert_active", False)
    _patch_results(monkeypatch, [0, 0, 0])
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_kleinanzeigen_health(client=None, logger=_NullLogger())

    assert len(sent) == 1
    assert "не отдаёт объявления" in sent[0]
    assert main._health_alert_active is True


async def test_health_check_does_not_alert_when_some_results_present(monkeypatch):
    monkeypatch.setattr(main, "_health_alert_active", False)
    _patch_results(monkeypatch, [0, 3, 0])
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_kleinanzeigen_health(client=None, logger=_NullLogger())

    assert sent == []
    assert main._health_alert_active is False


async def test_health_check_does_not_repeat_alert_while_still_broken(monkeypatch):
    monkeypatch.setattr(main, "_health_alert_active", True)
    _patch_results(monkeypatch, [0, 0, 0])
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_kleinanzeigen_health(client=None, logger=_NullLogger())

    assert sent == []
    assert main._health_alert_active is True


async def test_health_check_sends_recovery_message_once(monkeypatch):
    monkeypatch.setattr(main, "_health_alert_active", True)
    _patch_results(monkeypatch, [5, 0, 0])
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_kleinanzeigen_health(client=None, logger=_NullLogger())

    assert len(sent) == 1
    assert "снова отдаёт" in sent[0]
    assert main._health_alert_active is False


class _NullLogger:
    def error(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass
