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
SBT_ID        = 1  # Cafeteria


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


def unwrap_response(data):
    """Extract the response list from LunchTab envelope."""
    if isinstance(data, dict):
        ro = data.get("responseObject", {})
        if isinstance(ro, dict):
            r = ro.get("response", [])
            if isinstance(r, list):
                return r
    return []


def get_all_menus():
    data = api_get(f"/salesbusinesstypes/{SBT_ID}/menus?pageNumber=1&pageSize=300&isPublished=true&hideFromMenuBrowsers=false")
    if not data:
        return []
    ro = data.get("responseObject", {})
    if isinstance(ro, dict):
        return ro.get("response", [])
    return []


def pick_best_menu(menus):
    """Pick the most seasonally appropriate menu, falling back by highest id."""
    today = date.today()
    month = today.month
    year = today.year

    if month >= 8:
        keywords = [f"fall menu {year}", f"fall {year}"]
    elif month >= 3:
        keywords = [f"spring {year}", f"spring menu {year}"]
    else:
        keywords = [f"winter menu {year-1}-{year}", f"winter {year-1}-{year}"]

    print(f"  Looking for: {keywords}")

    for kw in keywords:
        for m in menus:
            if kw in m.get("name", "").lower():
                return m

    # Fallback: highest id
    return max(menus, key=lambda m: m.get("id", 0)) if menus else None


def fetch_week(menu_id, target_monday):
    start = target_monday.strftime("%Y-%m-%dT04:00:00.000Z")
    end = (target_monday + timedelta(days=6)).strftime("%Y-%m-%dT03:59:59.999Z")
    path = f"/salesbusinesstypes/{SBT_ID}/menubrowserweeks/{menu_id}?startDateTimeUtc={start}&endDateTimeUtc={end}"
    print(f"  GET {path[:100]}...")
    return api_get(path)


def parse_events(data, target_monday):
    """Parse days[] from the menubrowserweeks response into events."""
    weeks = unwrap_response(data)
    if not weeks:
        return []

    events = []
    for week in weeks:
        days = week.get("days", [])
        for day in days:
            if not day.get("isOpen", True):
                continue

            day_date_str = day.get("startDateUtc", "")[:10]
            if not day_date_str:
                continue
            try:
                # The date is UTC midnight+4 = Eastern midnight, so the date is correct
                day_date = date.fromisoformat(day_date_str)
            except ValueError:
                continue

            if day_date.weekday() >= 5:
                continue

            menu_items = day.get("menuItems", [])
            if not menu_items:
                continue

            names = []
            seen = set()
            for item in sorted(menu_items, key=lambda x: x.get("displaySequence", 0)):
                name = item.get("baseProductName", "").strip()
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    names.append(name)

            if not names:
                continue

            primary = names[0]
            summary = f"Loyola: {primary}"
            if len(names) > 1:
                summary += f" (+{len(names)-1} more)"
            description = "\n".join(f"- {n}" for n in names)

            events.append({
                "date": day_date,
                "summary": summary,
                "description": description,
            })
            print(f"  {day_date}: {', '.join(names)}")

    return events


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


def main():
    today = date.today()
    monday = get_monday(today)
    all_events = []

    # Get menus and pick the best one
    print("Fetching menu list...")
    menus = get_all_menus()
    print(f"  Found {len(menus)} menus")
    for m in menus:
        print(f"  - {m.get('name')} (id={m.get('id')})")

    best_menu = pick_best_menu(menus)
    if not best_menu:
        print("No menu found.")
        return

    menu_id = best_menu.get("id")
    print(f"  Selected: {best_menu.get('name')} (id={menu_id})")

    # Fetch each week
    for week_offset in range(WEEKS_AHEAD):
        target_monday = monday + timedelta(weeks=week_offset)
        print(f"\nFetching week of {target_monday}...")

        data = fetch_week(menu_id, target_monday)
        if not data:
            print("  No data.")
            continue

        events = parse_events(data, target_monday)
        if not events:
            print("  No events parsed — trying other menus...")
            # Fallback: try other menus
            for m in sorted(menus, key=lambda x: x.get("id", 0), reverse=True):
                if m.get("id") == menu_id:
                    continue
                print(f"  Trying {m.get('name')} (id={m.get('id')})...")
                data2 = fetch_week(m.get("id"), target_monday)
                if data2:
                    events = parse_events(data2, target_monday)
                    if events:
                        print(f"  Found items in {m.get('name')}")
                        break

        all_events.extend(events)

    if not all_events:
        print("No events found.")
        return

    ical_content = build_ical(all_events)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ical_content)

    print(f"\nWritten {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
