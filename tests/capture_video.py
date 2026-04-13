"""
Capture Product Demo Video

Playwright script that walks through the full Mentastic flow:
landing → register → chat (all 6 tools) → integrations → about → mobile.

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
BASE_URL = "http://localhost:5010"
EMAIL = "demo@mentastic.com"
PASSWORD = "demo1234"

frame_num = 0


async def capture(page, label, pause=1.0):
    global frame_num
    await asyncio.sleep(pause)
    path = FRAMES_DIR / f"{frame_num:03d}_{label}.png"
    await page.screenshot(path=str(path), type="png")
    print(f"  [{frame_num:03d}] {label}")
    frame_num += 1


async def wait_for_ws(page, timeout=10):
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


async def send_chat(page, msg, wait=20.0):
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
    await asyncio.sleep(0.5)


async def run():
    from playwright.async_api import async_playwright

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # ===== LANDING =====
        await page.goto(BASE_URL)
        await capture(page, "landing_hero", 2)

        await page.evaluate("window.scrollTo(0, 900)")
        await capture(page, "landing_features", 1)

        await page.evaluate("window.scrollTo(0, 2200)")
        await capture(page, "landing_integrations", 1)

        # ===== SIGNIN (Clerk UI) =====
        await page.goto(f"{BASE_URL}/signin")
        await asyncio.sleep(5)
        await capture(page, "signin_clerk", 1)

        # ===== REGISTER (Clerk UI) =====
        await page.goto(f"{BASE_URL}/register")
        await asyncio.sleep(5)
        await capture(page, "register_clerk", 1)

        # Login via fallback auth for chat testing
        import sys, os
        sys.path.insert(0, str(ROOT))
        os.chdir(str(ROOT))
        from utils.auth import create_user, get_user_by_email
        if not get_user_by_email(EMAIL):
            create_user(EMAIL, PASSWORD, "Demo User")
        await page.evaluate(f"""
            async () => {{
                const form = new FormData();
                form.append('email', '{EMAIL}');
                form.append('password', '{PASSWORD}');
                await fetch('/signin', {{ method: 'POST', body: form, redirect: 'follow' }});
            }}
        """)
        await asyncio.sleep(2)

        # ===== CHAT: Welcome =====
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await wait_for_ws(page)
        await capture(page, "chat_welcome", 1.5)

        # ===== CHAT: Readiness Check-In =====
        await send_chat(page, "I'd like to do a readiness check-in", 15)
        await capture(page, "chat_readiness", 1)

        # ===== CHAT: Recovery Plan =====
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "Help me create a recovery plan", 15)
        await capture(page, "chat_recovery", 1)

        # ===== CHAT: Resilience Builder =====
        await page.goto(f"{BASE_URL}/chat?new=1")
        await asyncio.sleep(3)
        await send_chat(page, "I want to work on resilience building", 15)
        await capture(page, "chat_resilience", 1)

        # ===== INTEGRATIONS =====
        await page.goto(f"{BASE_URL}/integrations")
        await capture(page, "integrations", 2)

        # ===== ABOUT =====
        await page.goto(f"{BASE_URL}/about")
        await capture(page, "about", 1.5)

        # ===== CONVERSATION HISTORY =====
        await page.goto(f"{BASE_URL}/chat")
        await asyncio.sleep(2)
        await capture(page, "conversation_history", 1)

        # ===== MOBILE =====
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(BASE_URL)
        await capture(page, "mobile_landing", 2)

        # ===== BACK TO DESKTOP =====
        await page.set_viewport_size({"width": 1440, "height": 900})
        await page.goto(BASE_URL)
        await capture(page, "final_landing", 1.5)

        await browser.close()

    print(f"\n  Captured {frame_num} frames to docs/frames/")


def build_video():
    from PIL import Image
    import av
    import numpy as np

    frames = sorted(FRAMES_DIR.glob("*.png"))
    if not frames:
        print("No frames found!")
        return

    images = [np.array(Image.open(f)) for f in frames]
    print(f"  Building video from {len(images)} frames...")

    mp4_path = ROOT / "docs" / "demo_video.mp4"
    fps = 2
    hold_frames = 3

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
