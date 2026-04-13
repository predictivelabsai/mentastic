"""
Capture User Guide Screenshots

Launches a headless browser, navigates the full Mentastic flow:
landing → register → chat → integrations → about → mobile.

Usage:
    # App must be running: python app.py
    python tests/capture_guide.py
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
    """Wait for chat WebSocket form to load."""
    for _ in range(timeout * 4):
        ready = await page.evaluate("""
            () => {
                var ta = document.getElementById('chat-input');
                var wsExt = document.querySelector('[ws-send]');
                return !!(ta && wsExt);
            }
        """)
        if ready:
            await asyncio.sleep(2)
            return True
        await asyncio.sleep(0.25)
    return False


async def send_and_wait(page, msg, wait=20):
    """Send a message via JS requestSubmit."""
    await wait_for_ws(page)
    await page.evaluate(f"""
        () => {{
            var ta = document.getElementById('chat-input');
            var fm = document.getElementById('chat-form');
            if (ta && fm) {{ ta.value = {repr(msg)}; fm.requestSubmit(); }}
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

        # --- 01: Landing page ---
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_landing_hero.png"))
        print("  captured  01_landing_hero.png")

        # --- 02: Landing scroll (features) ---
        await page.evaluate("window.scrollTo(0, 900)")
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_landing_features.png"))
        print("  captured  02_landing_features.png")

        # --- 03: Landing scroll (integrations + sectors) ---
        await page.evaluate("window.scrollTo(0, 2200)")
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "03_landing_integrations.png"))
        print("  captured  03_landing_integrations.png")

        # --- 04: Sign-in page (Clerk or fallback) ---
        await page.goto(f"{BASE_URL}/signin")
        await asyncio.sleep(5)  # wait for Clerk JS to mount
        await page.screenshot(path=str(SCREENSHOTS_DIR / "04_signin.png"))
        print("  captured  04_signin.png")

        # --- 04b: Register page ---
        await page.goto(f"{BASE_URL}/register")
        await asyncio.sleep(5)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "04b_register.png"))
        print("  captured  04b_register.png")

        # --- Login via fallback auth (POST to /signin with email+password) ---
        import sys, os
        sys.path.insert(0, str(ROOT))
        os.chdir(str(ROOT))
        from utils.auth import create_user, get_user_by_email
        if not get_user_by_email(EMAIL):
            create_user(EMAIL, PASSWORD, "Demo User")
        # POST login form via page.evaluate (bypasses Clerk UI)
        await page.evaluate(f"""
            async () => {{
                const form = new FormData();
                form.append('email', '{EMAIL}');
                form.append('password', '{PASSWORD}');
                const resp = await fetch('/signin', {{ method: 'POST', body: form, redirect: 'follow' }});
            }}
        """)
        await asyncio.sleep(2)

        # --- 05: Chat welcome ---
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await wait_for_ws(page)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "05_chat_welcome.png"))
        print("  captured  05_chat_welcome.png")

        # --- 06: Readiness Check-In ---
        await send_and_wait(page, "I'd like to do a readiness check-in", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "06_readiness_checkin.png"))
        print("  captured  06_readiness_checkin.png")

        # --- 07: Performance Scan ---
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "Let's do a performance scan", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "07_performance_scan.png"))
        print("  captured  07_performance_scan.png")

        # --- 08: Resilience Builder ---
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await send_and_wait(page, "I want to work on resilience building for stress", 15)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "08_resilience_builder.png"))
        print("  captured  08_resilience_builder.png")

        # --- 09: Conversation history ---
        await page.goto(f"{BASE_URL}/chat")
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "09_conversation_history.png"))
        print("  captured  09_conversation_history.png")

        # --- 10: Dashboard ---
        await page.goto(f"{BASE_URL}/dashboard")
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "10_dashboard.png"))
        print("  captured  10_dashboard.png")

        # --- 10b: Integrations page ---
        await page.goto(f"{BASE_URL}/integrations")
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "10b_integrations.png"))
        print("  captured  10b_integrations.png")

        # --- 11: About page ---
        await page.goto(f"{BASE_URL}/about")
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "11_about.png"))
        print("  captured  11_about.png")

        # --- 12: Sign In page ---
        await page.goto(f"{BASE_URL}/logout")
        await asyncio.sleep(1)
        await page.goto(f"{BASE_URL}/signin")
        await asyncio.sleep(1)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "12_signin.png"))
        print("  captured  12_signin.png")

        # --- 13: Mobile landing ---
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "13_mobile_landing.png"))
        print("  captured  13_mobile_landing.png")

        # --- 14: Mobile chat (re-login via fetch) ---
        await page.evaluate(f"""
            async () => {{
                const form = new FormData();
                form.append('email', '{EMAIL}');
                form.append('password', '{PASSWORD}');
                await fetch('/signin', {{ method: 'POST', body: form, redirect: 'follow' }});
            }}
        """)
        await asyncio.sleep(1)
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "14_mobile_chat.png"))
        print("  captured  14_mobile_chat.png")

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
