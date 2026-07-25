"""Trace exactly what happens on btn-preview click."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 900})

    # Track all navigations
    nav_events = []
    page.on("framenavigated", lambda f: nav_events.append(f"NAV: {f.url}") if f == page.main_frame else None)
    page.on("response", lambda r: nav_events.append(f"RESP {r.status}: {r.url}") if "/preview" in r.url or "/song/" in r.url else None)

    page.goto("http://127.0.0.1:8104/", wait_until="networkidle")
    page.locator('a.nav-btn').click()
    page.wait_for_url("**/new")
    page.locator("#song-title").fill("Trace")
    page.wait_for_url("**/song/**", timeout=10000)
    song_id = page.url.rstrip("/").split("/")[-1]
    print(f"Created song {song_id}, current URL: {page.url}")
    page.wait_for_timeout(2000)

    # Type something
    first_line = page.locator(".line-text[contenteditable='true']").first
    first_line.click()
    first_line.type("Test", delay=10)
    page.wait_for_timeout(1500)

    # Verify SONG_ID is set
    song_id_in_js = page.evaluate("() => typeof SONG_ID !== 'undefined' ? SONG_ID : 'undefined'")
    print(f"SONG_ID in JS: {song_id_in_js}")
    nav_events.append(f"--- now clicking preview button ---")

    # Click preview button
    btn = page.locator('#btn-preview')
    print(f"btn-preview count: {btn.count()}")
    print(f"btn-preview visible: {btn.first.is_visible() if btn.count() else 'N/A'}")
    btn.first.click()
    page.wait_for_timeout(3000)

    print(f"URL after click: {page.url}")
    print(f"\n--- Navigation events ---")
    for e in nav_events[-15:]:
        print(f"  {e}")

    browser.close()
