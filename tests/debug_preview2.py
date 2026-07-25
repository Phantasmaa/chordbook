"""Debug what's in the preview page after navigating there."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 900})

    page.goto("http://127.0.0.1:8104/", wait_until="networkidle")
    page.locator('a.nav-btn').click()
    page.wait_for_url("**/new")
    page.locator("#song-title").fill("Debug")
    page.wait_for_url("**/song/**")
    page.wait_for_timeout(2000)

    # Find lyric and type
    first_line = page.locator(".line-text[contenteditable='true']").first
    first_line.click()
    first_line.type("Hola mundo", delay=10)
    page.wait_for_timeout(1500)

    # Click in middle of "mundo" (5)
    char_rect = first_line.evaluate("""(el) => {
      const range = document.createRange();
      const tn = el.firstChild;
      range.setStart(tn, 5);
      range.setEnd(tn, 6);
      const r = range.getBoundingClientRect();
      return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")
    page.mouse.click(char_rect['x'], char_rect['y'])
    page.wait_for_timeout(500)
    page.locator('#chord-input-field').fill('C')
    page.keyboard.press('Enter')
    page.wait_for_timeout(2000)

    # Navigate to preview
    page.locator('#btn-preview').click()
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    # Hard reload
    page.goto(page.url, wait_until='networkidle')

    # Inspect
    print("URL:", page.url)
    print("title:", page.title())
    html = page.content()
    print(f"HTML length: {len(html)}")
    print(f"contains 'Hola mundo': {'Hola mundo' in html}")
    print(f"contains 'preview-chord-row': {'preview-chord-row' in html}")
    print(f"contains 'preview-text-row': {'preview-text-row' in html}")
    print(f"contains 'preview-line': {'preview-line' in html}")
    print(f"contains 'preview-block': {'preview-block' in html}")

    # Count
    print(f"preview-chord-row count: {page.locator('.preview-chord-row').count()}")
    print(f"preview-text-row count: {page.locator('.preview-text-row').count()}")
    print(f".line count: {page.locator('.preview-line').count()}")

    # Show what's in preview-content
    pc = page.locator('.preview-content').first
    if pc.count() > 0:
        print(f"\npreview-content innerHTML (first 1000):")
        print(pc.inner_html()[:1000])

    browser.close()
