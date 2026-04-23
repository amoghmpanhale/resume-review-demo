"""
render.py
---------
Takes a PNG screenshot of each HTML asset in this folder, using a real
headless Chromium so that Google Fonts render correctly.

Why a local HTTP server?
    The pages use `fetch('./rubric.json')` (or `./review.json`), which
    browsers refuse to do over the `file://` protocol. Serving the folder
    at http://localhost:<port> side-steps that restriction.
"""

import http.server
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


HERE = Path(__file__).parent
PORT = 8765


# ---------------------------------------------------------------------------
# 1. Tiny HTTP server in a background thread
# ---------------------------------------------------------------------------
def start_server():
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(HERE), **kw
    )
    # allow_reuse_address avoids "address already in use" on quick re-runs.
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# 2. Screenshot helper
# ---------------------------------------------------------------------------
def screenshot(page, url, out_path, width, height, scale=2):
    """Load `url` at (width × height), wait for the page to mark itself
    ready, and save a PNG to `out_path`. `scale` bumps pixel density for
    a crisper image on retina-class displays."""
    page.set_viewport_size({"width": width, "height": height})
    page.goto(url, wait_until="networkidle")

    # Wait for the render() function to set data-ready="true".
    page.wait_for_function('document.body.dataset.ready === "true"',
                           timeout=15_000)

    page.screenshot(path=str(out_path),
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                    omit_background=False)
    print(f"  wrote {out_path.name}  ({width}×{height})")


# ---------------------------------------------------------------------------
# 3. Main
# ---------------------------------------------------------------------------
def main():
    server = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(device_scale_factor=2)
            page = context.new_page()

            # --- Rubric data portrait (1080 × 1080 square) ---------------
            screenshot(
                page,
                f"http://127.0.0.1:{PORT}/rubric_portrait.html",
                HERE / "rubric_portrait.png",
                width=1080,
                height=1080,
            )

            # --- Viewer screenshots --------------------------------------
            # Load the viewer, then inject the review into it so we don't
            # have to simulate a file drop. The viewer's state + render
            # are both plain globals inside its <script> block, so we can
            # drive them directly via page.evaluate.
            page.set_viewport_size({"width": 1080, "height": 1350})
            page.goto(f"http://127.0.0.1:{PORT}/review_viewer.html",
                      wait_until="networkidle")
            page.evaluate("""
                async () => {
                    const res = await fetch('./review.json');
                    state.review = await res.json();
                    render();
                    await document.fonts.ready;
                }
            """)
            # Small pause to let layout settle after fonts load.
            page.wait_for_timeout(400)

            # (a) Portrait hero-crop — masthead + summary + first issues.
            #     Great for the LinkedIn feed image.
            page.screenshot(
                path=str(HERE / "viewer_hero.png"),
                clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
            )
            print("  wrote viewer_hero.png  (1080×1350)")

            # (b) Full-page — for a portfolio page or as a secondary slide.
            page.screenshot(
                path=str(HERE / "viewer_full.png"),
                full_page=True,
            )
            print("  wrote viewer_full.png  (full page)")

            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
