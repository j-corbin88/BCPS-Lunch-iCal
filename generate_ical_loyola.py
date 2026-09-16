#!/usr/bin/env python3
"""
Loyola Blakefield Lunch Menu → iCal Generator
Calls LunchTab API directly using session cookie
"""

import os
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

# ── Configuration ────────────────────────────────────────────────────────────
AUTH_COOKIE    = os.environ["LUNCHTAB_COOKIE"]
BASE_URL       = "https://loyolablakefield.lunchtab.app/api/v1"
OUTPUT_FILE    = "loyola-lunch.ics"
CALENDAR_NAME  = "Loyola Blakefield Daily Schedule"
WEEKS_AHEAD    = 4
# ─────────────────────────────────────────────────────────────────────────────


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def api_get(path: str) -> dict | list | None:
    url = f"{BASE_URL}{path}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Cookie": f"loyolablakefield__auth={AUTH_COOKIE}",
        "Referer": "https://loyolablakefield.lunchtab.app/menus/1/?salesBusinessTypeName=Cafeteria",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "x-csrf": "1",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            if not raw.strip():
                print(f"  Empty response for {url}")
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  HTTP {e.code} for {url}: {body}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def unwrap(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        ro = data.get("responseObject", {})
        if isinstance(ro, list):
            return ro
        if isinstance(ro, dict):
            for key in ("response", "items", "data"):
                if key in ro and isinstance(ro[key], list):
                    return ro[key]
        for key in ("response", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def sort_menus_by_relevance(menus: list) -> list:
    """Sort menus so the most likely current one comes first."""
    today = date.today()
    year = today.year
    month = today.month

    if month >= 8:
        preferred = [f"fall menu {year}", f"fall {year}"]
    elif month >= 3:
        preferred = [f"spring {year}", f"spring menu {year}"]
    else:
        preferred = [f"winter menu {year-1}-{year}", f"winter {year-1}-{year}"]

    print(f"  Preferred menu keywords: {preferred}")

    def score(m):
        name = m.get("name", "").lower()
        for i, pref in enumerate(preferred):
            if pref in name:
                return i
        # Fall back to highest id (most recently added)
        return 100 - m.get("id", 0)

    return sorted(menus, key=score)


def fetch_week_items(menu_id: int, target_monday: date) -> list:
    """Try to fetch menu items for a given week and menu id."""
    target_sunday = target_monday + timedelta(days=6)
    start = target_monday.strftime("%Y-%m-%dT00:00:00")
    end = target_sunday.strftime("%Y-%m-%dT23:59:59")

    endpoints = [
        f"/menus/{menu_id}/menuitems?startDateTimeUtc={start}&endDateTimeUtc={end}",
        f"/salesbusinesstypes/1/menus/{menu_id}/menuitems?startDateTimeUtc={start}&endDateTimeUtc={end}",
        f"/menus/{menu_id}/2?startDateTimeUtc={start}&endDateTimeUtc={end}",
    ]

    for ep in endpoints:
        print(f"  Trying endpoint: {ep[:80]}...")
        data = api_get(ep)
        if data:
            items = unwrap(data)
            if items:
                print(f"  Got {len(items)} items")
                return items
            else:
                print(f"  Raw sample: {json.dumps(data)[:300]}")

    return []


def ical_escape(text: str) -> str:
    return (text
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n"))


def fold(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    result = []
    while len(encoded) > 75:
        chunk = encoded[:75].decode("utf-8", errors="ignore")
        result.append(chunk)
        encoded = encoded[len(chunk.encode("utf-8")):]
    result.append(encoded.decode("utf-8"))
    return "\r\n ".join(result)


def build_ical(events: list[dict]) -> str:
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
