import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.immowelt.de"

# URL-слаг для поиска по городу - проверено вручную для каждого из 8 городов
# (title страницы подтверждает правильный город, без путаницы с районами
# других городов - в отличие от Kleinanzeigen с "Mülheim an der Ruhr").
SLUGS = {
    "Mülheim an der Ruhr": "muelheim-an-der-ruhr",
    "Neuss": "neuss",
    "Köln": "koeln",
    "Düsseldorf": "duesseldorf",
    "Essen": "essen",
    "Oberhausen": "oberhausen",
    "Hilden": "hilden",
    "Münster": "muenster",
    "Wuppertal": "wuppertal",
    "Solingen": "solingen",
    "Moers": "moers",
    "Leverkusen": "leverkusen",
}

# Immowelt не отдаёт цену/площадь через отдельные HTML-поля в выдаче поиска -
# всё зашито одной строкой в атрибуте title/alt карточки, например:
# "Wohnung zur Miete - Nippes - 1.447 € - 3 Zimmer, 96,3 m², frei ab ...".
_TITLE_RE = re.compile(r"-\s*([\d.,]+)\s*€\s*-\s*[\d.,]+\s*Zimmer,\s*([\d.,]+)\s*m²")


@dataclass
class ImmoweltListing:
    ad_id: str
    url: str
    title: str
    # Cтраница объявления (/expose/...) закрыта капчёй DataDome - проверить
    # эту цену на Kaltmiete/Warmmiete по отдельности, как для Kleinanzeigen,
    # нельзя. Берём как есть - у профессиональных площадок вроде Immowelt
    # это обычно Kaltmiete по умолчанию, но не проверено индивидуально.
    kaltmiete: float | None
    wohnflaeche: float | None


def build_search_url(city_name: str) -> str:
    slug = SLUGS[city_name]
    return f"{BASE_URL}/liste/{slug}/wohnungen/mieten"


def _parse_number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


async def fetch_listings(client: httpx.AsyncClient, url: str, limit: int) -> list[ImmoweltListing]:
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    listings = []
    for card in soup.select('div[data-testid="serp-core-classified-card-testid"]'):
        card_id = card.get("id", "")
        ad_id = card_id.removeprefix("classified-card-")
        link = card.select_one('a[data-testid="card-mfe-covering-link-testid"]')
        if not ad_id or link is None:
            continue

        href = link.get("href") or ""
        title_attr = link.get("title") or ""
        if not href:
            continue

        match = _TITLE_RE.search(title_attr)
        kaltmiete = _parse_number(match.group(1)) if match else None
        wohnflaeche = _parse_number(match.group(2)) if match else None

        listings.append(ImmoweltListing(
            ad_id=ad_id, url=urljoin(BASE_URL, href), title=title_attr,
            kaltmiete=kaltmiete, wohnflaeche=wohnflaeche,
        ))
        if len(listings) >= limit:
            break
    return listings
