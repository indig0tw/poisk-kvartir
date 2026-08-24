import asyncio
import logging

import httpx

import config
import storage_json
import sync
import tracker
from errors import is_transient
from models import City

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("apartment_finder")

CLOUD_STATE_PATH = "cloud_seen.json"


async def _run_check(label: str, coro) -> None:
    try:
        await coro
    except Exception as exc:
        if is_transient(exc):
            logger.warning(f"[{label}] временная ошибка сети: {exc}")
        else:
            logger.error(f"[{label}] неожиданная ошибка проверки", exc_info=True)


async def _check_one(client: httpx.AsyncClient, conn, city: City) -> None:
    await _run_check(city.name, tracker.check_city(
        client, conn, city, config.SEARCH_PRICE_BUFFER, config.MAX_WOHNFLAECHE_QM,
        config.MAX_LISTINGS_PER_CITY, config.SEARCH_RADIUS_KM, config.BOT_TOKEN, config.CHAT_ID,
    ))

    await _run_check(f"Immowelt/{city.name}", tracker.check_city_immowelt(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ))

    await _run_check(f"WG-Gesucht/{city.name}", tracker.check_city_wg_gesucht(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ))

    await _run_check(f"Immoportal/{city.name}", tracker.check_city_immoportal(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ))


async def main() -> None:
    # Подменяем storage-бэкенд tracker.py на JSON-версию: для GitHub Actions
    # (нет постоянного диска между запусками, состояние коммитится обратно в
    # репозиторий как обычный файл) вместо SQLite, которым пользуется
    # main.py при локальном непрерывном запуске. Логика проверки в
    # tracker.check_city от этого не меняется - она обращается к
    # storage.is_seen/mark_seen как к модулю-зависимости. Сделано внутри
    # main(), а не на уровне модуля - иначе один только "import run_once"
    # (например, в тестах) молча и необратимо ломал бы tracker.storage для
    # всего процесса, включая совсем не связанные тесты SQLite-бэкенда.
    tracker.storage = storage_json

    conn = storage_json.connect(CLOUD_STATE_PATH)
    initial_ids = set(conn.seen_ids)
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}

    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as client:
        for city in config.CITIES:
            logger.info(f"Проверяю {city.name}...")
            await _check_one(client, conn, city)

    storage_json.save(conn)
    logger.info(f"Готово. Всего просмотрено объявлений: {len(conn.seen_ids)}")

    # Отправляем найденные за этот прогон id обратно в репозиторий через
    # GitHub Contents API (тот же безопасный sha-механизм, что и у
    # локального бота в sync.py) - а не через git commit/push внутри
    # workflow, как было раньше. Раньше был реальный конфликт: если
    # локальный бот успевал запушить своё состояние через sync.py в то же
    # время, обычный "git push" в конце workflow падал с "rejected (fetch
    # first)" и всё, что нашёл этот прогон, терялось. Через API конфликт
    # решается сам - сравнивается sha текущего содержимого файла, устаревший
    # sha просто повторяется с актуальным состоянием (см. sync.push_new_ids).
    if config.GITHUB_TOKEN:
        new_ids = conn.seen_ids - initial_ids
        try:
            await asyncio.to_thread(sync.push_new_ids, new_ids, config.GITHUB_TOKEN, 3, "облачным workflow")
        except Exception:
            logger.error("[sync] не удалось отправить найденные id в cloud_seen.json", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
