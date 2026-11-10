"""Browser smoke test for the M14 web prototype (local dev tool, not CI).

Runs the complete owner journey against the locally running fixture API
(:18099) and web app (:8090):

  home -> search (Cyrillic + Latin) -> verified comparison -> add to basket
  -> optimize -> server-computed totals.

Verifies desktop (1280x900) and a true mobile viewport (390x844 device
emulation), captures screenshots and fails on console/page errors.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8090"
OUT = Path("docs/milestones")
if not OUT.exists():
    OUT = Path(__file__).resolve().parents[2] / "docs" / "milestones"

errors: list[str] = []


def watch(page):
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
        if msg.type == "error"
        else None,
    )


def run_desktop(context):
    page = context.new_page()
    watch(page)

    page.goto(BASE + "/")
    assert page.locator("h1").first.inner_text().startswith("Најдете каде е најевтино")
    assert page.locator("#freshness-title").count() == 1

    # Cyrillic search -> real offer rendered server-side
    page.fill("#home-q", "млеко")
    page.click(".search-form button")
    page.wait_for_url("**/search**")
    assert "Резултати за „млеко“" in page.locator("h1").inner_text()
    assert page.locator(".offer article").count() == 1
    assert "75,00 ден." in page.locator(".offer .price").inner_text()
    page.screenshot(path=str(OUT / "m14-screenshot-search.png"))

    # Latin input is transliterated (note shown, same results)
    page.goto(BASE + "/search?q=mleko")
    assert "пресловено" in page.locator(".note").inner_text()
    assert page.locator(".offer article").count() == 1

    # Add to basket from search
    page.click(".offer .btn-add")
    assert page.locator("#basket-count").inner_text() == "1"

    # Verified comparison + detail deep link
    page.goto(BASE + "/compare")
    assert page.locator(".compare-group").count() == 1
    page.click(".compare-group h2 a")
    page.wait_for_url("**/compare/10")
    assert page.locator(".compare-table tbody tr").count() == 2
    page.click(".compare-table .btn-add")
    # Same canonical product as the search add -> merged into one line (quantity 2).
    assert page.locator("#basket-count").inner_text() == "1"
    page.screenshot(path=str(OUT / "m14-screenshot-compare-detail.png"))

    # Basket: merged row has quantity 2; optimize; assert SERVER totals only
    page.goto(BASE + "/basket")
    assert page.locator(".basket-row").count() == 1
    assert page.locator(".basket-row input[type=number]").input_value() == "2"
    with page.expect_request(lambda r: "/basket/optimize" in r.url) as request_info:
        page.click("#basket-optimize")
    sent = request_info.value.post_data_json
    assert sent["items"][0]["quantity"] == 2  # browser relays, never converts
    page.wait_for_selector(".result-card")
    best = page.locator(".result-card >> nth=0").inner_text()
    assert "ВЕРО 1" in best
    assert "75,00 ден." in best  # canned server response rendered verbatim
    assert "Најдобра единствена продавница" in best
    page.screenshot(path=str(OUT / "m14-screenshot-basket-results.png"))
    print("desktop journey: OK")


def run_mobile(context):
    page = context.new_page()
    watch(page)
    page.goto(BASE + "/search?q=млеко")
    assert page.locator(".offer article").count() == 1
    assert page.locator("#basket-count").is_visible()
    page.screenshot(path=str(OUT / "m14-screenshot-search-mobile.png"))

    page.goto(BASE + "/")
    page.screenshot(path=str(OUT / "m14-screenshot-home-mobile.png"))
    print("mobile journey: OK")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            desktop = browser.new_context(viewport={"width": 1280, "height": 900})
            run_desktop(desktop)
            desktop.close()

            mobile = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=2,
                is_mobile=True,
                has_touch=True,
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36"
                ),
            )
            run_mobile(mobile)
            mobile.close()
        finally:
            browser.close()

    if errors:
        print("BROWSER ERRORS:")
        for e in errors:
            print(" -", e)
        return 1
    print("browser smoke: PASS (no console or page errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
