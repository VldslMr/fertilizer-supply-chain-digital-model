#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download daily IMF PortWatch traffic through Hormuz and Bab el-Mandeb.

This is a standalone script, similar to the earlier Suez Canal downloader.
No pip packages are required: it uses only Python's standard library.

Run from the repository root:
    python scripts/download_portwatch.py

Optional:
    python scripts/download_portwatch.py --start 2019-01-01 --end 2026-11-09

Output:
    data/raw/portwatch_hormuz_bab_daily.csv       (daily, long format)
    data/processed/portwatch_hormuz_bab_monthly.csv (monthly, wide format)
    data/processed/portwatch_metadata.json

Source: IMF PortWatch / UN Global Platform
https://portwatch.imf.org/
API: https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/
     Daily_Chokepoints_Data/FeatureServer/0/query

ATTENTION: capacity_* describes estimated ship carrying capacity (tonnes),
not actual fertilizer/urea cargo and not the quantity exported.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
PORTS = {"chokepoint4": "bab_el_mandeb", "chokepoint6": "hormuz"}
COUNTS = ["n_container", "n_dry_bulk", "n_general_cargo", "n_roro",
          "n_tanker", "n_cargo", "n_total"]
CAPACITIES = ["capacity_container", "capacity_dry_bulk",
              "capacity_general_cargo", "capacity_roro", "capacity_tanker",
              "capacity_cargo", "capacity"]
METRICS = COUNTS + CAPACITIES
DAILY_FIELDS = ["date", "portid", "portname"] + METRICS
PAGE_SIZE = 1000


def api_call(params: dict, retries: int = 5) -> dict:
    url = API + "?" + urlencode(params)
    error = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "academic-portwatch-downloader/1.0"})
            with urlopen(req, timeout=75) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise RuntimeError("PortWatch API returned an unexpected response")
            if "error" in data:
                raise RuntimeError(f"PortWatch ArcGIS error: {data['error']}")
            return data
        except HTTPError as exc:
            error = exc
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (URLError, TimeoutError, ConnectionError) as exc:
            error = exc
        if attempt < retries - 1:
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Cannot download PortWatch data: {error}")


def normalize_date(value) -> date:
    if isinstance(value, (int, float)):
        # Other ArcGIS layers may return epoch milliseconds.
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
    if isinstance(value, str):
        # This layer normally returns a DateOnly string: 'YYYY-MM-DD'.
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    raise ValueError(f"Unrecognized PortWatch date: {value!r}")


def download_port(portid: str, start_year: int) -> list[dict]:
    where = f"portid = '{portid}' AND year >= {start_year}"
    count_result = api_call({"where": where, "returnCountOnly": "true", "f": "json"})
    expected = count_result.get("count")
    if not isinstance(expected, int) or expected <= 0:
        raise RuntimeError(f"No server row count for {portid}: {count_result}")
    print(f"  {portid} ({PORTS[portid]}): {expected} records on the server", flush=True)

    result = []
    offset = 0
    while offset < expected:
        answer = api_call({
            "where": where,
            "outFields": ",".join(["ObjectId"] + DAILY_FIELDS),
            "returnGeometry": "false",
            "orderByFields": "ObjectId ASC",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "json",
        })
        features = answer.get("features")
        if not isinstance(features, list) or not features:
            raise RuntimeError(f"Empty/invalid page for {portid}, offset={offset}")
        result.extend(obj["attributes"] for obj in features)
        offset += len(features)
        print(f"  {portid}: {offset}/{expected}", flush=True)

    if len(result) != expected:
        raise RuntimeError(f"Incomplete download for {portid}: {len(result)} != {expected}")
    return result


def prepare_daily(records: list[dict], start: date, end: date) -> tuple[list[dict], int]:
    # Keep latest ObjectId for duplicated (date, portid); no modeling/data fitting.
    unique = {}
    duplicate_count = 0
    for item in records:
        missing = set(DAILY_FIELDS) - set(item)
        if missing:
            raise RuntimeError(f"Missing PortWatch columns: {sorted(missing)}")
        dt = normalize_date(item["date"])
        if not start <= dt <= end:
            continue
        portid = str(item["portid"]).strip().lower()
        if portid not in PORTS:
            raise RuntimeError(f"Unexpected port ID: {portid}")
        row = {k: item.get(k) for k in DAILY_FIELDS}
        row["date"] = dt.isoformat()
        row["portid"] = portid
        for col in METRICS:
            val = row[col]
            if val is None or val == "":
                row[col] = ""  # Do not turn missing values into zero.
                continue
            try:
                num = float(val)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Non-numeric {col} on {dt}: {val!r}") from exc
            if col in COUNTS:
                if not num.is_integer() or num < 0:
                    raise ValueError(f"Invalid vessel count {col} on {dt}: {val}")
                row[col] = int(num)
            else:
                row[col] = num
        key = (row["date"], portid)
        if key in unique:
            duplicate_count += 1
        unique[key] = (int(item.get("ObjectId") or 0), row)
    daily = [r for _, r in (entry for _, entry in sorted(unique.items()))]
    if not daily:
        raise RuntimeError("The downloaded API response contained no observations in range")
    missing_ports = set(PORTS) - {r["portid"] for r in daily}
    if missing_ports:
        raise RuntimeError(f"No observations for ports: {missing_ports}")
    return daily, duplicate_count


def month_starts(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield date(year, month, 1)
        month += 1
        if month > 12:
            year, month = year + 1, 1


def monthly_rows(daily: list[dict], month_start: date, month_end: date):
    buckets = {}
    for row in daily:
        dt = date.fromisoformat(row["date"])
        key = (date(dt.year, dt.month, 1), row["portid"])
        buckets.setdefault(key, []).append(row)

    columns = ["date"]
    for port in PORTS.values():
        columns += [f"{port}_{metric}_mean" for metric in METRICS]
        columns += [f"{port}_days_observed", f"{port}_days_in_month", f"{port}_coverage_share"]

    results = []
    for month in month_starts(month_start, month_end):
        entry = {col: "" for col in columns}
        entry["date"] = month.isoformat()
        for portid, name in PORTS.items():
            observed = buckets.get((month, portid), [])
            if not observed:
                continue  # Missing coverage, not zero traffic.
            days_count = len({r["date"] for r in observed})
            days_in_month = calendar.monthrange(month.year, month.month)[1]
            for metric in METRICS:
                values = [float(row[metric]) for row in observed if row[metric] != ""]
                if values:
                    entry[f"{name}_{metric}_mean"] = round(sum(values) / len(values), 6)
            entry[f"{name}_days_observed"] = days_count
            entry[f"{name}_days_in_month"] = days_in_month
            entry[f"{name}_coverage_share"] = round(days_count / days_in_month, 6)
        results.append(entry)
    return columns, results


def save_csv(path: Path, fields: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {path} ({len(rows)} records)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--start", default="2019-01-01", help="daily data from YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="daily data through YYYY-MM-DD")
    parser.add_argument("--monthly-start", default="2015-04-01")
    parser.add_argument("--monthly-end", default="2026-09-01")
    args = parser.parse_args()

    if sys.version_info < (3, 9):
        parser.error("Python 3.9 or newer is required")
    try:
        start, end, mstart, mend = [date.fromisoformat(x) for x in
                                   (args.start, args.end, args.monthly_start, args.monthly_end)]
    except ValueError:
        parser.error("Expected dates in YYYY-MM-DD format")
    if start > end or mstart > mend:
        parser.error("The beginning of the interval must precede the end")

    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    print("IMF PortWatch: Hormuz + Bab el-Mandeb", flush=True)
    print(f"Daily requested period: {start} to {end}", flush=True)
    all_records = []
    for portid in PORTS:
        all_records.extend(download_port(portid, start.year))
    daily, duplicates = prepare_daily(all_records, start, end)
    if duplicates:
        print(f"WARNING: removed {duplicates} duplicate dates", flush=True)

    save_csv(root / "data/raw/portwatch_hormuz_bab_daily.csv", DAILY_FIELDS, daily)
    mcols, monthly = monthly_rows(daily, mstart, mend)
    save_csv(root / "data/processed/portwatch_hormuz_bab_monthly.csv", mcols, monthly)

    metadata = {
        "source": "IMF PortWatch / UN Global Platform",
        "api": API,
        "portids": PORTS,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "available_first_day": daily[0]["date"],
        "available_last_day": daily[-1]["date"],
        "daily_rows": len(daily), "removed_duplicates": duplicates,
        "note": "PortWatch may be delayed; n_* = vessel counts, capacity_* = estimated vessel carrying capacity, NOT transported urea.",
    }
    meta_path = root / "data/processed/portwatch_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Last available PortWatch observation: {daily[-1]['date']}")
    print("Download complete. Use the daily CSV for EDA, monthly CSV for team merge.")


if __name__ == "__main__":
    main()
