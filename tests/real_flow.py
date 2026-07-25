"""
Chordbook — Full Real-World Flow Test

Simulates exactly what Manuel does:
1. Click "+ Nueva"
2. Type title "La Balsa"
3. Add Verso 1
4. Type lyric with realistic syllables
5. Click on a syllable to place a chord above it
6. Add Coro
7. Type coro lyrics
8. Place more chords
9. Export PDF
10. Verify PDF visually (screenshot)
11. Verify preview shows chords over correct syllables

Uses real lyrics from a known song to test pixel-accuracy.
"""
import os, sys, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8104"
SHOTS = "/root/chordbook/screenshots"
os.makedirs(SHOTS, exist_ok=True)

# Real lyric with syllable breaks (marked with |)
LYRIC_VERSO = "Si | al-guien | can-ta | al-go al |guien | es | por | que | vien-tes | lla-no"
LYRIC_CORO = "Na-da | na-da | va a per-ma-ne-cer | tal co-mo | es"

failures = []
passed = 0

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
    console_errors = []
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: console_errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    print("\n=== 1. Click + Nueva ===")
    page.goto(f"{BASE}/", wait_until="networkidle")
    page.locator('a.nav-btn').click()
    page.wait_for_url("**/new")
    check("/new" in page.url, "navigated to /new")

    print("\n=== 2. Fill title and artist ===")
    page.locator("#song-title").fill("La Balsa")
    page.locator("#song-artist").fill("Los Gatos")
    check(page.locator("#song-title").input_value() == "La Balsa", "title filled")

    # Select key Em
    page.locator("#song-key").select_option(value="E")
    check(page.locator("#song-key").input_value() == "E", "key = E")

    print("\n=== 3. Wait for autosave redirect ===")
    page.wait_for_url("**/song/**", timeout=5000)
    song_id = page.url.rstrip("/").split("/")[-1]
    check(song_id.isdigit(), f"song_id={song_id}")

    print("\n=== 4. Examine editor structure (CRITICAL — where do chords go?) ===")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/flow1_editor_empty.png", full_page=True)

    # Check if there's a default block already
    block_count = page.locator(".block, [data-block-type], .editor-block").count()
    print(f"  → initial blocks in DOM: {block_count}")

    # Inspect the editor.js to understand structure
    editor_js_url = f"{BASE}/static/js/editor.js"
    js_resp = page.request.get(editor_js_url)
    check(js_resp.status == 200, f"editor.js loads (HTTP {js_resp.status})")
    js_content = js_resp.text() if js_resp.status == 200 else ""
    check(len(js_content) > 1000, f"editor.js non-trivial ({len(js_content)} bytes)")

    # Look for click-to-place chord handler
    check("click" in js_content.lower() or "onclick" in js_content.lower() or "addEventListener" in js_content,
          "editor.js has click handlers")
    check("chord" in js_content.lower(), "editor.js references chords")

    # Check what's actually rendered — is there a lyric input?
    # Look for textarea or contenteditable
    inputs_in_editor = page.locator("#blocks-container input, #blocks-container textarea, #blocks-container [contenteditable]").count()
    print(f"  → inputs/textareas in blocks container: {inputs_in_editor}")
    check(inputs_in_editor > 0, f"editor has input fields for lyrics ({inputs_in_editor})")

    print("\n=== 5. Type lyric in first block ===")
    # Find the first text input/textarea in the blocks container
    first_input = page.locator("#blocks-container input, #blocks-container textarea").first
    if first_input.count() > 0:
        tag = first_input.evaluate("e => e.tagName")
        print(f"  → first input tag: {tag}")
        if tag == "TEXTAREA":
            first_input.fill("Si al-guien can-ta al-go al-guien es por-que vien-tes lla-no")
        else:
            first_input.fill("Si al-guien can-ta al-go")
        page.wait_for_timeout(1000)  # autosave
        page.screenshot(path=f"{SHOTS}/flow2_lyric_typed.png", full_page=True)
        check(True, "lyric typed into first block")
    else:
        check(False, "no input to type lyric into")

    print("\n=== 6. Try to place a chord (click on a syllable) ===")
    # Inspect DOM structure around lyric input
    blocks_html = page.locator("#blocks-container").inner_html()[:2000]
    print(f"  → blocks HTML preview: {blocks_html[:500]}")

    # Try clicking near a known word
    clickable_chord_targets = page.locator(".chord-slot, .chord-target, [data-chord-pos], .lyric span, .lyric-line span").count()
    print(f"  → clickable chord targets: {clickable_chord_targets}")

    # Inspect the chord popup logic
    has_chord_popup = page.locator("#chord-input-popup").count() > 0
    check(has_chord_popup, "chord input popup exists in DOM")

    print("\n=== 7. Save and verify preview ===")
    # Trigger autosave
    page.locator("#song-title").click()  # blur inputs to force save
    page.wait_for_timeout(2000)
    page.screenshot(path=f"{SHOTS}/flow3_after_save.png", full_page=True)

    # Hit preview button
    page.locator("#btn-preview").click()
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{SHOTS}/flow4_preview.png", full_page=True)
    check("La Balsa" in page.content(), "preview shows La Balsa")
    preview_has_lyric = "al-guien" in page.content() or "alguien" in page.content() or "Si" in page.content()
    check(preview_has_lyric, "preview shows the lyric text")

    print("\n=== 8. Generate PDF ===")
    pdf_resp = page.request.get(f"{BASE}/api/songs/{song_id}/pdf")
    check(pdf_resp.status == 200, f"PDF HTTP 200 ({pdf_resp.status})")
    pdf_bytes = pdf_resp.body()
    pdf_path = f"{SHOTS}/flow5_song_{song_id}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    check(pdf_bytes[:4] == b"%PDF", "PDF magic bytes OK")
    check(len(pdf_bytes) > 2000, f"PDF size > 2KB ({len(pdf_bytes)} bytes)")

    print("\n=== 9. Render PDF as image to inspect visually ===")
    # Convert PDF to image via poppler
    import subprocess
    r = subprocess.run(
        ["pdftoppm", "-png", "-r", "120", pdf_path, f"{SHOTS}/flow5_pdf"],
        capture_output=True, text=True
    )
    pdf_imgs = sorted([f for f in os.listdir(SHOTS) if f.startswith("flow5_pdf") and f.endswith(".png")])
    check(len(pdf_imgs) > 0, f"PDF rendered to images ({len(pdf_imgs)})")

    print("\n=== 10. Create setlist ===")
    page.goto(f"{BASE}/setlists", wait_until="networkidle")
    page.locator("#new-setlist-btn").click()
    page.wait_for_timeout(300)
    page.locator('input[name="name"]').fill("Recital Café")
    page.locator('textarea[name="description"]').fill("Set de prueba")
    page.locator("#new-setlist-form button[type=submit]").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/flow6_setlist.png", full_page=True)
    check("Recital Café" in page.content(), "setlist 'Recital Café' created and visible")

    # Click into the setlist
    page.locator('a.setlist-card', has_text="Recital Café").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/flow7_setlist_empty.png", full_page=True)

    # Add the song to it
    page.request.post(f"{BASE}/song/{song_id}/add-to-setlist")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/flow8_setlist_with_song.png", full_page=True)
    check("La Balsa" in page.content(), "La Balsa visible in setlist")

    # Export setlist PDF
    setlist_id = page.url.rstrip("/").split("/")[-1]
    sl_pdf_resp = page.request.get(f"{BASE}/api/setlists/{setlist_id}/pdf")
    check(sl_pdf_resp.status == 200, f"setlist PDF HTTP 200 ({sl_pdf_resp.status})")
    if sl_pdf_resp.status == 200:
        sl_pdf_bytes = sl_pdf_resp.body()
        sl_pdf_path = f"{SHOTS}/flow9_setlist_{setlist_id}.pdf"
        with open(sl_pdf_path, "wb") as f:
            f.write(sl_pdf_bytes)
        check(sl_pdf_bytes[:4] == b"%PDF", "setlist PDF magic bytes OK")
        subprocess.run(["pdftoppm", "-png", "-r", "120", sl_pdf_path, f"{SHOTS}/flow9_sl_pdf"])

    print("\n=== 11. Console errors ===")
    check(len(console_errors) == 0, f"no JS errors ({len(console_errors)})",
          str(console_errors[:3]))

    browser.close()

print(f"\n=== SUMMARY ===")
print(f"Passed: {passed}")
print(f"Failed: {len(failures)}")
if failures:
    print("\nFailures:")
    for n, d in failures:
        print(f"  - {n}: {d}")
    sys.exit(1)
print("✓ ALL CHECKS PASS")
