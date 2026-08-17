import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.wg-gesucht.de"

# Числовой city_id - проверено вручную по <title> страницы для каждого из
# 8 городов (без путаницы с районами - в отличие от Kleinanzeigen, тут с
# "Mülheim an der Ruhr" всё чисто).
CITY_IDS = {
    "Mülheim an der Ruhr": 89,
    "Neuss": 224,
    "Köln": 73,
    "Düsseldorf": 30,
    "Essen": 35,
    "Oberhausen": 97,
    "Hilden": 2797,
    "Münster": 91,
}

# ".2." в пути - категория "Wohnungen" (целые квартиры), а не "WG-Zimmer"
# (комнаты в подселении) - пользователю нужна отдельная квартира.
_SEARCH_PATH = "/wohnungen-in-{name}.{city_id}.2.1.0.html"

_SIZE_RE = re.compile(r"([\d.,]+)\s*m")


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


def build_search_url(city_name: str) -> str | None:
    city_id = CITY_IDS.get(city_name)
    if city_id is None:
        return None
    # Название в пути не участвует в фильтрации (сайт смотрит только на
    # city_id), но должно быть валидным URL-сегментом - слаг без умляутов
    # безопаснее прямого немецкого названия.
    slug = city_name.replace("ü", "ue").replace("ö", "oe").replace(" ", "-")
    return f"{BASE_URL}{_SEARCH_PATH.format(name=slug, city_id=city_id)}"


def _parse_euro(text: str) -> float | None:
    match = re.search(r"([\d.,]+)\s*€", text.replace("&euro;", "€"))
    if not match:
        return None
    try:
        return float(match.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


async def fetch_search_results(client: httpx.AsyncClient, url: str, limit: int) -> list[SearchResult]:
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    results = []
    for card in soup.select("div.wgg_card.offer_list_item[data-id]"):
        ad_id = card["data-id"]
        link = card.select_one("h2.truncate_title a")
        if link is None:
            continue
        href = link.get("href") or ""
        title = link.get_text(strip=True)
        if not href:
            continue
        results.append(SearchResult(ad_id=ad_id, url=urljoin(BASE_URL, href), title=title))
        if len(results) >= limit:
            break
    return results


def parse_detail_fields(html: str) -> dict[str, str]:
    """Разбирает блок "Kosten" (Miete/Nebenkosten/...) в словарь
    label -> value. В отличие от Kleinanzeigen, label и value тут не прямые
    siblings - каждый лежит в своём div.col-xs-6, а эти div-ы уже siblings
    друг друга (проверено на реальной разметке страницы объявления)."""
    soup = BeautifulSoup(html, "lxml")
    fields: dict[str, str] = {}
    for label_tag in soup.select("span.section_panel_detail"):
        # Текст лейбла иногда включает вложенный span-подсказку - берём
        # только первый текстовый узел, до вложенных тегов.
        label = label_tag.find(string=True, recursive=False)
        if label is None:
            continue
        label = label.strip().rstrip(":")

        label_container = label_tag.find_parent()
        if label_container is None:
            continue
        value_container = label_container.find_next_sibling()
        if value_container is None:
            continue
        value_tag = value_container.select_one(".section_panel_value")
        if value_tag is None:
            continue
        fields[label] = value_tag.get_text(strip=True)
    return fields


def compute_kaltmiete(fields: dict[str, str]) -> tuple[float | None, str]:
    """"Miete" на WG-Gesucht - это холодная аренда без Nebenkosten,
    проверено вручную на реальном объявлении (Miete 1200€ + Nebenkosten
    450€ = Gesamtmiete/Warmmiete 1650€ из шапки объявления, совпадает)."""
    if "Miete" in fields:
        return _parse_euro(fields["Miete"]), "указана напрямую (поле Miete)"
    return None, "поле Miete не найдено в объявлении"


def parse_wohnflaeche(html: str) -> float | None:
    soup = BeautifulSoup(html, "lxml")
    for detail_tag in soup.select("span.key_fact_detail"):
        if detail_tag.get_text(strip=True) != "Größe":
            continue
        value_tag = detail_tag.find_next_sibling("b", class_="key_fact_value")
        if value_tag is None:
            continue
        match = _SIZE_RE.search(value_tag.get_text(strip=True))
        if match:
            return float(match.group(1).replace(".", "").replace(",", "."))
    return None


def parse_description(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.select_one("div#ad_description_text")
    if tag is None:
        return ""
    for script in tag.select("script"):
        script.decompose()
    return tag.get_text(separator=" ", strip=True)


async def fetch_ad_details(client: httpx.AsyncClient, url: str) -> AdDetails:
    response = await client.get(url)
    response.raise_for_status()
    fields = parse_detail_fields(response.text)
    kaltmiete, note = compute_kaltmiete(fields)
    return AdDetails(
        kaltmiete=kaltmiete, kaltmiete_note=note, wohnflaeche=parse_wohnflaeche(response.text),
        description=parse_description(response.text),
    )
