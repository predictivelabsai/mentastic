"""
Capture User Guide Screenshots

Launches a headless browser, registers/logs in, navigates key screens,
and saves screenshots to screenshots/.

Usage:
    # App must be running: python app.py
    python tests/capture_guide.py

    # Or start app automatically:
    python tests/capture_guide.py --start-app
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCREENSHOTS_DIR = ROOT / "screenshots"
BASE_URL = "http://localhost:5010"
EMAIL = "demo@mentastic.com"
PASSWORD = "demo1234"


async def wait_for_ws(page, timeout=10):
    """Wait for the chat form to load AND the WebSocket to connect."""
    for _ in range(timeout * 4):
        ready = await page.evaluate("""
            () => {
                var ta = document.getElementById('chat-input');
                var fm = document.getElementById('chat-form');
                // Check HTMX ws extension has connected
                var ws = fm && fm['htmx-internal-data'] && fm['htmx-internal-data'].webSocket;
                var wsExt = document.querySelector('[ws-send]');
                return !!(ta && fm && wsExt);
            }
        """)
        if ready:
            await asyncio.sleep(2)  # extra settle for WS handshake
            return True
        await asyncio.sleep(0.25)
    return False


async def send_and_wait(page, msg, wait=20):
    """Send a message via JS requestSubmit (matching card onclick pattern)."""
    await wait_for_ws(page)
    await page.evaluate(f"""
        () => {{
            var ta = document.getElementById('chat-input');
            var fm = document.getElementById('chat-form');
            if (ta && fm) {{
                ta.value = {repr(msg)};
                fm.requestSubmit();
            }}
        }}
    """)
    await asyncio.sleep(wait)
    await page.evaluate("() => { var m=document.getElementById('chat-messages'); if(m) m.scrollTop=m.scrollHeight; }")
    await asyncio.sleep(1)


async def run():
    from playwright.async_api import async_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # --- 01: Landing page (not logged in) ---
        await page.goto(BASE_URL)
        await asyncio.sleep(3)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_landing.png"))
        print("  captured  01_landing.png — Landing page")

        # --- 02: Register form ---
        await page.click('text=Sign up')
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_register_form.png"))
        print("  captured  02_register_form.png — Register form")

        # --- Register the demo user ---
        await page.fill('input[name="email"]', EMAIL)
        await page.fill('input[name="password"]', PASSWORD)
        await page.fill('input[name="display_name"]', "Demo User")
        await page.click('button:has-text("Create Account")')
        await asyncio.sleep(3)

        # Reload to get fresh page after registration
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await wait_for_ws(page)

        # --- 03: Welcome screen with 6 cards ---
        await page.screenshot(path=str(SCREENSHOTS_DIR / "03_welcome_cards.png"))
        print("  captured  03_welcome_cards.png — Welcome screen with 6 cards")

        # --- 04: Readiness Check-In ---
        await send_and_wait(page, "I'd like to do a readiness check-in", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "04_readiness_checkin.png"))
        print("  captured  04_readiness_checkin.png — Readiness Check-In chat")

        # --- 05: Performance Scan ---
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "Let's do a performance scan", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "05_performance_scan.png"))
        print("  captured  05_performance_scan.png — Performance Scan chat")

        # --- 06: Recovery Plan ---
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "Help me create a recovery plan", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "06_recovery_plan.png"))
        print("  captured  06_recovery_plan.png — Recovery Plan chat")

        # --- 07: Stress & Load ---
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "Analyze my stress and load levels", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "07_stress_load.png"))
        print("  captured  07_stress_load.png — Stress & Load chat")

        # --- 08: Resilience Builder ---
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "I want to work on resilience building", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "08_resilience_builder.png"))
        print("  captured  08_resilience_builder.png — Resilience Builder chat")

        # --- 09: Trace panel visible ---
        # The trace panel should be open from the last chat
        await page.screenshot(path=str(SCREENSHOTS_DIR / "09_trace_panel.png"))
        print("  captured  09_trace_panel.png — Trace panel with tool calls")

        # --- 10: Conversation history in sidebar ---
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "10_conversation_history.png"))
        print("  captured  10_conversation_history.png — Conversation history")

        # --- 11: About page ---
        await page.goto(f"{BASE_URL}/about")
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "11_about_page.png"))
        print("  captured  11_about_page.png — About page")

        # --- 12: About page scrolled ---
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(0.5)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "12_about_page_scroll.png"))
        print("  captured  12_about_page_scroll.png — About page (scrolled)")

        # --- 13: Mobile responsive view ---
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "13_mobile_view.png"))
        print("  captured  13_mobile_view.png — Mobile responsive view")

        await browser.close()

    print(f"\n  All screenshots saved to {SCREENSHOTS_DIR}/")


def main():
    app_proc = None
    if "--start-app" in sys.argv:
        print("  Starting app...")
        app_proc = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(5)

    print(f"\n{'='*50}")
    print(f"  Mentastic User Guide — Screenshot Capture")
    print(f"{'='*50}\n")

    asyncio.run(run())

    if app_proc:
        app_proc.terminate()
        app_proc.wait()

    print("\n  Done!")


if __name__ == "__main__":
    main()
