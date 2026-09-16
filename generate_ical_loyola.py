#!/usr/bin/env python3
"""
Loyola Blakefield Lunch Menu -> iCal Generator
Calls LunchTab API directly using session cookie
"""

import os
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

# Configuration
AUTH_COOKIE   = os.environ["LUNCHTAB_COOKIE"]
BASE_URL      = "https://loyolablakefield.lunchtab.app/api/v1"
OUTPUT_FILE   = "loyola-lunch.ics"
CALENDAR_NAME = "Loyola Blakefield Daily Schedule"
WEEKS_AHEAD   = 4
# Sales business type id (1 = Cafeteria)
SBT_ID        = 1


def get_monday(d):
    return d - timedelta(days=d.weekday())


def api_get(path):
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


def unwrap(data):
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


def ical_escape(text):
    return (text
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n"))


def fold(line):
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


def build_ical(events):
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Loyola Blakefield Schedule Bot//EN",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
        "X-WR-TIMEZONE:America/New_York",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for ev in events:
        date_str = ev["date"].strftime("%Y%m%d")
        summary = ical_escape(ev["summary"])
        description = ical_escape(ev["description"])
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"loyola-lunch-{ev['date'].isoformat()}"))

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{now_str}")
        lines.append(f"DTSTART;VALUE=DATE:{date_str}")
        lines.append(f"DTEND;VALUE=DATE:{date_str}")
        lines.append(fold(f"SUMMARY:{summary}"))
        lines.append(fold(f"DESCRIPTION:{description}"))
        lines.append("TRANSP:TRANSPARENT")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def fetch_week(target_monday):
    # Dates in UTC with Eastern offset (UTC-4 in summer, UTC-5 in winter)
    # Use T04:00:00.000Z (EDT) as the site does
    start = target_monday.strftime("%Y-%m-%dT04:00:00.000Z")
    end_day = target_monday + timedelta(days=6)
    end = end_day.strftime("%Y-%m-%dT03:59:59.999Z")

    path = f"/salesbusinesstypes/{SBT_ID}/menubrowserweeks/2?startDateTimeUtc={start}&endDateTimeUtc={end}"
    print(f"  Fetching: {path[:100]}...")
    data = api_get(path)
    if not data:
        return []

    print(f"  Raw sample: {json.dumps(data)[:400]}")
    return unwrap(data)


def main():
    today = date.today()
    monday = get_monday(today)
    all_events = []

    for week_offset in range(WEEKS_AHEAD):
        target_monday = monday + timedelta(weeks=week_offset)
        print(f"\nFetching week of {target_monday}...")

        items = fetch_week(target_monday)
        print(f"  Got {len(items)} items")

        if not items:
            continue

        by_date = {}
        for item in items:
            # Try various date field names
            item_date_str = (
                item.get("dateTimeUtc", "")
                or item.get("date", "")
                or item.get("menuDate", "")
            )[:10]
            if not item_date_str:
                continue
            try:
                item_date = date.fromisoformat(item_date_str)
            except ValueError:
                continue
            if item_date.weekday() >= 5:
                continue

            # Try various name field paths
            name = ""
            if item.get("menuItem"):
                name = item["menuItem"].get("name", "")
            if not name:
                name = item.get("name", "") or item.get("itemName", "")
            if not name:
                continue

            by_date.setdefault(item_date, []).append(name)

        for day_date, names in sorted(by_date.items()):
            seen = set()
            items_deduped = []
            for n in names:
                if n.lower() not in seen:
                    seen.add(n.lower())
                    items_deduped.append(n)

            primary = items_deduped[0]
            summary = f"Loyola: {primary}"
            if len(items_deduped) > 1:
                summary += f" (+{len(items_deduped)-1} more)"
            description = "\n".join(f"- {i}" for i in items_deduped)

            all_events.append({
                "date": day_date,
                "summary": summary,
                "description": description,
            })
            print(f"  {day_date}: {', '.join(items_deduped)}")

    if not all_events:
        print("No events found.")
        return

    ical_content = build_ical(all_events)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ical_content)

    print(f"\nWritten {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
