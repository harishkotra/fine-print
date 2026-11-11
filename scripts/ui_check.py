"""Drive the real UI in Chrome and capture what a person would see."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8078/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fp_ui.png"
CLICK = sys.argv[3] if len(sys.argv) > 3 else "A water bill whose total does not add up"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1600}, device_scale_factor=2)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="networkidle")
    page.get_by_role("button", name=CLICK, exact=False).first.click()
    page.wait_for_selector("text=The arithmetic", timeout=60000)
    page.wait_for_function(
        "() => document.body.innerText.includes('Do not pay') || document.body.innerText.includes('Safe to pay') || document.body.innerText.includes('Check it yourself')",
        timeout=60000,
    )
    page.wait_for_timeout(600)
    page.screenshot(path=OUT, full_page=True)
    body = page.inner_text("body")
    print("CONSOLE_ERRORS", errors)
    print("---- VISIBLE TEXT ----")
    print(body[:3000])
    browser.close()
