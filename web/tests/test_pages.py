"""Server-rendered page tests: content, filters, transliteration, XSS, errors."""

import urllib.parse


def test_home_renders_value_prop_and_freshness(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert '<html lang="mk">' in html
    assert "Најдете каде е најевтино да пазарите" in html
    assert 'action="/search"' in html
    assert "Vero" in html and "Stokomak" in html
    assert "Свежи податоци" in html
    assert "17.04.2026" in html  # latest published date rendered server-side
    assert 'rel="canonical" href="http://web.test/"' in html
    assert "noindex" not in html


def test_search_renders_server_side_offers(client, stub):
    res = client.get("/search", params={"q": "млеко"})
    assert res.status_code == 200
    assert stub.search_calls[-1]["q"] == "млеко"
    html = res.text
    assert "Резултати за „млеко“" in html
    assert "Млеко Devin млеко 3.2% 1л" in html
    assert "75,00 ден." in html
    assert "ВЕРО 1" in html
    assert "акција" in html
    assert "објавено 17.04.2026" in html
    assert 'data-canonical-id="10"' in html
    assert 'data-retailer-product-id="101"' in html
    assert "1 понуда" in html


def test_search_hides_inconsistent_source_unit_price(client, stub):
    stub.offers[0].update({
        "normalizedSize": "500g",
        "priceCurrent": "32.00",
        "unitPrice": "64.00",
        "unitLabel": "1 гр",
    })
    res = client.get("/search", params={"q": "леб"})
    assert res.status_code == 200
    assert "ед. цена непотврдена" in res.text
    assert "64,00 ден./1 гр" not in res.text
    assert "32,00 ден." in res.text

    stub.offers[0]["unitLabel"] = "1 кг"
    res = client.get("/search", params={"q": "леб"})
    assert "64,00 ден./кг" in res.text
    assert "ед. цена непотврдена" not in res.text


def test_search_transliterates_latin_input(client, stub):
    res = client.get("/search", params={"q": "mleko"})
    assert res.status_code == 200
    assert stub.search_calls[-1]["q"] == "млеко"
    assert "пресловено" in res.text


def test_search_passes_filters_and_sort(client, stub):
    res = client.get("/search", params={"q": "млеко", "retailer": "vero", "instock": "true", "promo": "true", "sort": "price_desc"})
    assert res.status_code == 200
    call = stub.search_calls[-1]
    assert call["retailer"] == "vero"
    assert call["inStockOnly"] is True
    assert call["promoOnly"] is True
    assert call["sort"] == "price_desc"


def test_search_pagination_links_preserve_query(client, stub):
    stub.offers_total = 45
    res = client.get("/search", params={"q": "млеко", "page": 1})
    assert res.status_code == 200
    html = res.text
    assert "Страница 2 од 3" in html
    assert f'/search?q={urllib.parse.quote("млеко")}' in html
    assert "page=0" in html and "page=2" in html


def test_search_empty_query_browse_mode(client):
    res = client.get("/search")
    assert res.status_code == 200
    assert "Сите понуди" in res.text


def test_search_no_results_is_honest(client, stub):
    stub.offers = []
    stub.offers_total = 0
    res = client.get("/search", params={"q": "непознат"})
    assert res.status_code == 200
    assert "Нема пронајдени понуди" in res.text


def test_search_escapes_html_in_query(client):
    res = client.get("/search", params={"q": '<script>alert(1)</script>'})
    assert res.status_code == 200
    assert "<script>alert(1)</script>" not in res.text
    assert "&lt;script&gt;" in res.text


def test_search_offers_out_of_stock_note(client, stub):
    stub.offers[0]["availability"] = "out_of_stock"
    res = client.get("/search", params={"q": "млеко"})
    assert "Нема на залиха" in res.text


def test_compare_lists_verified_groups(client):
    res = client.get("/compare", params={"q": "млеко"})
    assert res.status_code == 200
    html = res.text
    assert "Млеко Devin 3.2% 1л" in html
    assert "85,00 ден." in html and "99,00 ден." in html and "14,00 ден." in html
    assert 'href="/compare/10"' in html
    assert "2 продавачи" in html


def test_compare_detail_is_deep_linkable(client, stub):
    res = client.get("/compare/10")
    assert res.status_code == 200
    assert stub.compare_calls[-1]["canonicalId"] == 10
    html = res.text
    assert "<h1>Млеко Devin 3.2% 1л</h1>" in html
    assert "stokomak" in html
    assert 'data-canonical-id="10"' in html
    assert 'rel="canonical" href="http://web.test/compare/10"' in html


def test_compare_detail_unknown_id_404(client):
    res = client.get("/compare/999")
    assert res.status_code == 404
    assert "не е пронајдена" in res.text


def test_compare_detail_non_numeric_id_gets_html_404(client):
    res = client.get("/compare/not-a-number")
    assert res.status_code == 404
    assert "не е пронајдена" in res.text


def test_basket_page_is_shell_without_totals(client):
    res = client.get("/basket")
    assert res.status_code == 200
    html = res.text
    assert 'id="basket-root"' in html
    assert 'id="basket-optimize"' in html
    assert "noindex" in html
    # The basket shell must never contain server-computed money values.
    assert "ден." not in html


def test_api_outage_renders_error_page(offline_client):
    # Home stays usable without freshness data (graceful degradation).
    res = offline_client.get("/")
    assert res.status_code == 200
    assert "Податоците за обем и свежина моментално не се достапни" in res.text

    # Search cannot render without the catalog -> honest 503 error page.
    res = offline_client.get("/search", params={"q": "млеко"})
    assert res.status_code == 503
    assert "Услугата е привремено недостапна" in res.text
