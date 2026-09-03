import asyncio

import httpx

import config
import immoportal
import immowelt
import storage
import sync
from errors import is_transient
from logger import setup_logger
from models import City
from notifier import send_message, verify_bot_token
from scraper import build_search_url, fetch_search_results
from tracker import check_city, check_city_immoportal, check_city_immowelt


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


# Сколько городов подряд проверять "здоровье" каждого источника каждый
# цикл - 3 достаточно, чтобы отличить реальную поломку парсера/сайта от
# того, что у конкретного города сейчас просто нет объявлений (см. баг
# 2026-08-19, когда Kleinanzeigen сменил вёрстку и парсер молча вернул 0
# для всех городов, кроме первого - без этой проверки такое не заметили бы
# неделями).
_HEALTH_CHECK_SAMPLE_SIZE = 3

# Не дублировать уведомление каждый цикл, пока проблема не устранена -
# только один раз при обнаружении и один раз при восстановлении. Отдельный
# флаг на источник - поломка одного сайта не должна маскироваться/маскировать
# состояние остальных.
_health_alert_active: dict[str, bool] = {}

# Сколько циклов подряд источник должен вернуть 0 объявлений, прежде чем
# слать уведомление - у некоторых сайтов на практике бывает разовая
# защитная страница на один цикл без всякой реальной поломки, с одного
# нулевого результата такое не отличить от настоящей поломки вроде смены
# вёрстки Kleinanzeigen 2026-08-19.
_HEALTH_ALERT_THRESHOLD = 2

_health_fail_streak: dict[str, int] = {}


async def _kleinanzeigen_count(client: httpx.AsyncClient, city: City) -> int:
    url = build_search_url(city, int(city.max_kaltmiete * config.SEARCH_PRICE_BUFFER), config.SEARCH_RADIUS_KM)
    return len(await fetch_search_results(client, url, 5))


async def _immowelt_count(client: httpx.AsyncClient, city: City) -> int:
    url = immowelt.build_search_url(city.name)
    return len(await immowelt.fetch_listings(client, url, 5))


async def _immoportal_count(client: httpx.AsyncClient, city: City) -> int:
    url = immoportal.build_search_url(city.name)
    if url is None:
        return 0
    return len(await immoportal.fetch_listings(client, url, 5))


_HEALTH_CHECK_SOURCES = (
    ("Kleinanzeigen", _kleinanzeigen_count),
    ("Immowelt", _immowelt_count),
    ("Immoportal", _immoportal_count),
)


async def _check_source_health(client: httpx.AsyncClient, logger, source: str, fetch_count) -> None:
    total_results = 0
    for city in config.CITIES[:_HEALTH_CHECK_SAMPLE_SIZE]:
        try:
            total_results += await asyncio.wait_for(fetch_count(client, city), timeout=_CHECK_TIMEOUT_SECONDS)
        except Exception:
            pass  # сетевые ошибки уже залогированы основным циклом проверки этого же города/источника

    was_active = _health_alert_active.get(source, False)
    if total_results == 0:
        streak = _health_fail_streak.get(source, 0) + 1
        _health_fail_streak[source] = streak
        logger.warning(
            f"[health] {source} вернул 0 объявлений по {_HEALTH_CHECK_SAMPLE_SIZE} проверочным городам "
            f"(подряд: {streak}/{_HEALTH_ALERT_THRESHOLD})"
        )
        if streak >= _HEALTH_ALERT_THRESHOLD and not was_active:
            logger.error(
                f"[health] {source} не отдаёт объявления {streak} цикла(ов) подряд - "
                "возможно, сайт снова сменил вёрстку или заблокировал бота"
            )
            await send_message(
                config.BOT_TOKEN, config.CHAT_ID,
                f"⚠️ {source} не отдаёт объявления уже {streak} цикла(ов) подряд - "
                "похоже, сайт что-то изменил или заблокировал бота. Стоит проверить.",
            )
            _health_alert_active[source] = True
    else:
        _health_fail_streak[source] = 0
        if was_active:
            await send_message(config.BOT_TOKEN, config.CHAT_ID, f"✅ {source} снова отдаёт объявления, всё в порядке.")
            _health_alert_active[source] = False


async def _check_bot_token(logger) -> None:
    """Проверяет BOT_TOKEN каждый цикл через Telegram getMe. Если токен
    битый - здесь физически нельзя послать Telegram-алерт (это же он и
    сломан), поэтому единственный сигнал - явная ERROR-запись в лог. Не
    покрывает облачный BOT_TOKEN отдельно (у run_once.py свой .env-независимый
    секрет) - см. verify_bot_token в run_once.py, где та же проверка роняет
    сам workflow, что и есть настоящий сигнал наружу для облака (см.
    инцидент 2026-08-28/29, когда битый токен в облаке сутки был незаметен
    именно потому, что ни локальная проверка его не видела, ни облако не
    падало явно)."""
    try:
        await asyncio.wait_for(verify_bot_token(config.BOT_TOKEN), timeout=_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        if is_transient(exc):
            # Обычная временная сетевая проблема (например, сеть ещё не
            # поднялась сразу после включения ПК/старта бота) - не признак
            # битого токена, просто попробуем на следующем цикле, как и
            # везде в этом файле. Раньше это тоже логировалось как ERROR
            # "BOT_TOKEN невалиден", что выглядело как поломка Telegram при
            # каждом старте бота, хотя на самом деле сеть просто не успела
            # подняться.
            logger.warning(f"[health] Telegram временно недоступен, попробуем на следующем цикле: {exc}")
        else:
            logger.error(f"[health] BOT_TOKEN невалиден - уведомления не будут доходить: {exc}")


async def _check_one(client: httpx.AsyncClient, conn, city: City, logger) -> None:
    await _run_check(city.name, check_city(
        client, conn, city, config.SEARCH_PRICE_BUFFER, config.MAX_WOHNFLAECHE_QM,
        config.MAX_LISTINGS_PER_CITY, config.SEARCH_RADIUS_KM, config.BOT_TOKEN, config.CHAT_ID,
    ), logger)

    await _run_check(f"Immowelt/{city.name}", check_city_immowelt(
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
            await _check_bot_token(logger)

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

            for source, fetch_count in _HEALTH_CHECK_SOURCES:
                try:
                    await _check_source_health(client, logger, source, fetch_count)
                except Exception:
                    logger.error(f"[health] проверка здоровья {source} сама упала с ошибкой", exc_info=True)

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
