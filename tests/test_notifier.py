import httpx
import pytest

from notifier import verify_bot_token


def _patch_async_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


async def test_verify_bot_token_succeeds_on_valid_token(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bottoken123/getMe"
        return httpx.Response(200, json={"ok": True, "result": {"id": 1, "is_bot": True}})

    _patch_async_client(monkeypatch, handler)

    await verify_bot_token("token123")


async def test_verify_bot_token_raises_on_invalid_token(monkeypatch):
    """Воспроизводит инцидент 2026-08-28/29: BOM-символ в начале токена -
    Telegram отвечает 404, get_me должен явно поднять исключение, а не
    молча "проглотить" ошибку."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"ok": False, "description": "Not Found"})

    _patch_async_client(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        await verify_bot_token("﻿bot-token-with-bom")
