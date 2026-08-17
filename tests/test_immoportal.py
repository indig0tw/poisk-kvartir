import httpx

import immoportal


def _card_html(ad_id: str = "16611", href: str = "/expose/16611", title: str = "Schöne Wohnung",
                kaltmiete: str = "1.350 €", wohnflaeche: str = "50 m2") -> str:
    return f"""
    <div class="property-teaser" data-property-id="{ad_id}">
        <a href="{href}">
            <h2>{title}</h2>
            <div>
                <div class="text-lg font-bold">{kaltmiete}</div>
                <p class="text-sm text-supporting-text">Kaltmiete</p>
            </div>
            <div>
                <div class="text-lg font-bold">{wohnflaeche}</div>
                <p class="text-sm text-supporting-text">Wohnfläche</p>
            </div>
        </a>
    </div>
    """


def test_build_search_url_returns_url_for_supported_city():
    url = immoportal.build_search_url("Köln")
    assert url == "https://www.immoportal.com/suche/de/nordrhein-westfalen/koeln/wohnungen/mieten"


def test_build_search_url_returns_none_for_unknown_city():
    assert immoportal.build_search_url("Berlin") is None


async def test_fetch_listings_parses_labelled_price_and_size():
    html = f"<html><body>{_card_html()}</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await immoportal.fetch_listings(client, "https://example.test/search", limit=10)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.ad_id == "16611"
    assert listing.url == "https://www.immoportal.com/expose/16611"
    assert listing.title == "Schöne Wohnung"
    assert listing.kaltmiete == 1350.0
    assert listing.wohnflaeche == 50.0


async def test_fetch_listings_handles_missing_size_gracefully():
    html = f"<html><body>{_card_html(ad_id='2', href='/expose/2', wohnflaeche='')}</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await immoportal.fetch_listings(client, "https://example.test/search", limit=10)

    assert listings[0].wohnflaeche is None


async def test_fetch_listings_respects_limit():
    html = "<html><body>" + _card_html("1", "/expose/1") + _card_html("2", "/expose/2") + "</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        listings = await immoportal.fetch_listings(client, "https://example.test/search", limit=1)

    assert len(listings) == 1
