import httpx

from models import City
from scraper import (
    build_search_url,
    compute_kaltmiete,
    fetch_ad_details,
    fetch_search_results,
    parse_detail_fields,
    parse_wohnflaeche,
)

SEARCH_HTML = """
<html><body><ul>
<li>
<article class="aditem" data-adid="111" data-href="/s-anzeige/erste-wohnung/111-203-1">
  <div class="aditem-main">
    <h2 class="text-module-begin"><a class="ellipsis" href="/s-anzeige/erste-wohnung/111-203-1">
    Erste Wohnung</a></h2>
  </div>
</article>
</li>
<li>
<article class="aditem" data-adid="222" data-href="/s-anzeige/zweite-wohnung/222-203-1">
  <div class="aditem-main">
    <h2 class="text-module-begin"><a class="ellipsis" href="/s-anzeige/zweite-wohnung/222-203-1">
    Zweite Wohnung</a></h2>
  </div>
</article>
</li>
</ul></body></html>
"""


def _detail_html(*rows: tuple[str, str]) -> str:
    items = "".join(
        f'<li class="addetailslist--detail">{label}'
        f'<span class="addetailslist--detail--value">{value}</span></li>'
        for label, value in rows
    )
    return f"<html><body><ul>{items}</ul></body></html>"


def test_build_search_url_encodes_city_and_price():
    city = City("Mülheim an der Ruhr", "Mülheim an der Ruhr", 440.50)
    url = build_search_url(city, 572, 0)
    assert "preis:0:572" in url
    assert "locationStr=M%C3%BClheim%20an%20der%20Ruhr" in url
    assert "radius=0" in url
    assert "sortingField=SORTING_DATE" in url


def test_parse_detail_fields_extracts_label_value_pairs():
    html = _detail_html(("Wohnfläche", "53 m²"), ("Zimmer", "2"))
    fields = parse_detail_fields(html)
    assert fields == {"Wohnfläche": "53 m²", "Zimmer": "2"}


def test_compute_kaltmiete_uses_direct_value_when_present():
    fields = {"Kaltmiete": "770 €", "Nebenkosten": "110 €", "Warmmiete": "880 €"}
    kaltmiete, note = compute_kaltmiete(fields)
    assert kaltmiete == 770.0
    assert "напрямую" in note


def test_compute_kaltmiete_subtracts_nebenkosten_from_warmmiete():
    # Пример из скриншота пользователя: Warmmiete 710, Nebenkosten 200 -> Kaltmiete 510
    fields = {"Nebenkosten": "200 €", "Warmmiete": "710 €"}
    kaltmiete, note = compute_kaltmiete(fields)
    assert kaltmiete == 510.0
    assert "Warmmiete - Nebenkosten" in note


def test_compute_kaltmiete_returns_none_when_only_warmmiete_given():
    fields = {"Warmmiete": "660 €"}
    kaltmiete, note = compute_kaltmiete(fields)
    assert kaltmiete is None
    assert "без разбивки" in note


def test_compute_kaltmiete_returns_none_when_nothing_found():
    kaltmiete, note = compute_kaltmiete({})
    assert kaltmiete is None
    assert "не найдена" in note


def test_parse_wohnflaeche_reads_qm_value():
    assert parse_wohnflaeche({"Wohnfläche": "53 m²"}) == 53.0
    assert parse_wohnflaeche({}) is None


async def test_fetch_search_results_parses_ad_id_url_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await fetch_search_results(client, "https://example.test/search", limit=10)

    assert [r.ad_id for r in results] == ["111", "222"]
    assert results[0].title == "Erste Wohnung"
    assert results[0].url == "https://www.kleinanzeigen.de/s-anzeige/erste-wohnung/111-203-1"


async def test_fetch_search_results_respects_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await fetch_search_results(client, "https://example.test/search", limit=1)

    assert len(results) == 1


async def test_fetch_ad_details_combines_parsing_and_kaltmiete_calc():
    html = _detail_html(("Wohnfläche", "53 m²"), ("Nebenkosten", "200 €"), ("Warmmiete", "710 €"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        details = await fetch_ad_details(client, "https://example.test/ad/1")

    assert details.kaltmiete == 510.0
    assert details.wohnflaeche == 53.0
