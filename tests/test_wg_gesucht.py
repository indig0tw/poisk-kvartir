import httpx

import wg_gesucht

SEARCH_HTML = """
<html><body>
<div class="wgg_card offer_list_item" data-id="111">
  <h2 class="truncate_title"><a href="/wohnungen-in-Koeln-Ehrenfeld.111.html">Erste Wohnung</a></h2>
</div>
<div class="wgg_card offer_list_item" data-id="222">
  <h2 class="truncate_title"><a href="/wohnungen-in-Koeln-Nippes.222.html">Zweite Wohnung</a></h2>
</div>
</body></html>
"""


def _detail_html(size: str = "85m&sup2;", miete: str = "1200&euro;", nebenkosten: str | None = "450&euro;",
                  description: str = "Schöne Wohnung.") -> str:
    # Реальная разметка WG-Gesucht: label и value НЕ прямые siblings - у
    # каждого свой div.col-xs-6, а эти div-ы уже siblings друг друга.
    nebenkosten_row = (
        '<div class="row">'
        '<div class="col-xs-6"><span class="section_panel_detail">Nebenkosten:</span></div>'
        f'<div class="col-xs-6"><span class="section_panel_value">{nebenkosten}</span></div>'
        "</div>"
        if nebenkosten is not None else ""
    )
    return f"""
    <html><body>
    <span class="key_fact_detail">Größe</span>
    <b class="key_fact_value">{size}</b>

    <div class="row">
        <div class="col-xs-6"><span class="section_panel_detail">Miete:</span></div>
        <div class="col-xs-6"><span class="section_panel_value">{miete}</span></div>
    </div>
    {nebenkosten_row}

    <div id="ad_description_text">{description}</div>
    </body></html>
    """


def test_build_search_url_uses_correct_city_id():
    url = wg_gesucht.build_search_url("Köln")
    assert url == "https://www.wg-gesucht.de/wohnungen-in-Koeln.73.2.1.0.html"


def test_build_search_url_returns_none_for_unknown_city():
    assert wg_gesucht.build_search_url("Berlin") is None


def test_build_search_url_transliterates_umlauts_in_slug():
    url = wg_gesucht.build_search_url("Mülheim an der Ruhr")
    assert "Muelheim-an-der-Ruhr" in url
    assert ".89.2.1.0.html" in url


def test_parse_detail_fields_extracts_miete_and_nebenkosten():
    fields = wg_gesucht.parse_detail_fields(_detail_html())
    assert fields == {"Miete": "1200€", "Nebenkosten": "450€"}


def test_compute_kaltmiete_uses_miete_field_directly():
    kaltmiete, note = wg_gesucht.compute_kaltmiete({"Miete": "1200€", "Nebenkosten": "450€"})
    assert kaltmiete == 1200.0
    assert "Miete" in note


def test_compute_kaltmiete_returns_none_when_miete_field_missing():
    kaltmiete, note = wg_gesucht.compute_kaltmiete({"Nebenkosten": "450€"})
    assert kaltmiete is None


def test_parse_wohnflaeche_reads_groesse():
    assert wg_gesucht.parse_wohnflaeche(_detail_html(size="85m&sup2;")) == 85.0


def test_parse_description_strips_scripts():
    html = _detail_html(description='Text vor <script>evil()</script> Text danach')
    description = wg_gesucht.parse_description(html)
    assert "evil()" not in description
    assert "Text vor" in description and "Text danach" in description


async def test_fetch_search_results_parses_ad_id_url_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await wg_gesucht.fetch_search_results(client, "https://example.test/search", limit=10)

    assert [r.ad_id for r in results] == ["111", "222"]
    assert results[0].title == "Erste Wohnung"
    assert results[0].url == "https://www.wg-gesucht.de/wohnungen-in-Koeln-Ehrenfeld.111.html"


async def test_fetch_search_results_respects_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await wg_gesucht.fetch_search_results(client, "https://example.test/search", limit=1)

    assert len(results) == 1


async def test_fetch_ad_details_combines_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_detail_html())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        details = await wg_gesucht.fetch_ad_details(client, "https://example.test/ad/1")

    assert details.kaltmiete == 1200.0
    assert details.wohnflaeche == 85.0
    assert "Schöne Wohnung" in details.description
