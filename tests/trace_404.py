"""Rastrear 404 — escuchar TODOS los requests y reportar cuáles fallan."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = ctx.new_page()
    failures = []

    def on_response(resp):
        if resp.status >= 400:
            failures.append(f"{resp.status} {resp.url}")

    page.on("response", on_response)

    # Cargar todas las páginas
    for url in ["http://127.0.0.1:8104/", "http://127.0.0.1:8104/setlists",
                "http://127.0.0.1:8104/new", "http://127.0.0.1:8104/song/8"]:
        page.goto(url, wait_until="networkidle")

    print(f"Total failures: {len(failures)}")
    for f in failures:
        print(f"  {f}")

    browser.close()
