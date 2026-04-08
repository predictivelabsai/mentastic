"""
Generate architecture PDF from architecture_readme.md.

Renders each Mermaid diagram as a PNG screenshot via Playwright,
then assembles everything into a clean PDF.

Usage: python docs/generate_architecture_pdf.py
Output: docs/architecture.pdf
"""

import re
import asyncio
import base64
from pathlib import Path
from markdown import markdown

ROOT = Path(__file__).parent
MD_FILE = ROOT / "architecture_readme.md"
PDF_FILE = ROOT / "architecture.pdf"
DIAGRAM_DIR = ROOT / "diagrams"


async def render_mermaid_to_png(browser, code: str, index: int) -> str:
    """Render a single Mermaid diagram to PNG, return the file path."""
    page = await browser.new_page(viewport={"width": 1200, "height": 800})

    html = f"""<!DOCTYPE html>
<html><head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
    body {{ margin: 0; padding: 20px; background: white; display: flex; justify-content: center; }}
    .mermaid {{ font-family: -apple-system, sans-serif; }}
</style>
</head><body>
<div class="mermaid">
{code}
</div>
<script>
    mermaid.initialize({{
        startOnLoad: true,
        theme: 'base',
        themeVariables: {{
            primaryColor: '#f0fdfa',
            primaryBorderColor: '#0d9488',
            primaryTextColor: '#1e293b',
            lineColor: '#64748b',
            secondaryColor: '#f1f5f9',
            tertiaryColor: '#ffffff',
            fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
            fontSize: '14px'
        }}
    }});
</script>
</body></html>"""

    await page.set_content(html, wait_until="networkidle")
    await page.wait_for_function(
        "() => document.querySelector('.mermaid svg') !== null",
        timeout=15000,
    )
    await asyncio.sleep(0.5)

    # Get the SVG bounding box and screenshot just that element
    mermaid_div = await page.query_selector(".mermaid")
    path = str(DIAGRAM_DIR / f"diagram_{index:02d}.png")
    await mermaid_div.screenshot(path=path, type="png")
    await page.close()
    return path


async def generate_pdf():
    from playwright.async_api import async_playwright

    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)

    print("  Reading markdown...")
    md_text = MD_FILE.read_text()

    # Extract mermaid blocks
    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    mermaid_blocks = [(m.start(), m.end(), m.group(1).strip()) for m in pattern.finditer(md_text)]
    print(f"  Found {len(mermaid_blocks)} Mermaid diagrams")

    # Render each diagram to PNG
    print("  Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        diagram_paths = []
        for i, (start, end, code) in enumerate(mermaid_blocks):
            print(f"  Rendering diagram {i+1}/{len(mermaid_blocks)}...")
            path = await render_mermaid_to_png(browser, code, i)
            diagram_paths.append(path)

        # Build final HTML with diagrams as embedded images
        parts = []
        pos = 0
        for i, (start, end, code) in enumerate(mermaid_blocks):
            before = md_text[pos:start]
            parts.append(markdown(before, extensions=["tables", "fenced_code"]))
            # Embed PNG as base64
            with open(diagram_paths[i], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            parts.append(f'<div class="diagram"><img src="data:image/png;base64,{b64}"></div>')
            pos = end

        parts.append(markdown(md_text[pos:], extensions=["tables", "fenced_code"]))
        html_body = "\n".join(parts)

        css = """
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 11pt; line-height: 1.6; color: #1e293b;
    max-width: 1100px; margin: 0 auto; padding: 40px;
}
h1 { font-size: 26pt; color: #0d9488; border-bottom: 3px solid #0d9488; padding-bottom: 10px; }
h2 { font-size: 16pt; color: #0f766e; margin-top: 36px; break-after: avoid; }
h3 { font-size: 13pt; color: #1e293b; margin-top: 20px; }
p { margin: 6px 0; }
code { background: #f1f5f9; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; font-size: 9.5pt; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; break-inside: avoid; }
th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
th { background: #f0fdfa; font-weight: 600; color: #0f766e; }
tr:nth-child(even) td { background: #f8fafc; }
.diagram { text-align: center; margin: 16px 0; break-inside: avoid; }
.diagram img { max-width: 100%; height: auto; }
"""

        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>{html_body}</body></html>"""

        # Render PDF
        print("  Generating PDF...")
        page = await browser.new_page()
        await page.set_content(full_html, wait_until="networkidle")
        await page.pdf(
            path=str(PDF_FILE),
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"},
        )
        await browser.close()

    size_kb = PDF_FILE.stat().st_size / 1024
    print(f"  Saved: {PDF_FILE} ({size_kb:.0f} KB)\n  Done!")


def main():
    print(f"\n  Mentastic Architecture PDF Generator\n")
    asyncio.run(generate_pdf())


if __name__ == "__main__":
    main()
