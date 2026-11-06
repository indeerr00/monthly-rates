#!/usr/bin/env python3
"""Build rates.json for the Monthly iOS app from the Optimal Blue indices on FRED.

Run daily by .github/workflows/refresh.yml. Needs FRED_KEY in the environment.
Writes nothing and exits non-zero on any problem, so a bad run leaves the last
good rates.json in place rather than publishing junk to the app.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
API = "https://api.stlouisfed.org/fred/series/observations"

# id in the feed -> (FRED series, display name, term in years)
SERIES = [
    ("30f", "OBMMIC30YF", "30-year fixed", 30),
    ("15f", "OBMMIC15YF", "15-year fixed", 15),
]

ATTRIBUTION = (
    "Source: Optimal Blue Mortgage Market Indices (OBMMIC30YF, OBMMIC15YF), "
    "retrieved from FRED, Federal Reserve Bank of St. Louis."
)

# A year of trading days plus slack, so the 52-week range and year-ago figure are real.
LOOKBACK_DAYS = 420
HISTORY_POINTS = 250


def _get(url: str) -> bytes:
    """GET with retries.

    FRED's graph CSV export intermittently stalls -- a single read timeout on
    2026-11-05 skipped a day of rates. One attempt is not enough; these are
    cheap requests and the job runs once a day.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "monthly-rates/1.0"})
    last = None
    for attempt in range(4):
        if attempt:
            time.sleep(5 * attempt)          # 5s, 10s, 15s
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                return r.read()
        except Exception as e:                # noqa: BLE001 -- retry anything transient
            last = e
            print(f"  attempt {attempt + 1}/4 failed: {e}", file=sys.stderr)
    raise RuntimeError(f"all 4 attempts failed: {last}")


def _point(day: str, raw: str) -> dict | None:
    """One observation, or None if FRED has no value for that day."""
    day, raw = day.strip(), raw.strip()
    if raw in (".", "", "NA") or len(day) != 10:
        return None
    try:
        return {"date": day, "value": round(float(raw), 3)}
    except ValueError:
        return None


def fetch_csv(series_id: str, start: str) -> list[dict]:
    """FRED's graph CSV export. Needs no API key, which is why it is tried first."""
    q = urllib.parse.urlencode({"id": series_id, "cosd": start})
    text = _get(f"{CSV}?{q}").decode("utf-8-sig", "replace")

    rows = [r for r in text.splitlines() if r.strip()]
    if len(rows) < 2:
        raise RuntimeError(f"{series_id}: CSV had {len(rows)} line(s)")

    points = []
    for row in rows[1:]:                      # row 0 is the header
        cells = row.split(",")
        if len(cells) < 2:
            continue
        if (p := _point(cells[0], cells[1])) is not None:
            points.append(p)
    return points


def fetch_api(series_id: str, start: str, key: str) -> list[dict]:
    """The documented FRED API. Used only if the keyless CSV export fails."""
    q = urllib.parse.urlencode(
        {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        }
    )
    payload = json.loads(_get(f"{API}?{q}"))
    points = []
    for o in payload.get("observations", []):
        if (p := _point(o.get("date", ""), str(o.get("value", "")))) is not None:
            points.append(p)
    return points


def fetch(series_id: str, key: str) -> list[dict]:
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        points = fetch_csv(series_id, start)
        if len(points) >= 30:
            print(f"{series_id}: {len(points)} observations via keyless CSV export")
            return points
        raise RuntimeError(f"CSV export returned only {len(points)} observations")
    except Exception as e:
        if not key:
            raise RuntimeError(f"{series_id}: {e}; and no FRED_KEY is set to fall back on") from e
        print(f"{series_id}: CSV export unusable ({e}); falling back to the FRED API", file=sys.stderr)

    points = fetch_api(series_id, start, key)
    print(f"{series_id}: {len(points)} observations via the FRED API")
    return points


def value_nearest(points: list[dict], target: date) -> float:
    return min(points, key=lambda p: abs(datetime.strptime(p["date"], "%Y-%m-%d").date() - target))["value"]


def pack(feed_id: str, series_id: str, name: str, term: int, key: str) -> dict:
    points = fetch(series_id, key)
    # Guard here rather than in fetch(): this is where the data gets indexed.
    if len(points) < 30:
        raise RuntimeError(f"{series_id}: only {len(points)} usable observations")
    latest = datetime.strptime(points[-1]["date"], "%Y-%m-%d").date()
    window = [
        p for p in points
        if datetime.strptime(p["date"], "%Y-%m-%d").date() > latest - timedelta(days=365)
    ]
    values = [p["value"] for p in window] or [points[-1]["value"]]
    return {
        "id": feed_id,
        "name": name,
        "term": term,
        "current": points[-1]["value"],
        "previous": points[-2]["value"],
        "yearAgo": value_nearest(points, latest - timedelta(days=365)),
        "history": points[-HISTORY_POINTS:],
        "rangeLow": min(values),
        "rangeHigh": max(values),
    }


def main() -> int:
    # Optional: only needed if FRED's keyless CSV export stops working.
    key = os.environ.get("FRED_KEY", "").strip()

    try:
        products = [pack(fid, sid, name, term, key) for fid, sid, name, term in SERIES]
    except Exception as e:                      # network, shape, or sanity failure
        print(f"refresh failed: {e}", file=sys.stderr)
        return 1

    # Every product should be quoting the same day; if they drift, use the older one
    # so the app never shows a date it has no data for.
    as_of = min(p["history"][-1]["date"] for p in products)

    # Deliberately no fetch timestamp: the workflow commits only when this file
    # changes, and a timestamp would make every run look like new data.
    feed = {
        "source": "Optimal Blue",
        "asOf": as_of,
        "cadence": "daily",
        "attribution": ATTRIBUTION,
        "products": products,
    }

    with open("rates.json", "w") as f:
        json.dump(feed, f, separators=(",", ":"))
        f.write("\n")

    print(f"wrote rates.json as of {as_of}: " + ", ".join(f"{p['id']}={p['current']}" for p in products))
    return 0


if __name__ == "__main__":
    sys.exit(main())
