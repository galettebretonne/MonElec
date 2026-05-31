"""Reverse-engineer the D2L Sicame API using Playwright.

Captures all XHR/Fetch requests made during login and navigation
to identify API endpoints, auth mechanism, and data format.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CAPTURE_FILE = DATA_DIR / "captured_requests.json"
AUTH_FILE = DATA_DIR / "auth_state.json"

URL = "https://d2l.sicame.io/Login?ReturnUrl=%2FDetails%2F22002000211"
DETAILS_URL = "https://d2l.sicame.io/Details/22002000211"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )

        # Intercept ALL requests
        def on_request(request):
            url = request.url
            # Skip static assets, data uris, etc.
            if any(skip in url for skip in [".css", ".js", ".png", ".ico", ".svg", "google-analytics"]):
                return
            if url.startswith("data:"):
                return
            entry = {
                "timestamp": datetime.now().isoformat(),
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
                "resource_type": request.resource_type,
            }
            if request.post_data:
                entry["post_data"] = request.post_data
            captured.append(entry)
            print(f"[REQ] {request.method} {url}")

        def on_response(response):
            url = response.url
            if any(skip in url for skip in [".css", ".js", ".png", ".ico", ".svg"]):
                return
            if url.startswith("data:"):
                return
            # Update the matching request entry with response info
            for entry in captured:
                if entry["url"] == url and "status" not in entry:
                    entry["status"] = response.status
                    entry["content_type"] = response.headers.get("content-type", "")
                    # Try to capture response body for API calls
                    if "json" in response.headers.get("content-type", ""):
                        try:
                            entry["response_body"] = response.json()
                        except Exception:
                            try:
                                entry["response_body_preview"] = response.text()[:1000]
                            except Exception:
                                pass
                    break
            print(f"[RES] {response.status} {url}")

        context.on("request", on_request)
        context.on("response", on_response)

        page = context.new_page()

        print("=" * 60)
        print("Navigate to login page...")
        print("Login manually in the browser window.")
        print("After login, the script will navigate to the Details page.")
        print("Press Enter in the terminal after you have logged in...")
        print("=" * 60)

        page.goto(URL, wait_until="networkidle")

        # Wait for user to log in manually
        input("Press Enter after successful login...")

        # Save auth state (cookies, localStorage)
        context.storage_state(path=str(AUTH_FILE))
        print(f"Auth state saved to {AUTH_FILE}")

        # Navigate to details page
        print(f"Navigating to {DETAILS_URL}...")
        page.goto(DETAILS_URL, wait_until="networkidle", timeout=30000)

        print("Waiting for data to load...")
        page.wait_for_timeout(5000)

        # Let user explore a bit more if they want
        print("You can now interact with the page to trigger more API calls.")
        input("Press Enter when done to save captured requests...")

        browser.close()

    # Save all captured requests
    output = {
        "captured_at": datetime.now().isoformat(),
        "url": URL,
        "details_url": DETAILS_URL,
        "requests": captured,
    }
    with open(CAPTURE_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nCaptured {len(captured)} requests -> {CAPTURE_FILE}")

    # Summary
    print("\n=== API Endpoints detected ===")
    api_calls = [r for r in captured if r.get("method") in ("GET", "POST", "PUT", "DELETE")]
    seen = set()
    for r in api_calls:
        url = r["url"]
        # Deduplicate by URL pattern
        clean = url.split("?")[0] if "?" in url else url
        if clean not in seen:
            seen.add(clean)
            method = r["method"]
            status = r.get("status", "?")
            ct = r.get("content_type", "")
            print(f"  {method} {status} {url}")


if __name__ == "__main__":
    main()
