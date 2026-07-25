"""
Chordbook — Real Song Test (corrected)

Writes to the RIGHT fields:
- block-name INPUT for "Verso 1" etc.
- contenteditable .line-text for actual lyric
- clicks inside .line-text to place chords
"""
import os, sys, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8104"
SHOTS = "/root/chordbook/screenshots"
os.makedirs(SHOTS, exist_ok=True)

passed = 0
failures = []
def check(cond, name, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failures.append((name, detail))
        print(f"  ✗ FAIL: {name}  {detail}")

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    # Create new song
    print("\n=== Create song ===")
    page.goto(f"{BASE}/new", wait_until="networkidle")
    page.locator("#song-title").fill("La Balsa")
    page.locator("#song-artist").fill("Los Gatos")
    page.locator("#song-key").select_option("E")
    page.wait_for_url("**/song/**", timeout=5000)
    song_id = page.url.rstrip("/").split("/")[-1]
    check(song_id.isdigit(), f"song_id={song_id}")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/real2_editor_empty.png", full_page=True)

    # Find the contenteditable
    print("\n=== Inspect line structure ===")
    line_text_els = page.locator(".line-text[contenteditable='true']")
    print(f"  → contenteditable .line-text count: {line_text_els.count()}")
    check(line_text_els.count() >= 1, "at least one .line-text contenteditable exists")

    chord_line_els = page.locator(".line-chords")
    print(f"  → .line-chords count: {chord_line_els.count()}")

    # Add lyric to first line
    print("\n=== Type lyric into first .line-text ===")
    first_line = line_text_els.first
    first_line.click()
    first_line.type("Si alguien canta algo", delay=10)
    page.wait_for_timeout(1500)  # autosave
    page.screenshot(path=f"{SHOTS}/real3_lyric_typed.png", full_page=True)

    # Verify it saved
    db_state = page.evaluate("() => SONG.content.blocks[0].lines[0].text")
    print(f"  → SONG.content.blocks[0].lines[0].text = {db_state!r}")
    check(db_state == "Si alguien canta algo", f"text saved correctly ({db_state!r})")

    # Click to place a chord above "alguien" (around char 3)
    print("\n=== Click to place chord ===")
    # Position cursor at "alguien" — click after "Si " (3 chars in)
    first_line.evaluate("""(el) => {
      const range = document.createRange();
      const textNode = el.firstChild;
      range.setStart(textNode, 3);
      range.collapse(true);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }""")
    # Now we need to actually click at that position to trigger the chord popup
    # The chord input opens on click within .line-text
    # Get bounding rect of the character position
    char_rect = first_line.evaluate("""(el) => {
      const range = document.createRange();
      const textNode = el.firstChild;
      range.setStart(textNode, 3);
      range.setEnd(textNode, 4);
      const rect = range.getBoundingClientRect();
      return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
    }""")
    print(f"  → char position rect: {char_rect}")
    page.mouse.click(char_rect["x"], char_rect["y"])
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/real4_chord_popup.png", full_page=True)

    # Check if popup opened
    popup_visible = page.evaluate("""() => {
      const p = document.getElementById('chord-input-popup');
      return p && p.style.display !== 'none';
    }""")
    check(popup_visible, "chord input popup opened on click")

    if popup_visible:
        # Type chord symbol
        page.locator("#chord-input-field").fill("Em")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)  # autosave
        page.screenshot(path=f"{SHOTS}/real5_chord_placed.png", full_page=True)

        # Verify in SONG
        chord_data = page.evaluate("""() => SONG.content.blocks[0].lines[0].chords""")
        print(f"  → chords after placing: {chord_data}")
        check(len(chord_data) == 1 and chord_data[0]["symbol"] == "Em",
              f"chord 'Em' saved at correct position ({chord_data})")
        check(chord_data[0]["position"] == 3,
              f"chord positioned at char 3 ({chord_data[0].get('position')})")

    # Add another chord (place at position 11 over "can-ta")
    print("\n=== Place second chord ===")
    first_line.evaluate("""(el) => {
      const range = document.createRange();
      const textNode = el.firstChild;
      range.setStart(textNode, 11);
      range.collapse(true);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }""")
    char_rect2 = first_line.evaluate("""(el) => {
      const range = document.createRange();
      const textNode = el.firstChild;
      range.setStart(textNode, 11);
      range.setEnd(textNode, 12);
      const rect = range.getBoundingClientRect();
      return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
    }""")
    page.mouse.click(char_rect2["x"], char_rect2["y"])
    page.wait_for_timeout(500)
    popup_visible2 = page.evaluate("""() => {
      const p = document.getElementById('chord-input-popup');
      return p && p.style.display !== 'none';
    }""")
    if popup_visible2:
        page.locator("#chord-input-field").fill("A")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        chords2 = page.evaluate("() => SONG.content.blocks[0].lines[0].chords")
        print(f"  → chords after second: {chords2}")
        check(len(chords2) == 2, "two chords placed")

    # Add second line via the addLine button (more reliable than keyboard)
    print("\n=== Add new line via + Agregar línea button ===")
    add_line_btns = page.locator('button:has-text("Agregar línea")')
    print(f"  → add-line buttons: {add_line_btns.count()}")
    if add_line_btns.count() > 0:
        add_line_btns.first.click()
        page.wait_for_timeout(500)
        new_lines = page.locator(".line-text[contenteditable='true']")
        print(f"  → line-text after add: {new_lines.count()}")
        if new_lines.count() >= 2:
            new_lines.nth(1).click()
            new_lines.nth(1).type("alguien es porque vienen los aviones", delay=10)
            page.wait_for_timeout(1500)

    # Add a Coro block
    print("\n=== Add Coro block ===")
    page.locator('button.btn-section[data-type="chorus"]').click()
    page.wait_for_timeout(500)
    new_blocks_count = page.locator(".block").count()
    print(f"  → blocks after adding Coro: {new_blocks_count}")
    check(new_blocks_count >= 2, f"Coro block added ({new_blocks_count} blocks)")

    # Type into coro's first line
    all_lines = page.locator(".line-text[contenteditable='true']")
    if all_lines.count() > 0:
        coro_line = all_lines.last
        coro_line.click()
        coro_line.type("Llegan cuando se van")
        page.wait_for_timeout(1500)

    page.screenshot(path=f"{SHOTS}/real6_full_song.png", full_page=True)

    # Preview the song
    print("\n=== Preview the song ===")
    page.locator("#btn-preview").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    # Hard refresh to bypass cache
    page.goto(page.url, wait_until="networkidle")
    page.screenshot(path=f"{SHOTS}/real7_preview.png", full_page=True)

    preview_html = page.content()
    check("Si alguien canta algo" in preview_html, "preview shows full lyric")
    check("alguien es porque vienen los aviones" in preview_html, "preview shows second line")
    check("Llegan cuando se van" in preview_html, "preview shows coro lyric")
    check("Em" in preview_html, "preview shows chord Em")
    check("A" in preview_html, "preview shows chord A")

    # Check the chord line is positioned ABOVE the lyric
    # In preview.html, .chord-line should contain "Em" before "Si"
    chord_section = page.locator(".preview-chord-row").first.text_content()
    print(f"  → first chord line content: {chord_section!r}")
    check(chord_section and "Em" in chord_section, "chord Em in chord line")

    # PDF
    print("\n=== Export PDF ===")
    pdf_resp = page.request.get(f"{BASE}/api/songs/{song_id}/pdf")
    check(pdf_resp.status == 200, f"PDF HTTP 200")
    pdf_bytes = pdf_resp.body()
    pdf_path = f"{SHOTS}/real8_song_{song_id}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    check(pdf_bytes[:4] == b"%PDF", "PDF magic bytes")
    check(len(pdf_bytes) > 3000, f"PDF size {len(pdf_bytes)} bytes")

    # Render PDF to image
    import subprocess
    subprocess.run(["pdftoppm", "-png", "-r", "150", pdf_path, f"{SHOTS}/real8_pdf"],
                   capture_output=True)

    # Console errors
    check(len(errors) == 0, f"no JS errors ({len(errors)})", str(errors[:3]))

    browser.close()

print(f"\n=== SUMMARY ===")
print(f"Passed: {passed}")
print(f"Failed: {len(failures)}")
for n, d in failures:
    print(f"  - {n}: {d}")
sys.exit(1 if failures else 0)
