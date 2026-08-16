import httpx

from immowelt import build_search_url, fetch_listings

# Разметка карточки упрощена, но сохраняет реальную структуру (проверено
# вручную на живой странице поиска immowelt.de): id карточки, ссылка на
# объявление и вся нужная информация (цена/комнаты/площадь) одной строкой
# в атрибуте title.
SEARCH_HTML = """
<html><body>
<div id="classified-card-26UXN77QPEQB" data-testid="serp-core-classified-card-testid">
  <a href="https://www.immowelt.de/expose/a57a27cf-bfca-462d-b498-a33aeed0d005"
     title="Wohnung zur Miete - Nippes - 1.447 € - 3 Zimmer, 96,3 m², frei ab 17.08.2026"
     data-testid="card-mfe-covering-link-testid"></a>
</div>
<div id="classified-card-99ZZ11AABB" data-testid="serp-core-classified-card-testid">
  <a href="https://www.immowelt.de/expose/b57a27cf-bfca-462d-b498-a33aeed0d006"
     title="Wohnung zur Miete - Ehrenfeld - 395 € - 1 Zimmer, 20 m², frei ab 01.10.2026"
     data-testid="card-mfe-covering-link-testid"></a>
</div>
</body></html>
"""


def test_build_search_url_uses_correct_slug():
    assert build_search_url("Mülheim an der Ruhr") == "https://www.immowelt.de/liste/muelheim-an-der-ruhr/wohnungen/mieten"
    assert build_search_url("Köln") == "https://www.immowelt.de/liste/koeln/wohnungen/mieten"


async def test_fetch_listings_parses_price_and_size_from_title_attribute():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await fetch_listings(client, "https://example.test/search", limit=10)

    assert len(listings) == 2
    assert listings[0].ad_id == "26UXN77QPEQB"
    assert listings[0].kaltmiete == 1447.0
    assert listings[0].wohnflaeche == 96.3
    assert listings[0].url == "https://www.immowelt.de/expose/a57a27cf-bfca-462d-b498-a33aeed0d005"

    assert listings[1].ad_id == "99ZZ11AABB"
    assert listings[1].kaltmiete == 395.0
    assert listings[1].wohnflaeche == 20.0


async def test_fetch_listings_respects_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SEARCH_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await fetch_listings(client, "https://example.test/search", limit=1)

    assert len(listings) == 1
