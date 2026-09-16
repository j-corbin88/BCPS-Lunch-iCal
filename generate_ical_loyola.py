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

    sorted_menus = sort_menus_by_relevance(menus)

    # Try each week, falling back through menus if needed
    for week_offset in range(WEEKS_AHEAD):
        target_monday = monday + timedelta(weeks=week_offset)
        print(f"\nFetching week of {target_monday}...")

        items = []
        used_menu = None

        for menu in sorted_menus:
            menu_id = menu.get("id")
            menu_name = menu.get("name")
            print(f"  Trying menu: {menu_name} (id={menu_id})")
            items = fetch_week_items(menu_id, target_monday)
            if items:
                used_menu = menu_name
                break

        if not items:
            print(f"  No items found for week of {target_monday} in any menu")
            continue

        print(f"  Using menu: {used_menu}")

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
