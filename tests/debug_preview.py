"""Debug: what does /preview actually render?"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8104"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # Use an existing song (id=24 was the latest test one)
    page.goto(f"{BASE}/song/24", wait_until="networkidle")
    page.screenshot(path="/root/chordbook/screenshots/debug_editor_24.png", full_page=True)

    # Check the song data
    song_data_json = page.locator("#song-data").text_content() or ""
    print(f"song-data length: {len(song_data_json)}")
    print(f"song-data first 800 chars: {song_data_json[:800]}")

    # Check actual page content for the lyric
    print(f"\n=== Editor page content (after lyric + chorus) ===")
    page_html = page.content()
    print(f"contains 'Si al-guien': {'Si al-guien' in page_html}")
    print(f"contains 'La Balsa': {'La Balsa' in page_html}")
    print(f"contains 'alguien': {'alguien' in page_html}")
    print(f"contains 'can-ta': {'can-ta' in page_html}")

    # Now go to preview
    page.goto(f"{BASE}/song/24/preview", wait_until="networkidle")
    page.screenshot(path="/root/chordbook/screenshots/debug_preview_24.png", full_page=True)

    preview_html = page.content()
    print(f"\n=== Preview page content ===")
    print(f"preview contains 'La Balsa': {'La Balsa' in preview_html}")
    print(f"preview contains 'alguien': {'alguien' in preview_html}")
    print(f"preview contains 'Verso': {'Verso' in preview_html}")
    print(f"preview contains 'PREVIEW': {'PREVIEW' in preview_html}")
    print(f"preview length: {len(preview_html)}")

    # Look at the body
    print("\n=== Preview body innerHTML ===")
    body = page.locator("body").inner_html()
    print(body[:2000])

    browser.close()
