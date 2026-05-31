"""Collect electricity consumption data from D2L Sicame API.

Usage:
  # One-shot fetch (stdout)
  python src/collector.py --username your@email.com --password yourpass

  # With InfluxDB
  python src/collector.py --username your@email.com --password yourpass --influx

  # Using .env file
  python src/collector.py --influx
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

BASE_URL = "https://d2l.sicame.io"
LOGIN_URL = f"{BASE_URL}/Login"
DETAILS_URL = f"{BASE_URL}/Details/Details"


def parse_args():
    parser = argparse.ArgumentParser(description="D2L Sicame electricity collector")
    parser.add_argument("--username", help="Login email")
    parser.add_argument("--password", help="Login password")
    parser.add_argument("--influx", action="store_true", help="Write to InfluxDB")
    parser.add_argument("--device-id", default="22002000211", help="D2L device ID")
    parser.add_argument("--meter-serial", default="22064149732", help="Meter serial")
    parser.add_argument(
        "--days-back", type=int, default=1,
        help="How many days of history to fetch (0 = today only)"
    )
    return parser.parse_args()


class D2LSession:
    def __init__(self, username: str, password: str, device_id: str, meter_serial: str):
        self.username = username
        self.password = password
        self.device_id = device_id
        self.meter_serial = meter_serial
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        })
        self._token = None

    def _extract_csrf_token(self) -> str | None:
        for cookie in self.session.cookies:
            if cookie.name.startswith(CSRF_COOKIE_PREFIX):
                return cookie.value
        return None

    def _extract_login_fields(self, html: str) -> dict[str, str]:
        fields = {}
        m = re.search(
            r'<input[^>]*name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            html,
        )
        if m:
            fields["__RequestVerificationToken"] = m.group(1)
        return fields

    def _get_details_page_csrf(self) -> str | None:
        """Fetch details page and extract __RequestVerificationToken from the form."""
        details_url = f"{BASE_URL}/Details/{self.device_id}"
        resp = self.session.get(details_url)
        resp.raise_for_status()
        m = re.search(
            r'<input[^>]*name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            resp.text,
        )
        if m:
            return m.group(1)
        return None

    def login(self) -> None:
        login_url = f"{LOGIN_URL}?ReturnUrl=%2FDetails%2F{self.device_id}"

        # GET login page to obtain CSRF cookie + token
        resp = self.session.get(login_url)
        resp.raise_for_status()

        login_fields = self._extract_login_fields(resp.text)
        if "__RequestVerificationToken" not in login_fields:
            print("[!] Could not find CSRF token in login page", file=sys.stderr)
            sys.exit(1)

        login_fields["loginData.Username"] = self.username
        login_fields["loginData.Password"] = self.password
        login_fields["loginData.RememberMe"] = "false"
        login_fields["loginData.CGUOk"] = "true"

        # POST login with ReturnUrl
        resp = self.session.post(
            login_url,
            data=login_fields,
            allow_redirects=True,
        )
        resp.raise_for_status()

        if "Login" in resp.url:
            print(f"[!] Login failed — still on login page", file=sys.stderr)
            print(f"    Response length: {len(resp.text)}", file=sys.stderr)
            if "invalid" in resp.text.lower():
                print(f"    Possible invalid credentials", file=sys.stderr)
            sys.exit(1)

        # Fetch details page to get the AJAX CSRF token
        self._token = self._get_details_page_csrf()
        if not self._token:
            print("[!] Could not get CSRF token from details page", file=sys.stderr)
            sys.exit(1)
        print(f"[+] Login OK, session established", file=sys.stderr)

    def fetch_data(
        self,
        from_dt: datetime,
        to_dt: datetime,
        visualization: str = "DetailedByDay",
    ) -> dict[str, Any]:
        if self._token is None:
            raise RuntimeError("Not logged in")

        params = {"handler": "GetDatas"}
        data = {
            "d2l_id": self.device_id,
            "detailData.d2lInfo.Compteur": self.meter_serial,
            "detailData.d2lInfo.Id": self.device_id,
            "detailData.d2lInfo.Name": "",
            "detailData.from": from_dt.strftime("%d/%m/%Y %H:%M:%S"),
            "detailData.to": to_dt.strftime("%d/%m/%Y %H:%M:%S"),
            "detailData.typeDatas": "Power",
            "detailData.typeVisualization": visualization,
            "isonlyproduction": "False",
            "detailData.SelectedDate": from_dt.strftime("%Y-%m-%d"),
            "detailData.SelectedDateUnixEpoch": str(int(from_dt.timestamp() * 1000)),
        }
        headers = {
            "RequestVerificationToken": self._token,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": f"{BASE_URL}/Details/{self.device_id}",
        }

        resp = self.session.post(DETAILS_URL, params=params, data=data, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def fetch_range(
        self, from_dt: datetime, to_dt: datetime
    ) -> list[dict[str, Any]]:
        results = []
        current = from_dt
        one_day = timedelta(days=1)

        while current < to_dt:
            day_end = min(current + one_day, to_dt)
            print(
                f"  Fetching {current.date()}...",
                file=sys.stderr, end="", flush=True
            )
            json_data = self.fetch_data(current, day_end)
            print(
                f" {len(json_data.get('graphDatas', []))} points",
                file=sys.stderr,
            )
            results.append(json_data)
            current = day_end

        return results


def format_for_influx(
    json_data: list[dict], unit: str = "Wh"
) -> list[dict]:
    """Convert API response to InfluxDB point format."""
    points = []
    for page in json_data:
        columns = page.get("columns", [])
        for entry in page.get("graphDatas", []):
            ts = entry["timeSerie"]["Key"]
            values = entry["timeSerie"]["Value"]
            for i, val in enumerate(values):
                if val is None:
                    continue
                col_name = columns[i]["item1"] if i < len(columns) else f"index_{i}"
                col_label = columns[i]["item2"] if i < len(columns) else ""
                points.append({
                    "measurement": "electricite_index",
                    "time": ts,
                    "tags": {
                        "tarif": col_name,
                        "tarif_label": col_label,
                    },
                    "fields": {
                        "valeur": float(val),
                        "unite": unit,
                    },
                })
    return points


def write_influxdb(points: list[dict]) -> None:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    url = os.getenv("INFLUX_URL", "http://localhost:8086")
    token = os.getenv("INFLUX_TOKEN", "my-token")
    org = os.getenv("INFLUX_ORG", "monelec")
    bucket = os.getenv("INFLUX_BUCKET", "electricite")

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    for p in points:
        point = (
            Point(p["measurement"])
            .time(p["time"])
            .tag("tarif", p["tags"]["tarif"])
            .tag("tarif_label", p["tags"]["tarif_label"])
            .field("valeur", p["fields"]["valeur"])
            .field("unite", p["fields"]["unite"])
        )
        try:
            write_api.write(bucket=bucket, org=org, record=point)
        except Exception as e:
            print(f"[!] Write error: {e}", file=sys.stderr)

    write_api.close()
    client.close()
    print(f"[+] {len(points)} points written to InfluxDB", file=sys.stderr)


def main():
    load_dotenv()
    args = parse_args()

    username = args.username or os.getenv("D2L_USERNAME")
    password = args.password or os.getenv("D2L_PASSWORD")
    device_id = args.device_id
    meter_serial = args.meter_serial

    if not username or not password:
        print(
            "Error: provide --username/--password or set D2L_USERNAME/D2L_PASSWORD in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=args.days_back)
    from_dt = from_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    to_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    d2l = D2LSession(username, password, device_id, meter_serial)
    d2l.login()

    print(f"Fetching data from {from_dt.date()} to {to_dt.date()}", file=sys.stderr)

    # Fetch daily detail (1-minute granularity)
    raw = d2l.fetch_range(from_dt, to_dt)

    # Save raw JSON
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw_path = data_dir / f"raw_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(raw_path, "w") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"Raw data saved to {raw_path}", file=sys.stderr)

    # Format for InfluxDB
    points = format_for_influx(raw, unit="Wh")
    print(f"Formatted {len(points)} points", file=sys.stderr)

    if args.influx:
        write_influxdb(points)
    else:
        # Pretty print first/last few points as sample
        print(json.dumps(points[:3], indent=2, default=str))
        if len(points) > 6:
            print("...")
            print(json.dumps(points[-3:], indent=2, default=str))


if __name__ == "__main__":
    main()
