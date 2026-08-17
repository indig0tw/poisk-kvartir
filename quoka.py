import html
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

BASE_URL = "https://www.quoka.de"

# URL-слаг для поиска по городу - проверено вручную по полю addressLocality
# в самой выдаче (не по заголовку страницы - он часто общий даже при
# правильной фильтрации). "Mülheim an der Ruhr" ни в одном варианте слага
# не даёт корректную фильтрацию (сайт подсовывает соседние города вроде
# Oberhausen/Gelsenkirchen) - для этого города Quoka не подключаем, город
# и так покрыт Kleinanzeigen и Immowelt.
SLUGS = {
    "Neuss": "neuss",
    "Köln": "koeln",
    "Düsseldorf": "duesseldorf",
    "Essen": "essen",
    "Oberhausen": "oberhausen",
    "Hilden": "hilden",
    "Münster": "muenster",
}

_WOHNFLAECHE_RE = re.compile(r"(\d+[.,]?\d*)\s*(?:m²|m2|qm|m\s+Wohnfläche)", re.IGNORECASE)


@dataclass
class QuokaListing:
    ad_id: str
    url: str
    title: str
    description: str
    # offers.price в JSON-LD Quoka - проверено вручную на реальных
    # объявлениях: совпадает с "Kaltmiete" из текста описания.
    kaltmiete: float | None
    wohnflaeche: float | None


def build_search_url(city_name: str) -> str | None:
    slug = SLUGS.get(city_name)
    if slug is None:
        return None
    return f"{BASE_URL}/anzeigen/immobilienmarkt/vermietungen/vermietung-wohnungen/nordrhein-westfalen/{slug}/"


def _parse_wohnflaeche(item: dict, description: str) -> float | None:
    floor_size = item.get("itemOffered", {}).get("floorSize", {}).get("value")
    if floor_size:
        try:
            value = float(str(floor_size).replace(",", "."))
            if value > 0:
                return value
        except ValueError:
            pass
    match = _WOHNFLAECHE_RE.search(description)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _extract_item_lists(html: str) -> list[dict]:
    """Достаёт itemListElement из <script type="application/ld+json">
    блоков. JSON внутри вложенный (image/offers/itemOffered) - выцепить его
    регуляркой по фигурным скобкам ненадёжно (non-greedy обрывается на
    первой попавшейся "}", а не на настоящем конце объекта), поэтому просто
    берём сырой текст между тегами script и парсим его целиком."""
    items = []
    for script_match in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL,
    ):
        try:
            # strict=False - JSON-LD от Quoka технически невалиден: в
            # описаниях объявлений встречаются буквальные переносы строк
            # вместо экранированных \n, из-за чего строгий парсер падает
            # с "Invalid control character" (проверено на реальных данных).
            data = json.loads(script_match.group(1), strict=False)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "ItemList":
            items.extend(data.get("itemListElement", []))
    return items


async def fetch_listings(client: httpx.AsyncClient, url: str, limit: int) -> list[QuokaListing]:
    response = await client.get(url)
    response.raise_for_status()

    listings = []
    for item in _extract_item_lists(response.text):
        href = item.get("url") or ""
        # html.unescape - Quoka отдаёт title/description с необработанными
        # HTML-сущностями внутри JSON-строк (например "B&#252;rgergeld"
        # вместо "Bürgergeld"), иначе фильтр по ключевым словам их не
        # найдёт (проверено на реальных данных - без unescape "Bürgergeld"
        # не находился в описании, где он точно был).
        title = html.unescape(item.get("name") or "")
        description = html.unescape(item.get("description") or "")
        if not href:
            continue

        offer = item.get("offers", {})
        price = offer.get("price")
        kaltmiete = float(price) if price not in (None, "", "0.00") else None

        listings.append(QuokaListing(
            ad_id=href, url=urljoin(BASE_URL + "/", href), title=title, description=description,
            kaltmiete=kaltmiete, wohnflaeche=_parse_wohnflaeche(item, description),
        ))
        if len(listings) >= limit:
            break
    return listings
