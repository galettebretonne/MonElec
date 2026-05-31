"""Convert index readings to actual power consumption.

The API returns cumulative index values (Wh). This computes delta
between consecutive points to get real consumption (W average over interval).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def compute_power(raw_pages: list[dict]) -> list[dict]:
    """Compute power (W) from index differences."""
    columns = raw_pages[0].get("columns", [])
    col_count = len(columns)

    all_points = []
    for page in raw_pages:
        for entry in page.get("graphDatas", []):
            ts = entry["timeSerie"]["Key"]
            vals = entry["timeSerie"]["Value"]
            all_points.append((ts, vals))

    all_points.sort(key=lambda x: x[0])

    # Calculate deltas
    power_points = []
    for i in range(1, len(all_points)):
        prev_ts, prev_vals = all_points[i - 1]
        curr_ts, curr_vals = all_points[i]

        t_prev = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
        t_curr = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
        delta_h = (t_curr - t_prev).total_seconds() / 3600
        if delta_h <= 0:
            continue

        for j in range(col_count):
            prev_v = prev_vals[j] if j < len(prev_vals) else None
            curr_v = curr_vals[j] if j < len(curr_vals) else None
            if prev_v is None or curr_v is None:
                continue
            delta_wh = curr_v - prev_v
            if delta_wh < 0:
                continue
            power_w = delta_wh / delta_h

            col_name = columns[j]["item1"]
            col_label = columns[j]["item2"]
            power_points.append({
                "measurement": "electricite_power",
                "time": curr_ts,
                "tags": {"tarif": col_name, "tarif_label": col_label},
                "fields": {"valeur": round(power_w, 1), "unite": "W"},
            })

    return power_points


def main():
    import glob as g

    files = sorted(Path(DATA_DIR).glob("raw_*.json"))
    if not files:
        print("No raw_*.json files in data/")
        return

    latest = files[-1]
    print(f"Processing {latest}...")

    with open(latest) as f:
        raw = json.load(f)

    power_points = compute_power(raw)
    out_file = DATA_DIR / f"power_{latest.stem.replace('raw_', '')}.json"
    with open(out_file, "w") as f:
        json.dump(power_points, f, indent=2, default=str)

    print(f"Computed {len(power_points)} power points -> {out_file}")

    # Print summary
    print("\n=== Last values per tariff ===")
    seen = set()
    for p in reversed(power_points):
        tag = p["tags"]["tarif"]
        if tag not in seen:
            seen.add(tag)
            label = p["tags"]["tarif_label"]
            val = p["fields"]["valeur"]
            print(f"  {label:30s} {val:8.1f} W  @ {p['time']}")


if __name__ == "__main__":
    main()
