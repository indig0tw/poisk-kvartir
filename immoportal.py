import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.immoportal.com"

# URL-слаг для поиска по городу - проверено вручную по <title> страницы для
# каждого из 8 городов (без путаницы с районами - включая Mülheim an der
# Ruhr, где у Kleinanzeigen и Quoka была путаница).
SLUGS = {
    "Mülheim an der Ruhr": "muelheim-an-der-ruhr",
    "Neuss": "neuss",
    "Köln": "koeln",
    "Düsseldorf": "duesseldorf",
    "Essen": "essen",
    "Oberhausen": "oberhausen",
    "Hilden": "hilden",
    "Münster": "muenster",
}

_NUMBER_RE = re.compile(r"([\d.,]+)")


@dataclass
class Listing:
    ad_id: str
    url: str
    title: str
    # Цена и площадь берутся прямо из карточки в выдаче поиска - явно
    # подписаны словами "Kaltmiete"/"Wohnfläche" (проверено вручную на
    # реальных объявлениях), заход на страницу объявления не нужен.
    kaltmiete: float | None
    wohnflaeche: float | None


def build_search_url(city_name: str) -> str | None:
    slug = SLUGS.get(city_name)
    if slug is None:
        return None
    return f"{BASE_URL}/suche/de/nordrhein-westfalen/{slug}/wohnungen/mieten"


def _parse_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _find_labelled_value(card, label: str) -> float | None:
    for label_tag in card.select("p"):
        if label_tag.get_text(strip=True) != label:
            continue
        value_tag = label_tag.find_previous_sibling("div")
        if value_tag is None:
            continue
        return _parse_number(value_tag.get_text(strip=True))
    return None


async def fetch_listings(client: httpx.AsyncClient, url: str, limit: int) -> list[Listing]:
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    listings = []
    for card in soup.select("div.property-teaser[data-property-id]"):
        ad_id = card["data-property-id"]
        link = card.select_one("a[href]")
        title_tag = card.select_one("h2")
        if link is None or title_tag is None:
            continue
        href = link.get("href") or ""
        if not href:
            continue

        listings.append(Listing(
            ad_id=ad_id, url=urljoin(BASE_URL, href), title=title_tag.get_text(strip=True),
            kaltmiete=_find_labelled_value(card, "Kaltmiete"),
            wohnflaeche=_find_labelled_value(card, "Wohnfläche"),
        ))
        if len(listings) >= limit:
            break
    return listings
