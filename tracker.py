import logging
import sqlite3

import httpx

import storage
from models import City
from notifier import send_message
from scraper import build_search_url, fetch_ad_details, fetch_search_results

logger = logging.getLogger("apartment_finder")


def _format_message(city: City, title: str, kaltmiete: float | None, kaltmiete_note: str,
                     wohnflaeche: float | None, url: str) -> str:
    price_line = f"{kaltmiete:.0f} € Kaltmiete" if kaltmiete is not None else f"Кальтмитте неизвестна ({kaltmiete_note})"
    size_line = f"{wohnflaeche:.0f} м²" if wohnflaeche is not None else "площадь не указана"
    return (
        f"🏠 {city.name} | {price_line} | {size_line}\n"
        f"Лимит по городу: {city.max_kaltmiete:.0f} €\n\n"
        f"{title}\n{url}"
    )


async def check_city(client: httpx.AsyncClient, conn: sqlite3.Connection, city: City,
                      search_price_buffer: float, max_wohnflaeche_qm: float, max_listings: int,
                      radius_km: int, bot_token: str, chat_id: str) -> None:
    search_url = build_search_url(city, int(city.max_kaltmiete * search_price_buffer), radius_km)
    results = await fetch_search_results(client, search_url, max_listings)

    for result in results:
        if storage.is_seen(conn, result.ad_id):
            continue

        details = await fetch_ad_details(client, result.url)

        size_ok = details.wohnflaeche is None or details.wohnflaeche <= max_wohnflaeche_qm
        price_ok = details.kaltmiete is not None and details.kaltmiete <= city.max_kaltmiete
        matched = price_ok and size_ok

        if matched:
            text = _format_message(
                city, result.title, details.kaltmiete, details.kaltmiete_note,
                details.wohnflaeche, result.url,
            )
            await send_message(bot_token, chat_id, text)
            logger.info(f"[{city.name}] найдено подходящее объявление: {result.title} "
                        f"({details.kaltmiete} €, {details.wohnflaeche} м²) - {result.url}")

        storage.mark_seen(
            conn, result.ad_id, city.name, matched, result.title,
            details.kaltmiete, details.wohnflaeche, result.url,
        )
