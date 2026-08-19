import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from models import City

BASE_URL = "https://www.kleinanzeigen.de"
SEARCH_PATH = "/s-wohnung-mieten/preis:0:{max_price}/c203"


@dataclass
class SearchResult:
    ad_id: str
    url: str
    title: str


@dataclass
class AdDetails:
    kaltmiete: float | None
    kaltmiete_note: str
    wohnflaeche: float | None
    description: str


def build_search_url(city: City, max_price: int, radius_km: int) -> str:
    path = SEARCH_PATH.format(max_price=max_price)
    return (
        f"{BASE_URL}{path}?locationStr={quote(city.location_str)}"
        f"&radius={radius_km}&sortingField=SORTING_DATE"
    )


def _parse_euro(text: str) -> float | None:
    match = re.search(r"([\d.,]+)\s*€", text)
    if not match:
        return None
    number = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def _parse_qm(text: str) -> float | None:
    match = re.search(r"([\d.,]+)\s*m", text)
    if not match:
        return None
    number = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def _parse_card_title(article) -> str:
    # Старая вёрстка (класс "aditem" на article) - заголовок в h2.
    title_tag = article.select_one("h2 a.ellipsis")
    if title_tag is not None:
        return title_tag.get_text(strip=True)

    # Новая вёрстка (Tailwind-классы вместо "aditem", без h2 вообще) -
    # заголовка в HTML карточки нет, но есть JSON-LD script с полем title.
    script_tag = article.select_one('script[type="application/ld+json"]')
    if script_tag is not None:
        try:
            data = json.loads(script_tag.string or "")
            title = data.get("title")
            if title:
                return title
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return ""


async def fetch_search_results(client: httpx.AsyncClient, url: str, limit: int) -> list[SearchResult]:
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    results = []
    # Без ".aditem" в селекторе - у части объявлений класс на article теперь
    # Tailwind-утилиты ("flex justify-between p-medium") вместо "aditem",
    # но data-adid/data-href остаются на месте в обоих вариантах вёрстки.
    for article in soup.select("article[data-adid]"):
        ad_id = article["data-adid"]
        href = article.get("data-href") or ""
        title = _parse_card_title(article)
        if not href:
            continue
        results.append(SearchResult(ad_id=ad_id, url=urljoin(BASE_URL, href), title=title))
        if len(results) >= limit:
            break
    return results


def parse_detail_fields(html: str) -> dict[str, str]:
    """Разбирает список характеристик объявления (Wohnfläche, Kaltmiete,
    Nebenkosten, Warmmiete и т.д.) в словарь label -> value. Набор полей
    отличается от объявления к объявлению - не все продавцы указывают
    Kaltmiete и Nebenkosten отдельно."""
    soup = BeautifulSoup(html, "lxml")
    fields: dict[str, str] = {}
    for item in soup.select("li.addetailslist--detail"):
        value_tag = item.select_one(".addetailslist--detail--value")
        if value_tag is None:
            continue
        label = item.get_text(strip=True).replace(value_tag.get_text(strip=True), "").strip()
        fields[label] = value_tag.get_text(strip=True)
    return fields


def compute_kaltmiete(fields: dict[str, str]) -> tuple[float | None, str]:
    """Считает Kaltmiete по правилу пользователя: работаем только с
    Kaltmiete. Если в объявлении она не указана напрямую, а есть Warmmiete +
    Nebenkosten - вычитаем Nebenkosten из Warmmiete. Если есть только
    Warmmiete без разбивки (частый случай для комнат в WG) - точную
    Kaltmiete посчитать нельзя, возвращаем None с пояснением."""
    if "Kaltmiete" in fields:
        return _parse_euro(fields["Kaltmiete"]), "указана напрямую"

    warmmiete = _parse_euro(fields["Warmmiete"]) if "Warmmiete" in fields else None
    nebenkosten = _parse_euro(fields["Nebenkosten"]) if "Nebenkosten" in fields else None
    if warmmiete is not None and nebenkosten is not None:
        return warmmiete - nebenkosten, "рассчитана как Warmmiete - Nebenkosten"

    if warmmiete is not None:
        return None, f"в объявлении только Warmmiete ({warmmiete:.0f} €) без разбивки на Nebenkosten"

    return None, "цена не найдена в объявлении"


def parse_wohnflaeche(fields: dict[str, str]) -> float | None:
    if "Wohnfläche" in fields:
        return _parse_qm(fields["Wohnfläche"])
    return None


def parse_description(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.select_one('p[itemprop="description"]')
    return tag.get_text(strip=True) if tag else ""


async def fetch_ad_details(client: httpx.AsyncClient, url: str) -> AdDetails:
    response = await client.get(url)
    response.raise_for_status()
    fields = parse_detail_fields(response.text)
    kaltmiete, note = compute_kaltmiete(fields)
    return AdDetails(
        kaltmiete=kaltmiete, kaltmiete_note=note, wohnflaeche=parse_wohnflaeche(fields),
        description=parse_description(response.text),
    )
