"""Analyze captured API requests and summarize endpoints."""

import json
import sys
from collections import defaultdict
from pathlib import Path


def main():
    capture_file = Path(__file__).resolve().parent.parent / "data" / "captured_requests.json"
    if not capture_file.exists():
        print(f"File not found: {capture_file}")
        print("Run src/reverse_api.py first to capture API requests.")
        sys.exit(1)

    with open(capture_file) as f:
        data = json.load(f)

    requests = data.get("requests", [])
    print(f"Total requests captured: {len(requests)}")
    print(f"URL: {data.get('url')}")
    print(f"Captured at: {data.get('captured_at')}")
    print()

    # Group by base URL
    groups = defaultdict(list)
    for r in requests:
        url = r["url"]
        method = r["method"]
        status = r.get("status", "?")
        ct = r.get("content_type", "")
        # Extract base path
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        groups[base].append((method, status, ct, r.get("response_body") is not None))

    print(f"=== Unique Endpoints ({len(groups)}) ===")
    for base, calls in sorted(groups.items()):
        methods = set(m for m, _, _, _ in calls)
        statuses = set(str(s) for _, s, _, _ in calls if s != "?")
        has_json = any(has for _, _, _, has in calls)
        sample = calls[0]
        print(f"\n  {base}")
        print(f"    Methods : {', '.join(sorted(methods))}")
        print(f"    Statuses: {', '.join(sorted(statuses)) if statuses else 'unknown'}")
        if has_json:
            print(f"    JSON    : yes")
        if sample[2]:
            print(f"    Type    : {sample[2]}")

    # Show JSON responses
    print("\n\n=== JSON Response Samples ===")
    for r in requests:
        if "response_body" in r:
            print(f"\n--- {r['method']} {r['url']} ---")
            body = r["response_body"]
            if isinstance(body, str) and len(body) > 500:
                print(body[:500] + "...")
            else:
                print(json.dumps(body, indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
