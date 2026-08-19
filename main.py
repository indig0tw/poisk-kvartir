import asyncio

import httpx

import config
import storage
import sync
from errors import is_transient
from logger import setup_logger
from models import City
from notifier import send_message
from scraper import build_search_url, fetch_search_results
from tracker import check_city, check_city_immoportal, check_city_immowelt, check_city_wg_gesucht


# Жёсткий потолок на одну проверку город+источник. httpx timeout=20 на
# клиенте в теории должен ограничивать каждый запрос сам по себе, но на
# практике словили реальное зависание без единой ошибки на несколько часов
# (похоже на подвисшее DNS-разрешение в Windows, которое не всегда уважает
# таймаут httpx) - этот wait_for снаружи гарантирует, что цикл не встанет
# намертво, даже если внутренний таймаут почему-то не сработал.
_CHECK_TIMEOUT_SECONDS = 60


async def _run_check(label: str, coro, logger) -> None:
    try:
        await asyncio.wait_for(coro, timeout=_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        if is_transient(exc):
            logger.warning(f"[{label}] временная ошибка сети, попробуем на следующем цикле: {exc}")
        else:
            logger.error(f"[{label}] неожиданная ошибка проверки", exc_info=True)


# Сколько городов подряд проверять "здоровье" Kleinanzeigen каждый цикл -
# 3 достаточно, чтобы отличить реальную поломку парсера/сайта от того, что
# у конкретного города сейчас просто нет объявлений (см. баг 2026-08-19,
# когда сайт сменил вёрстку и парсер молча вернул 0 для всех городов, кроме
# первого - без этой проверки такое не заметили бы неделями).
_HEALTH_CHECK_SAMPLE_SIZE = 3

# Не дублировать уведомление каждый цикл, пока проблема не устранена -
# только один раз при обнаружении и один раз при восстановлении.
_health_alert_active = False


async def _check_kleinanzeigen_health(client: httpx.AsyncClient, logger) -> None:
    global _health_alert_active

    total_results = 0
    for city in config.CITIES[:_HEALTH_CHECK_SAMPLE_SIZE]:
        try:
            url = build_search_url(city, int(city.max_kaltmiete * config.SEARCH_PRICE_BUFFER), config.SEARCH_RADIUS_KM)
            results = await asyncio.wait_for(fetch_search_results(client, url, 5), timeout=_CHECK_TIMEOUT_SECONDS)
            total_results += len(results)
        except Exception:
            pass  # сетевые ошибки уже залогированы основным циклом проверки этого же города

    if total_results == 0:
        logger.error(
            f"[health] Kleinanzeigen не вернул ни одного объявления по {_HEALTH_CHECK_SAMPLE_SIZE} "
            f"проверочным городам - возможно, сайт снова сменил вёрстку или заблокировал бота"
        )
        if not _health_alert_active:
            await send_message(
                config.BOT_TOKEN, config.CHAT_ID,
                "⚠️ Kleinanzeigen не отдаёт объявления ни по одному из проверочных городов уже целый цикл - "
                "похоже, сайт что-то изменил или заблокировал бота. Стоит проверить.",
            )
            _health_alert_active = True
    elif _health_alert_active:
        await send_message(config.BOT_TOKEN, config.CHAT_ID, "✅ Kleinanzeigen снова отдаёт объявления, всё в порядке.")
        _health_alert_active = False


async def _check_one(client: httpx.AsyncClient, conn, city: City, logger) -> None:
    await _run_check(city.name, check_city(
        client, conn, city, config.SEARCH_PRICE_BUFFER, config.MAX_WOHNFLAECHE_QM,
        config.MAX_LISTINGS_PER_CITY, config.SEARCH_RADIUS_KM, config.BOT_TOKEN, config.CHAT_ID,
    ), logger)

    await _run_check(f"Immowelt/{city.name}", check_city_immowelt(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ), logger)

    await _run_check(f"WG-Gesucht/{city.name}", check_city_wg_gesucht(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ), logger)

    await _run_check(f"Immoportal/{city.name}", check_city_immoportal(
        client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
        config.BOT_TOKEN, config.CHAT_ID,
    ), logger)


async def main() -> None:
    logger = setup_logger(config.LOG_PATH, config.LOG_RETENTION_DAYS)
    logger.info(f"Бот запущен. Города: {', '.join(city.name for city in config.CITIES)}")

    conn = storage.connect(config.DB_PATH)
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}

    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as client:
        while True:
            cloud_ids: set[str] = set()
            if config.GITHUB_TOKEN:
                try:
                    cloud_ids = await asyncio.wait_for(
                        asyncio.to_thread(sync.pull_cloud_ids, config.GITHUB_TOKEN),
                        timeout=_CHECK_TIMEOUT_SECONDS,
                    )
                    storage.mark_seen_bulk(conn, cloud_ids - storage.get_all_ids(conn))
                except Exception:
                    logger.error("[sync] не удалось подтянуть cloud_seen.json", exc_info=True)

            for city in config.CITIES:
                await _check_one(client, conn, city, logger)

            try:
                await _check_kleinanzeigen_health(client, logger)
            except Exception:
                logger.error("[health] проверка здоровья Kleinanzeigen сама упала с ошибкой", exc_info=True)

            if config.GITHUB_TOKEN:
                try:
                    new_ids = storage.get_all_ids(conn) - cloud_ids
                    await asyncio.wait_for(
                        asyncio.to_thread(sync.push_new_ids, new_ids, config.GITHUB_TOKEN),
                        timeout=_CHECK_TIMEOUT_SECONDS,
                    )
                except Exception:
                    logger.error("[sync] не удалось отправить новые id в cloud_seen.json", exc_info=True)

            await asyncio.sleep(config.POLL_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(main())
