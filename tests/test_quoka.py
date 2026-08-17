import httpx

import quoka

_ITEM_LIST_HTML = """
<html><body>
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "ItemList",
    "itemListElement": [
        {
            "name": "Schöne 2-Zimmer-Wohnung",
            "description": "Helle Wohnung, 55 m² Wohnfläche, gerne auch mit Bürgergeld.",
            "url": "anzeigen/immobilienmarkt/vermietungen/vermietung-wohnungen/anzeige/schoene-wohnung/abc123.html",
            "offers": {"price": "480.00", "priceCurrency": "EUR"},
            "itemOffered": {"@type": "House", "floorSize": {"value": "55"}}
        },
        {
            "name": "Zimmer ohne Fläche im JSON",
            "description": "Gemütliches Zimmer, 18qm, ideal für Studenten.",
            "url": "anzeigen/immobilienmarkt/vermietungen/vermietung-wohnungen/anzeige/zimmer/def456.html",
            "offers": {"price": "300.00", "priceCurrency": "EUR"},
            "itemOffered": {"@type": "House", "floorSize": {"value": "0"}}
        }
    ]
}
</script>
</body></html>
"""


def test_build_search_url_returns_none_for_muelheim_an_der_ruhr():
    # Mülheim an der Ruhr не даёт корректной фильтрации на Quoka ни при
    # одном варианте слага (проверено вручную - сайт подсовывает соседние
    # города вроде Oberhausen/Gelsenkirchen) - сознательно отключено.
    assert quoka.build_search_url("Mülheim an der Ruhr") is None


def test_build_search_url_returns_url_for_supported_city():
    url = quoka.build_search_url("Köln")
    assert url is not None
    assert "koeln" in url


async def test_fetch_listings_parses_item_list_json_ld():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ITEM_LIST_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await quoka.fetch_listings(client, "https://example.test/search", limit=10)

    assert len(listings) == 2
    first = listings[0]
    assert first.title == "Schöne 2-Zimmer-Wohnung"
    assert first.kaltmiete == 480.0
    assert first.wohnflaeche == 55.0
    assert first.url == (
        "https://www.quoka.de/anzeigen/immobilienmarkt/vermietungen/vermietung-wohnungen/anzeige/"
        "schoene-wohnung/abc123.html"
    )


async def test_fetch_listings_falls_back_to_description_for_wohnflaeche_when_floorsize_is_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ITEM_LIST_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await quoka.fetch_listings(client, "https://example.test/search", limit=10)

    second = listings[1]
    assert second.kaltmiete == 300.0
    assert second.wohnflaeche == 18.0


async def test_fetch_listings_tolerates_literal_newlines_in_json_strings():
    # Quoka отдаёт технически невалидный JSON-LD - буквальные переносы
    # строк внутри значений вместо экранированных \n (проверено на
    # реальных данных сайта, а не выдумано для теста).
    html = """
    <script type="application/ld+json">
    {
        "@type": "ItemList",
        "itemListElement": [
            {
                "name": "Wohnung mit Zeilenumbruch",
                "description": "Erste Zeile
Zweite Zeile",
                "url": "anzeigen/vermietungen/anzeige/mit-umbruch/xyz789.html",
                "offers": {"price": "350.00"},
                "itemOffered": {"floorSize": {"value": "30"}}
            }
        ]
    }
    </script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await quoka.fetch_listings(client, "https://example.test/search", limit=10)

    assert len(listings) == 1
    assert listings[0].kaltmiete == 350.0
    assert "Zweite Zeile" in listings[0].description


async def test_fetch_listings_unescapes_html_entities_in_title_and_description():
    # Quoka отдаёт title/description с необработанными HTML-сущностями
    # внутри самого JSON (например "B&#252;rgergeld" вместо "Bürgergeld") -
    # без unescape фильтр по ключевым словам такое не находит.
    html_content = """
    <script type="application/ld+json">
    {
        "@type": "ItemList",
        "itemListElement": [
            {
                "name": "Sch&#246;ne Wohnung in K&#246;ln",
                "description": "B&#252;rgergeldempf&#228;nger nicht gew&#252;nscht!",
                "url": "anzeigen/vermietungen/anzeige/entities/qwe987.html",
                "offers": {"price": "450.00"},
                "itemOffered": {"floorSize": {"value": "40"}}
            }
        ]
    }
    </script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await quoka.fetch_listings(client, "https://example.test/search", limit=10)

    assert listings[0].title == "Schöne Wohnung in Köln"
    assert listings[0].description == "Bürgergeldempfänger nicht gewünscht!"


async def test_fetch_listings_respects_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ITEM_LIST_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await quoka.fetch_listings(client, "https://example.test/search", limit=1)

    assert len(listings) == 1
