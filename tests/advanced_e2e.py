"""
Chordbook — Advanced Test Suite
- 3 viewports (mobile/tablet/desktop)
- Estilos computados (background oscuro, button visible, sin errores CSS)
- Flujo CRUD + setlist + PDF
- Screenshots de evidencia
"""
import sys, json, os, subprocess, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8104"
SHOTS = "/root/chordbook/screenshots"
os.makedirs(SHOTS, exist_ok=True)

VIEWPORTS = [
    ("mobile",  390, 844),
    ("tablet",  768, 1024),
    ("desktop", 1280, 800),
]

failures = []
checks_passed = 0

def assert_(cond, name, details=""):
    global checks_passed
    if cond:
        checks_passed += 1
        print(f"  ✓ {name}")
    else:
        failures.append((name, details))
        print(f"  ✗ FAIL: {name}  {details}")

with sync_playwright() as p:
    browser = p.chromium.launch()
    for vname, w, h in VIEWPORTS:
        print(f"\n=== {vname} ({w}x{h}) ===")
        ctx = browser.new_context(viewport={"width": w, "height": h})
        page = ctx.new_page()
        errors = []
        failed_requests = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("response", lambda r: failed_requests.append((r.status, r.url)) if r.status >= 400 else None)

        # 1) Index
        page.goto(f"{BASE}/", wait_until="networkidle")
        page.screenshot(path=f"{SHOTS}/v2_index_{vname}.png", full_page=True)

        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        text = page.evaluate("getComputedStyle(document.body).color")
        # Dark bg should be rgb(14, 14, 16) (#0e0e10)
        assert_(bg in ["rgb(14, 14, 16)", "rgb(15, 15, 17)"], f"body bg is dark ({bg})")
        assert_(text != "rgb(0, 0, 0)" and "239" not in text[:5], f"text not pure black ({text})")

        # Topnav "+ Nueva" button visible
        new_btn = page.locator('a.nav-btn', has_text="Nueva")
        assert_(new_btn.count() == 1, f"'+ Nueva' button exists")
        assert_(new_btn.first.is_visible(), f"'+ Nueva' button visible on {vname}")

        # 2) Click + Nueva → editor (no 500, no template error)
        new_btn.first.click()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{SHOTS}/v2_new_{vname}.png", full_page=True)
        url = page.url
        assert_(url.endswith("/new"), f"navigated to /new (url={url})")
        title_input = page.locator("#song-title")
        assert_(title_input.count() == 1, "title input exists")
        assert_(title_input.first.is_visible(), "title input visible")
        # no 500 error in title
        assert_("Internal Server Error" not in page.content(), "no 500 error on /new")

        # 3) Type a title and save
        title_input.first.fill("La Balsa - Smoke Test")
        artist_input = page.locator("#song-artist")
        artist_input.first.fill("Los Gatos")
        # The editor auto-saves via debounce
        page.wait_for_timeout(1500)  # wait for autosave + redirect
        page.screenshot(path=f"{SHOTS}/v2_editor_saved_{vname}.png", full_page=True)
        # After save, URL should be /song/<id>
        assert_(("/song/" in page.url) and ("/new" not in page.url),
                f"redirected to /song/<id> after save (url={page.url})")

        song_id = page.url.rstrip("/").split("/")[-1]
        assert_(song_id.isdigit(), f"valid song_id={song_id}")

        # 4) Add a block with lyric
        add_verso = page.locator('button.btn-section[data-type="verse"]')
        if add_verso.count() == 0:
            add_verso = page.locator('button', has_text="Verso")
        assert_(add_verso.count() >= 1, "'+ Verso' button exists in editor")

        # 5) Preview page
        page.goto(f"{BASE}/song/{song_id}/preview", wait_until="networkidle")
        page.screenshot(path=f"{SHOTS}/v2_preview_{vname}.png", full_page=True)
        assert_("La Balsa" in page.content() or "Smoke" in page.content(),
                "preview shows the saved title")

        # 6) PDF endpoint
        pdf_resp = page.request.get(f"{BASE}/api/songs/{song_id}/pdf")
        assert_(pdf_resp.status == 200, f"PDF HTTP 200 ({pdf_resp.status})")
        assert_(pdf_resp.headers.get("content-type", "").startswith("application/pdf"),
                f"PDF content-type correct ({pdf_resp.headers.get('content-type')})")
        pdf_bytes = pdf_resp.body()
        assert_(len(pdf_bytes) > 1000, f"PDF size > 1KB ({len(pdf_bytes)} bytes)")
        assert_(pdf_bytes[:4] == b"%PDF", f"PDF magic bytes OK")

        # 7) Setlists page (CRITICAL — was 500 before)
        page.goto(f"{BASE}/setlists", wait_until="networkidle")
        page.screenshot(path=f"{SHOTS}/v2_setlists_{vname}.png", full_page=True)
        assert_("Internal Server Error" not in page.content(),
                f"setlists page no 500 error")
        # Should have '+ Nuevo setlist' button
        new_sl_btn = page.locator("#new-setlist-btn")
        assert_(new_sl_btn.count() == 1, "'+ Nuevo setlist' button exists")
        assert_(new_sl_btn.first.is_visible(), "'+ Nuevo setlist' button visible")

        # 8) Create a setlist via modal
        new_sl_btn.first.click()
        page.wait_for_timeout(300)
        modal = page.locator("#new-setlist-modal")
        assert_(not "hidden" in (modal.first.get_attribute("class") or ""),
                "modal opens on click")
        page.locator('input[name="name"]').first.fill("Recital de prueba")
        page.locator('textarea[name="description"]').first.fill("Test E2E")
        page.locator("#new-setlist-form button[type=submit]").click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SHOTS}/v2_setlist_created_{vname}.png", full_page=True)
        # Should now show the setlist card
        assert_("Recital de prueba" in page.content(),
                "setlist card visible after creation")

        # 9) Open the setlist and add a song to it
        sl_card = page.locator('a.setlist-card', has_text="Recital de prueba")
        if sl_card.count() == 0:
            sl_card = page.locator('a', has_text="Recital de prueba")
        assert_(sl_card.count() >= 1, "setlist card link found")
        sl_card.first.click()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{SHOTS}/v2_setlist_view_{vname}.png", full_page=True)
        # Use API directly to add song to setlist (more reliable than UI)
        setlist_id = page.url.rstrip("/").split("/")[-1]
        add_resp = page.request.post(
            f"{BASE}/song/{song_id}/add-to-setlist",
            form={"setlist_id": setlist_id}
        )
        assert_(add_resp.status in [200, 302], f"add-to-setlist returned {add_resp.status}")
        page.reload(wait_until="networkidle")
        page.screenshot(path=f"{SHOTS}/v2_setlist_with_song_{vname}.png", full_page=True)
        assert_("La Balsa" in page.content(), "song appears in setlist after add")

        # 10) Delete song from setlist
        remove_btn = page.locator('form.delete-form button')
        if remove_btn.count() > 0:
            remove_btn.first.click()
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"{SHOTS}/v2_setlist_after_remove_{vname}.png", full_page=True)

        # 11) Page-level errors
        assert_(len(errors) == 0, f"no JS errors ({len(errors)} errors)",
                str(errors[:3]) + " | failed_requests: " + str(failed_requests[:5]))

        ctx.close()

    browser.close()

# Summary
print(f"\n=== SUMMARY ===")
print(f"Passed: {checks_passed}")
print(f"Failed: {len(failures)}")
if failures:
    print("\nFailures:")
    for name, details in failures:
        print(f"  - {name}: {details}")
    sys.exit(1)
else:
    print("\n✓ ALL CHECKS PASS")
    sys.exit(0)
