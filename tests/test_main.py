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


def _reset(monkeypatch, source: str):
    monkeypatch.setitem(main._health_alert_active, source, False)
    monkeypatch.setitem(main._health_fail_streak, source, 0)


async def test_health_check_does_not_alert_on_first_failed_cycle(monkeypatch):
    # Один цикл с нулём - это ещё может быть разовая защита сайта, не повод
    # сразу слать уведомление.
    _reset(monkeypatch, "TestSource")
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    assert sent == []
    assert main._health_alert_active["TestSource"] is False
    assert main._health_fail_streak["TestSource"] == 1


async def test_health_check_alerts_after_threshold_consecutive_failures(monkeypatch):
    _reset(monkeypatch, "TestSource")
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))
    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    assert len(sent) == 1
    assert "TestSource" in sent[0]
    assert "не отдаёт объявления" in sent[0]
    assert main._health_alert_active["TestSource"] is True


async def test_health_check_resets_streak_on_success_before_threshold(monkeypatch):
    _reset(monkeypatch, "TestSource")
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))
    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([1, 0, 0]))
    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    # Успешный цикл посреди двух неудачных должен сбросить счётчик - до
    # порога так и не дошло, уведомления быть не должно.
    assert sent == []
    assert main._health_fail_streak["TestSource"] == 1


async def test_health_check_does_not_repeat_alert_while_still_broken(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", True)
    monkeypatch.setitem(main._health_fail_streak, "TestSource", 2)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([0, 0, 0]))

    assert sent == []
    assert main._health_alert_active["TestSource"] is True


async def test_health_check_sends_recovery_message_once(monkeypatch):
    monkeypatch.setitem(main._health_alert_active, "TestSource", True)
    monkeypatch.setitem(main._health_fail_streak, "TestSource", 2)
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    await main._check_source_health(None, _NullLogger(), "TestSource", _fake_fetch_count([5, 0, 0]))

    assert len(sent) == 1
    assert "снова отдаёт" in sent[0]
    assert main._health_alert_active["TestSource"] is False
    assert main._health_fail_streak["TestSource"] == 0


async def test_health_check_sources_are_independent(monkeypatch):
    # Поломка одного источника не должна триггерить/маскировать уведомление
    # по другому - у каждого свой флаг и свой streak.
    _reset(monkeypatch, "Broken")
    _reset(monkeypatch, "Healthy")
    sent = _FakeSentMessages()
    monkeypatch.setattr(main, "send_message", sent)

    for _ in range(2):
        await main._check_source_health(None, _NullLogger(), "Broken", _fake_fetch_count([0, 0, 0]))
    await main._check_source_health(None, _NullLogger(), "Healthy", _fake_fetch_count([1, 2, 3]))

    assert len(sent) == 1
    assert "Broken" in sent[0]
    assert main._health_alert_active["Broken"] is True
    assert main._health_alert_active["Healthy"] is False


async def test_health_check_sources_cover_all_sites():
    names = [name for name, _ in main._HEALTH_CHECK_SOURCES]
    assert names == ["Kleinanzeigen", "Immowelt", "Immoportal"]


async def test_immoportal_count_returns_zero_for_unsupported_city(monkeypatch):
    monkeypatch.setattr(main.immoportal, "build_search_url", lambda name: None)
    from models import City

    count = await main._immoportal_count(None, City("Nowhere", "Nowhere", 500.0))
    assert count == 0


class _RecordingLogger(_NullLogger):
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)


async def test_check_bot_token_logs_error_without_raising_on_invalid_token(monkeypatch):
    """Воспроизводит инцидент 2026-08-28/29 (BOM в BOT_TOKEN): main.py -
    бесконечный цикл, он не должен падать целиком из-за битого токена
    (в отличие от run_once.py, для которого это фатально), но проблема
    обязана быть явно видна в логе, а не потеряться среди обычных сетевых
    предупреждений."""
    async def fake_verify_fails(bot_token):
        raise Exception("404 Not Found")

    monkeypatch.setattr(main, "verify_bot_token", fake_verify_fails)
    logger = _RecordingLogger()

    await main._check_bot_token(logger)

    assert len(logger.errors) == 1
    assert "BOT_TOKEN" in logger.errors[0]


async def test_check_bot_token_is_silent_on_valid_token(monkeypatch):
    async def fake_verify_ok(bot_token):
        pass

    monkeypatch.setattr(main, "verify_bot_token", fake_verify_ok)
    logger = _RecordingLogger()

    await main._check_bot_token(logger)

    assert logger.errors == []


async def test_check_bot_token_logs_warning_not_error_on_transient_network_failure(monkeypatch):
    """Раньше любая ошибка при проверке токена (включая обычный
    "сеть ещё не поднялась после старта ПК") логировалась как ERROR
    "BOT_TOKEN невалиден" - выглядело так, будто именно Telegram сломался
    при каждом запуске бота, хотя на самом деле сеть просто не успела
    подняться. Временные сетевые ошибки (httpx.RequestError и подобные,
    см. errors.is_transient) должны идти в warning, не в error."""
    import httpx

    async def fake_verify_network_down(bot_token):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(main, "verify_bot_token", fake_verify_network_down)
    logger = _RecordingLogger()

    await main._check_bot_token(logger)

    assert logger.errors == []
    assert len(logger.warnings) == 1
