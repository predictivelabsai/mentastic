"""
Capture Product Demo Video

Playwright script that walks through the Mentastic platform,
capturing frames for an MP4 video and animated GIF.

Usage:
    python app.py &
    python tests/capture_video.py

Output:
    docs/demo_video.mp4
    docs/demo_video.gif
    docs/frames/*.png
"""

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRAMES_DIR = ROOT / "docs" / "frames"
BASE_URL = "http://localhost:5001"
EMAIL = "demo@mentastic.com"
PASSWORD = "demo1234"

frame_num = 0


async def capture(page, label, pause=1.0):
    """Capture a frame with a pause for natural pacing."""
    global frame_num
    await asyncio.sleep(pause)
    path = FRAMES_DIR / f"{frame_num:03d}_{label}.png"
    await page.screenshot(path=str(path), type="png")
    print(f"  [{frame_num:03d}] {label}")
    frame_num += 1


async def wait_for_ws(page, timeout=10):
    """Wait for chat form to load AND WebSocket to connect."""
    for _ in range(timeout * 4):
        ready = await page.evaluate("""
            () => {
                var ta = document.getElementById('chat-input');
                var fm = document.getElementById('chat-form');
                var wsExt = document.querySelector('[ws-send]');
                return !!(ta && fm && wsExt);
            }
        """)
        if ready:
            await asyncio.sleep(2)
            return True
        await asyncio.sleep(0.25)
    return False


async def send_chat(page, msg, wait=20.0):
    """Send a message via JS requestSubmit, then wait for streaming response."""
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
    await asyncio.sleep(0.5)


async def run():
    from playwright.async_api import async_playwright

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # ===== LANDING =====
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await capture(page, "landing", 0.5)

        # ===== LOGIN =====
        # Try to login (user should exist from capture_guide or manual setup)
        await page.fill('input[name="email"]', EMAIL)
        await page.fill('input[name="password"]', PASSWORD)
        await capture(page, "login_filled", 0.5)

        await page.click('button:has-text("Login")')
        await asyncio.sleep(2)

        # ===== WELCOME SCREEN =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await wait_for_ws(page)
        await capture(page, "welcome_screen", 1.5)
        await capture(page, "welcome_screen_hold", 1.0)

        # ===== CHAT: Readiness Check-In =====
        await send_chat(page, "I'd like to do a readiness check-in", 15)
        await capture(page, "chat_readiness_checkin", 1.0)
        await page.evaluate("() => { var m=document.getElementById('chat-messages'); if(m) m.scrollTop=m.scrollHeight; }")
        await capture(page, "chat_readiness_checkin_scroll", 0.5)

        # ===== CHAT: Performance Scan =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "Let's do a performance scan", 15)
        await capture(page, "chat_performance_scan", 1.0)

        # ===== CHAT: Recovery Plan =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "Help me create a recovery plan", 15)
        await capture(page, "chat_recovery_plan", 1.0)

        # ===== CHAT: Stress & Load =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "Analyze my stress and load levels", 15)
        await capture(page, "chat_stress_load", 1.0)

        # ===== CHAT: Readiness Report =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "Show me my readiness report", 15)
        await capture(page, "chat_readiness_report", 1.0)

        # ===== CHAT: Resilience Builder =====
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "I want to work on resilience building", 15)
        await capture(page, "chat_resilience_builder", 1.0)

        # ===== CONVERSATION HISTORY =====
        await page.goto(BASE_URL)
        await asyncio.sleep(2)
        await capture(page, "conversation_history", 1.0)

        # ===== ABOUT PAGE =====
        await page.goto(f"{BASE_URL}/about")
        await asyncio.sleep(1)
        await capture(page, "about_page", 1.5)
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(0.5)
        await capture(page, "about_page_scroll", 1.0)

        # ===== MOBILE VIEW =====
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(2)
        await capture(page, "mobile_welcome", 1.5)

        # ===== BACK TO DESKTOP WELCOME =====
        await page.set_viewport_size({"width": 1440, "height": 900})
        await page.goto(f"{BASE_URL}/?new=1")
        await asyncio.sleep(2)
        await capture(page, "final_welcome", 1.5)

        await browser.close()

    print(f"\n  Captured {frame_num} frames to docs/frames/")


def build_video():
    """Assemble frames into MP4 video and GIF."""
    from PIL import Image
    import av
    import numpy as np

    frames = sorted(FRAMES_DIR.glob("*.png"))
    if not frames:
        print("No frames found!")
        return

    images = [np.array(Image.open(f)) for f in frames]
    print(f"  Building video from {len(images)} frames...")

    # --- MP4 ---
    mp4_path = ROOT / "docs" / "demo_video.mp4"
    fps = 2
    hold_frames = 3  # each screenshot held for 1.5 seconds

    container = av.open(str(mp4_path), mode="w")
    h, w = images[0].shape[:2]
    w_enc = w if w % 2 == 0 else w - 1
    h_enc = h if h % 2 == 0 else h - 1
    stream = container.add_stream("libx264", rate=fps)
    stream.width = w_enc
    stream.height = h_enc
    stream.pix_fmt = "yuv420p"

    for img in images:
        img_cropped = img[:h_enc, :w_enc, :3]
        frame = av.VideoFrame.from_ndarray(img_cropped, format="rgb24")
        for _ in range(hold_frames):
            for packet in stream.encode(frame):
                container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)
    container.close()
    total_secs = len(images) * hold_frames / fps
    print(f"  Saved MP4: {mp4_path} ({total_secs:.0f}s)")

    # --- GIF ---
    gif_path = ROOT / "docs" / "demo_video.gif"
    pil_frames = []
    for img in images:
        pil_img = Image.fromarray(img[:, :, :3])
        pil_img = pil_img.resize((w // 2, h // 2), Image.LANCZOS)
        pil_frames.append(pil_img)

    pil_frames[0].save(
        str(gif_path), save_all=True, append_images=pil_frames[1:],
        duration=1500, loop=0, optimize=True,
    )
    print(f"  Saved GIF: {gif_path}")


def main():
    print(f"\n{'='*60}")
    print(f"  Mentastic Product Demo — Video Capture")
    print(f"{'='*60}\n")

    asyncio.run(run())

    print(f"\n{'='*60}")
    print(f"  Building video and GIF...")
    print(f"{'='*60}\n")

    build_video()

    print(f"\n  Done!")
    print(f"  MP4: docs/demo_video.mp4")
    print(f"  GIF: docs/demo_video.gif")
    print(f"  Frames: docs/frames/\n")


if __name__ == "__main__":
    main()
