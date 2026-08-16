import asyncio

import httpx

import config
import storage
from errors import is_transient
from logger import setup_logger
from models import City
from tracker import check_city, check_city_immowelt


async def _check_one(client: httpx.AsyncClient, conn, city: City, logger) -> None:
    try:
        await check_city(
            client, conn, city, config.SEARCH_PRICE_BUFFER, config.MAX_WOHNFLAECHE_QM,
            config.MAX_LISTINGS_PER_CITY, config.SEARCH_RADIUS_KM, config.BOT_TOKEN, config.CHAT_ID,
        )
    except Exception as exc:
        if is_transient(exc):
            logger.warning(f"[{city.name}] временная ошибка сети, попробуем на следующем цикле: {exc}")
        else:
            logger.error(f"[{city.name}] неожиданная ошибка проверки", exc_info=True)

    try:
        await check_city_immowelt(
            client, conn, city, config.MAX_WOHNFLAECHE_QM, config.MAX_LISTINGS_PER_CITY,
            config.BOT_TOKEN, config.CHAT_ID,
        )
    except Exception as exc:
        if is_transient(exc):
            logger.warning(f"[Immowelt/{city.name}] временная ошибка сети, попробуем на следующем цикле: {exc}")
        else:
            logger.error(f"[Immowelt/{city.name}] неожиданная ошибка проверки", exc_info=True)


async def main() -> None:
    logger = setup_logger(config.LOG_PATH, config.LOG_RETENTION_DAYS)
    logger.info(f"Бот запущен. Города: {', '.join(city.name for city in config.CITIES)}")

    conn = storage.connect(config.DB_PATH)
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}

    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as client:
        while True:
            for city in config.CITIES:
                await _check_one(client, conn, city, logger)
            await asyncio.sleep(config.POLL_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(main())
