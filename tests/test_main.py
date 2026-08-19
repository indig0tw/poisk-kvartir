import main


class _FakeSentMessages(list):
    async def __call__(self, bot_token, chat_id, text, **kwargs):
        self.append(text)


class _NullLogger:
    def error(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def _fake_fetch_count(counts: list[int]):
    """i-й вызов возвращает counts[i] (по числу проверочных городов)."""
    call = {"n": 0}

    async def fetch_count(client, city):
        n = counts[call["n"]] if call["n"] < len(counts) else 0
        call["n"] += 1
        return n

    return fetch_count


async def test_health_check_alerts_when_all_sample_cities_empty(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", False)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    assert len(sent) == 1
    assert "TestSource" in sent[0]
    assert "не отдаёт объявления" in sent[0]
    assert main._health_alert_active["TestSource"] is True


async def test_health_check_does_not_alert_when_some_results_present(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", False)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 3, 0]))

    assert sent == []
    assert main._health_alert_active["TestSource"] is False


async def test_health_check_does_not_repeat_alert_while_still_broken(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", True)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    assert sent == []
    assert main._health_alert_active["TestSource"] is True


async def test_health_check_sends_recovery_message_once(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", True)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([5, 0, 0]))

    assert len(sent) == 1
    assert "снова отдаёт" in sent[0]
    assert main._health_alert_active["TestSource"] is False


async def test_health_check_sources_are_independent(monkeypatch):
    # Поломка одного источника не должна триггерить/маскировать уведомление
    # по другому - у каждого свой флаг в _health_alert_active.
    monkeypatch.setitem(main._health_alert_active, "Broken", False)
    monkeypatch.setitem(main._health_alert_active, "Healthy", False)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "Broken", _fake_fetch_count([0, 0, 0]))
    await main._check_source_health(None, _NullLogger(), "Healthy", _fake_fetch_count([1, 2, 3]))

    assert len(sent) == 1
    assert "Broken" in sent[0]
    assert main._health_alert_active["Broken"] is True
    assert main._health_alert_active["Healthy"] is False


async def test_health_check_sources_cover_all_four_sites():
    names = [name for name, _ in main._HEALTH_CHECK_SOURCES]
    assert names == ["Kleinanzeigen", "Immowelt", "WG-Gesucht", "Immoportal"]


async def test_wg_gesucht_count_returns_zero_for_unsupported_city(monkeypatch):
    monkeypatch.setattr(main.wg_gesucht, "build_search_url", lambda name: None)
    from models import City

    count = await main._wg_gesucht_count(None, City("Nowhere", "Nowhere", 500.0))
    assert count == 0


async def test_immoportal_count_returns_zero_for_unsupported_city(monkeypatch):
    monkeypatch.setattr(main.immoportal, "build_search_url", lambda name: None)
    from models import City

    count = await main._immoportal_count(None, City("Nowhere", "Nowhere", 500.0))
    assert count == 0
