"""SEO + technical essentials: robots, sitemap, noindex rules, headers."""

def test_robots_disallows_user_and_api_paths(client):
    res = client.get("/robots.txt")
    assert res.status_code == 200
    text = res.text
    assert "User-agent: *" in text
    assert "Disallow: /basket" in text
    assert "Disallow: /api/" in text
    assert "Sitemap: http://web.test/sitemap.xml" in text


def test_sitemap_contains_only_stable_urls(client):
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert '<loc>http://web.test/</loc>' in res.text
    assert '<loc>http://web.test/compare</loc>' in res.text
    assert "/search" not in res.text
    assert "/basket" not in res.text


def test_search_pages_are_noindex_but_canonicalised(client):
    res = client.get("/search", params={"q": "млеко"})
    assert '<meta name="robots" content="noindex, follow">' in res.text
    assert 'rel="canonical" href="http://web.test/search"' in res.text


def test_compare_pagination_is_noindex_first_page_is_indexable(client):
    first = client.get("/compare")
    assert 'name="robots"' not in first.text
    second = client.get("/compare", params={"page": 1})
    assert '<meta name="robots" content="noindex, follow">' in second.text


def test_security_headers_present(client):
    res = client.get("/")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    csp = res.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp


def test_home_has_unique_title_and_description(client):
    res = client.get("/")
    assert "<title>AI Пазарење — најдобри цени во Македонија</title>" in res.text
    assert 'name="description"' in res.text
