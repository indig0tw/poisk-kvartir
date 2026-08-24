import base64
import json
import logging

import httpx

logger = logging.getLogger("apartment_finder")

REPO = "indig0tw/poisk-kvartir"
FILE_PATH = "cloud_seen.json"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "poisk-kvartir-sync",
    }


def _get_remote_state(token: str) -> tuple[set[str], str]:
    """Текущее содержимое cloud_seen.json прямо из репозитория через GitHub
    API - без git pull/checkout, чтобы не трогать локальную рабочую копию
    (в той же папке параллельно может идти обычная разработка)."""
    response = httpx.get(API_URL, headers=_headers(token), timeout=20)
    response.raise_for_status()
    data = response.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return set(json.loads(content)), data["sha"]


def pull_cloud_ids(token: str) -> set[str]:
    """Список id, которые уже нашёл и разослал облачный workflow - без
    этого локальный бот при запуске находит те же объявления "впервые" и
    шлёт по ним повторное уведомление."""
    try:
        ids, _ = _get_remote_state(token)
        return ids
    except Exception as exc:
        logger.warning(f"[sync] не удалось получить cloud_seen.json из GitHub: {exc}")
        return set()


def push_new_ids(new_ids: set[str], token: str, attempts: int = 3, source: str = "локальным ботом") -> None:
    """Отправляет id, найденные (локальным ботом или облачным workflow) и
    которых ещё нет в cloud_seen.json, в репозиторий - чтобы другая сторона
    их уже не переоткрывала и не слала то же уведомление ещё раз. Конфликт
    с параллельным коммитом от другого писателя (используется и main.py, и
    run_once.py - гонка между ними и была причиной бага 2026-08-24)
    разрешается через sha текущего содержимого файла - GitHub API отклонит
    устаревший sha, и мы просто повторяем с актуальным."""
    if not new_ids:
        return

    for attempt in range(attempts):
        try:
            current, sha = _get_remote_state(token)
        except Exception as exc:
            logger.warning(f"[sync] не удалось прочитать текущее состояние перед отправкой: {exc}")
            return

        merged = current | new_ids
        if merged == current:
            return

        content_b64 = base64.b64encode(
            json.dumps(sorted(merged), ensure_ascii=False).encode("utf-8")
        ).decode()
        payload = {
            "message": f"Синхронизация: объявления, найденные {source}",
            "content": content_b64,
            "sha": sha,
        }
        response = httpx.put(API_URL, headers=_headers(token), json=payload, timeout=20)
        if response.status_code in (200, 201):
            return

        logger.warning(
            f"[sync] push не удался (попытка {attempt + 1}/{attempts}), "
            f"HTTP {response.status_code}: {response.text[:200]}"
        )

    logger.error("[sync] не удалось отправить новые id в облако после нескольких попыток")
