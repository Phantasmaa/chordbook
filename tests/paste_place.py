"""
Chordbook — Paste-and-Place Test (mobile-first workflow)

Simulates Manuel's actual workflow:
1. Open editor (mobile viewport)
2. Click "📋 Pegar letra" button
3. Modal opens → textarea
4. Paste multi-line lyrics
5. Verify "X líneas detectadas" counter updates
6. Click "Pegar y separar"
7. Verify each line of lyrics became a line in the block
8. Click on a syllable to place chord
9. Verify chord popup shows categorized suggestions
10. Tap a suggestion → chord placed
11. Verify preview shows everything correctly
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

# Realistic lyric from "La Balsa" by Los Gatos (Argentine classic)
FULL_LYRIC_VERSO = """Si alguien canta algo es porque tiene algo que decir
O porque tiene algo que vender
O porque le sobra el corazon
O porque le faltan palabras para tanto dolor"""

FULL_LYRIC_CORO = """Llegan cuando se van
Se van cuando llegan
Asi es la vida"""

# Test on mobile viewport (Android)
VIEWPORTS = [
    ("mobile",  390, 844),
    ("desktop", 1280, 800),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    for vname, w, h in VIEWPORTS:
        print(f"\n========== {vname.upper()} ({w}x{h}) ==========")
        ctx = browser.new_context(viewport={"width": w, "height": h})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        # 1. Create song
        page.goto(f"{BASE}/new", wait_until="networkidle")
        page.locator("#song-title").fill("La Balsa")
        page.locator("#song-artist").fill("Los Gatos")
        page.locator("#song-key").select_option("E")
        page.wait_for_url("**/song/**", timeout=8000)
        song_id = page.url.rstrip("/").split("/")[-1]
        check(song_id.isdigit(), f"song_id={song_id}")
        page.wait_for_timeout(800)
        page.screenshot(path=f"{SHOTS}/paste1_editor_{vname}.png", full_page=True)

        # 2. Find and click "📋 Pegar letra" button
        print("\n=== Click 'Pegar letra' ===")
        paste_btn = page.locator('.paste-lyrics-btn').first
        check(paste_btn.count() >= 1, f"'Pegar letra' button exists")
        check(paste_btn.first.is_visible(), f"'Pegar letra' button visible on {vname}")
        paste_btn.first.click()
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SHOTS}/paste2_modal_{vname}.png", full_page=True)

        # 3. Modal opens
        modal = page.locator('#paste-modal-overlay')
        check(modal.count() == 1, "paste modal opens")
        textarea = modal.locator('#paste-textarea')
        check(textarea.count() == 1, "modal has textarea")
        check(textarea.first.is_visible(), "textarea visible")

        # 4. Paste lyrics (simulate)
        textarea.first.fill(FULL_LYRIC_VERSO)
        page.wait_for_timeout(300)

        # 5. Counter shows correct line count
        line_count_text = modal.locator('#paste-line-count').text_content()
        print(f"  → detected lines: {line_count_text}")
        expected_lines = len([l for l in FULL_LYRIC_VERSO.split('\n') if l.strip()])
        check(line_count_text == str(expected_lines),
              f"counter shows {expected_lines} lines (got {line_count_text})")

        # 6. Confirm button shows correct text
        confirm_btn = modal.locator('.paste-confirm')
        confirm_text = confirm_btn.text_content()
        print(f"  → confirm text: {confirm_text}")
        check(f"{expected_lines} líneas" in confirm_text,
              f"confirm button text shows line count ({confirm_text})")

        page.screenshot(path=f"{SHOTS}/paste3_textarea_filled_{vname}.png", full_page=True)

        # 7. Click confirm
        confirm_btn.click()
        page.wait_for_timeout(800)
        check(modal.count() == 0, "modal closes after confirm")
        page.screenshot(path=f"{SHOTS}/paste4_after_paste_{vname}.png", full_page=True)

        # 8. Each lyric line is now a line in the editor
        line_texts = page.evaluate("() => SONG.content.blocks[0].lines.map(l => l.text)")
        print(f"  → lines in block: {line_texts}")
        check(len(line_texts) == expected_lines,
              f"block has {expected_lines} lines (got {len(line_texts)})")
        check(line_texts[0] == "Si alguien canta algo es porque tiene algo que decir",
              "first lyric line correct")
        check(line_texts[-1] == "O porque le faltan palabras para tanto dolor",
              "last lyric line correct")

        # 9. Test paste WITHOUT newlines (should auto-split by punctuation/length)
        print("\n=== Test paste without newlines ===")
        paste_btn = page.locator('.paste-lyrics-btn').first
        paste_btn.click()
        page.wait_for_timeout(400)
        modal = page.locator('#paste-modal-overlay')
        no_newline_text = "Primera linea de prueba. Segunda linea de prueba. Tercera linea de prueba. Cuarta linea de prueba. Quinta linea de prueba"
        modal.locator('#paste-textarea').fill(no_newline_text)
        page.wait_for_timeout(300)
        nl_count = modal.locator('#paste-line-count').text_content()
        print(f"  → detected from no-newlines: {nl_count}")
        check(int(nl_count) >= 3, f"split by punctuation works (got {nl_count})")

        # 10. Clear button
        modal.locator('.paste-clear').click()
        page.wait_for_timeout(200)
        check(modal.locator('#paste-textarea').input_value() == "",
              "clear button empties textarea")
        # Cancel
        modal.locator('.modal-cancel').click()
        page.wait_for_timeout(300)
        check(page.locator('#paste-modal-overlay').count() == 0,
              "modal closes on cancel")

        # 11. Test inline paste (Ctrl+V in a line) with multi-line text
        print("\n=== Test inline Ctrl+V paste ===")
        # Reset song to clean state
        page.evaluate("() => { SONG.content.blocks[0].lines = [{chords: [], text: ''}]; render(); }")
        page.wait_for_timeout(300)
        first_line = page.locator(".line-text[contenteditable='true']").first
        first_line.click()
        # Simulate paste event
        page.evaluate("""(lyrics) => {
          const dt = new DataTransfer();
          dt.setData('text/plain', lyrics);
          const el = document.querySelector('.line-text[contenteditable=true]');
          const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
          el.dispatchEvent(ev);
        }""", FULL_LYRIC_CORO)
        page.wait_for_timeout(800)
        coro_lines = page.evaluate("() => SONG.content.blocks[0].lines.map(l => l.text)")
        print(f"  → after inline paste: {coro_lines}")
        check(len(coro_lines) >= 3, f"inline paste split multi-line ({len(coro_lines)} lines)")

        # 12. Click on a syllable to place chord
        print("\n=== Click to place chord ===")
        first_line = page.locator(".line-text[contenteditable='true']").first
        first_line.click()
        first_line.type("Llegan cuando se van", delay=5)
        page.wait_for_timeout(1500)

        # Click on position 0 (start of line)
        rect = first_line.evaluate("""(el) => {
          const range = document.createRange();
          const tn = el.firstChild;
          range.setStart(tn, 0);
          range.setEnd(tn, 1);
          const r = range.getBoundingClientRect();
          return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""")
        page.mouse.click(rect['x'], rect['y'])
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SHOTS}/paste5_chord_popup_{vname}.png", full_page=True)

        popup = page.locator('#chord-input-popup')
        check(popup.count() == 1 and popup.first.is_visible(),
              "chord popup opens on click")
        check(popup.locator('.chord-group-label').count() >= 4,
              f"popup has grouped suggestions (got {popup.locator('.chord-group-label').count()} groups)")

        # 13. Tap a suggestion (Am — menores)
        am_btn = popup.locator('button[data-chord="Am"]')
        check(am_btn.count() == 1, "Am button in popup")
        am_btn.first.click()
        page.wait_for_timeout(1500)
        chords = page.evaluate("() => SONG.content.blocks[0].lines[0].chords")
        print(f"  → chords after tap: {chords}")
        check(len(chords) == 1 and chords[0]['symbol'] == 'Am',
              f"Am chord placed by tapping suggestion ({chords})")

        # 14. Type custom chord in field and confirm with ✓ button
        print("\n=== Type custom chord + confirm ===")
        first_line.click()
        # Click at end of "van"
        rect2 = first_line.evaluate("""(el) => {
          const range = document.createRange();
          const tn = el.firstChild;
          const len = tn.textContent.length;
          range.setStart(tn, len - 1);
          range.setEnd(tn, len);
          const r = range.getBoundingClientRect();
          return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""")
        page.mouse.click(rect2['x'], rect2['y'])
        page.wait_for_timeout(400)
        # Type chord
        page.locator('#chord-input-field').fill("E7")
        # Tap ✓ button instead of Enter
        page.locator('#chord-confirm-btn').click()
        page.wait_for_timeout(1500)
        chords2 = page.evaluate("() => SONG.content.blocks[0].lines[0].chords")
        print(f"  → chords after E7: {chords2}")
        check(any(c['symbol'] == 'E7' for c in chords2),
              f"E7 chord placed via ✓ button ({chords2})")

        # 15. Preview
        page.locator("#btn-preview").click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        page.goto(page.url, wait_until="networkidle")
        page.screenshot(path=f"{SHOTS}/paste6_preview_{vname}.png", full_page=True)
        preview_html = page.content()
        check("Llegan cuando se van" in preview_html, "preview shows lyric")
        check("Am" in preview_html, "preview shows Am chord")
        check("E7" in preview_html, "preview shows E7 chord")

        # 16. No JS errors
        check(len(errors) == 0, f"no JS errors ({len(errors)})",
              str(errors[:3]))

        ctx.close()
    browser.close()

print(f"\n=== SUMMARY ===")
print(f"Passed: {passed}")
print(f"Failed: {len(failures)}")
for n, d in failures:
    print(f"  - {n}: {d}")
sys.exit(1 if failures else 0)
