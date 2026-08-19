import base64
import json
from dataclasses import dataclass, field

import httpx
import pytest

import sync


def _encode(ids: list[str]) -> str:
    return base64.b64encode(json.dumps(ids, ensure_ascii=False).encode("utf-8")).decode()


@dataclass
class _FakeGetResponse:
    ids: list[str]
    sha: str = "sha-1"

    def raise_for_status(self):
        pass

    def json(self):
        return {"content": _encode(self.ids), "sha": self.sha}


@dataclass
class _FakePutResponse:
    status_code: int
    text: str = ""


@dataclass
class _FakeApi:
    """Подменяет httpx.get/httpx.put для Contents API - без реальной сети."""
    get_ids: list[str] = field(default_factory=list)
    get_sha: str = "sha-1"
    put_status: int = 200
    get_calls: int = 0
    put_calls: list = field(default_factory=list)

    def get(self, url, **kwargs):
        self.get_calls += 1
        return _FakeGetResponse(self.get_ids, self.get_sha)

    def put(self, url, **kwargs):
        self.put_calls.append(kwargs["json"])
        return _FakePutResponse(self.put_status)


def test_pull_cloud_ids_returns_remote_content(monkeypatch):
    fake = _FakeApi(get_ids=["1", "iw:2"])
    monkeypatch.setattr(httpx, "get", fake.get)
    assert sync.pull_cloud_ids("token") == {"1", "iw:2"}


def test_pull_cloud_ids_returns_empty_set_on_error(monkeypatch):
    def broken_get(url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", broken_get)
    assert sync.pull_cloud_ids("token") == set()


def test_push_new_ids_noop_when_nothing_new(monkeypatch):
    fake = _FakeApi()
    monkeypatch.setattr(httpx, "get", fake.get)
    monkeypatch.setattr(httpx, "put", fake.put)
    sync.push_new_ids(set(), "token")
    assert fake.get_calls == 0
    assert fake.put_calls == []


def test_push_new_ids_skips_already_present_ids(monkeypatch):
    fake = _FakeApi(get_ids=["1", "2"])
    monkeypatch.setattr(httpx, "get", fake.get)
    monkeypatch.setattr(httpx, "put", fake.put)
    sync.push_new_ids({"2"}, "token")
    assert fake.put_calls == []


def test_push_new_ids_merges_and_sends_sha(monkeypatch):
    fake = _FakeApi(get_ids=["1"], get_sha="abc123")
    monkeypatch.setattr(httpx, "get", fake.get)
    monkeypatch.setattr(httpx, "put", fake.put)

    sync.push_new_ids({"2"}, "token")

    assert len(fake.put_calls) == 1
    payload = fake.put_calls[0]
    assert payload["sha"] == "abc123"
    sent_ids = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    assert set(sent_ids) == {"1", "2"}


def test_push_new_ids_retries_on_sha_conflict_then_succeeds(monkeypatch):
    call_count = {"put": 0}
    state = {"ids": ["1"], "sha": "sha-old"}

    def fake_get(url, **kwargs):
        return _FakeGetResponse(state["ids"], state["sha"])

    def fake_put(url, **kwargs):
        call_count["put"] += 1
        if call_count["put"] == 1:
            # Кто-то другой успел закоммитить первым - sha устарел.
            state["ids"] = ["1", "3"]
            state["sha"] = "sha-new"
            return _FakePutResponse(status_code=409, text="sha mismatch")
        return _FakePutResponse(status_code=200)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "put", fake_put)

    sync.push_new_ids({"2"}, "token", attempts=3)

    assert call_count["put"] == 2


def test_push_new_ids_gives_up_after_exhausting_attempts(monkeypatch):
    fake = _FakeApi(get_ids=["1"])
    fake.put_status = 409
    monkeypatch.setattr(httpx, "get", fake.get)
    monkeypatch.setattr(httpx, "put", fake.put)

    sync.push_new_ids({"2"}, "token", attempts=2)

    assert len(fake.put_calls) == 2
