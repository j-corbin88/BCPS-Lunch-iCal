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
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def unwrap(data) -> list:
    """Extract the list from LunchTab's nested response envelope."""
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

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_str}",
            f"DTSTART;VALUE=DATE:{date_str}",
            f"DTEND;VALUE=DATE:{date_str}",
            fold(f"SUMMARY:{summary}"),
            fold(f"DESCRIPTION:{description}"),
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    today = date.today()
    monday = get_monday(today)
    all_events = []

    # Fetch all menus
    print("Fetching menu list...")
    menus_data = api_get("/salesbusinesstypes/1/menus?pageNumber=1&pageSize=300&isPublished=true&hideFromMenuBrowsers=false")
    if not menus_data:
        print("Failed to fetch menus.")
        return

    menus = unwrap(menus_data)
    print(f"  Found {len(menus)} menus")

    for m in menus:
        print(f"  Menu: {m.get('name')} (id={m.get('id')})")

    # Pick the first published menu (most current)
    current_menu = menus[0] if menus else None
    if not current_menu:
        print("No menu found.")
        return

    menu_id = current_menu.get("id")
    print(f"Using menu: {current_menu.get('name')} (id={menu_id})")

    # Fetch menu items for each week
    for week_offset in range(WEEKS_AHEAD):
        target_monday = monday + timedelta(weeks=week_offset)
        target_sunday = target_monday + timedelta(days=6)
        print(f"\nFetching week of {target_monday}...")

        start = target_monday.strftime("%Y-%m-%dT00:00:00")
        end = target_sunday.strftime("%Y-%m-%dT23:59:59")

        data = api_get(f"/menus/{menu_id}/menuitems?startDateTimeUtc={start}&endDateTimeUtc={end}")
        if not data:
            print("  No data.")
            continue

        print(f"  Raw sample: {json.dumps(data)[:300]}")

        items = unwrap(data)
        print(f"  Got {len(items)} items")

        # Group by date
        by_date = {}
        for item in items:
            item_date_str = item.get("dateTimeUtc", item.get("date", ""))[:10]
            if not item_date_str:
                continue
            try:
                item_date = date.fromisoformat(item_date_str)
            except ValueError:
                continue
            if item_date.weekday() >= 5:
                continue
            name = (item.get("menuItem", {}) or {}).get("name", "") or item.get("name", "")
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
            summary = f"🎓 {primary}"
            if len(items_deduped) > 1:
                summary += f" (+{len(items_deduped)-1} more)"
            description = "\n".join(f"• {i}" for i in items_deduped)

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

    print(f"\n✅ Written {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
