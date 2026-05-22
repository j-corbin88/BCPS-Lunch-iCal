#!/usr/bin/env python3
"""
BCPS Lunch Menu → iCal Generator
Fetches the current + next week's menu from Nutrislice and writes lunch.ics
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
import uuid

# ── Configuration ────────────────────────────────────────────────────────────
DISTRICT    = "bcps"
SCHOOL_SLUG = "bcps-weekly-menus"
MENU_TYPE   = "weekly-menus"
OUTPUT_FILE = "lunch.ics"
CALENDAR_NAME = "BCPS Daily Schedule"
WEEKS_AHEAD = 4
# ─────────────────────────────────────────────────────────────────────────────

BREAKFAST_KEYWORDS = [
    "waffle", "pancake", "muffin", "bagel", "cereal", "oatmeal",
    "granola", "french toast", "breakfast", "biscuit", "donut",
    "pop tart", "cinnamon", "cocoa puff", "lucky charm", "cheerio",
    "fruit juice", "juice", "yogurt", "egg"
]

LUNCH_EXCLUDES = [
    "assorted savory bread"
]


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def fetch_week(monday: date) -> dict | None:
    url = (
        f"https://{DISTRICT}.api.nutrislice.com/menu/api/weeks/school/"
        f"{SCHOOL_SLUG}/menu-type/{MENU_TYPE}/"
        f"{monday.year}/{monday.month:02d}/{monday.day:02d}/"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def extract_lunch_items(menu_items: list) -> list[str]:
    seen = set()
    items = []
    for item in menu_items:
        food = item.get("food")
        if not food:
            continue
        name = food.get("name", "").strip()
        if not name:
            continue
        if food.get("food_category") != "entree":
            continue
        name_lower = name.lower()
        if any(kw in name_lower for kw in BREAKFAST_KEYWORDS):
            continue
        if any(kw in name_lower for kw in LUNCH_EXCLUDES):
            continue
        if name not in seen:
            seen.add(name)
            items.append(name)
    return items


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
        "PRODID:-//BCPS Lunch Bot//EN",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
        "X-WR-TIMEZONE:America/New_York",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for ev in events:
        date_str = ev["date"].strftime("%Y%m%d")
        summary = ical_escape(ev["summary"])
        description = ical_escape(ev["description"])
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bcps-lunch-{ev['date'].isoformat()}"))

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

    for week_offset in range(WEEKS_AHEAD):
        target_monday = monday + timedelta(weeks=week_offset)
        print(f"Fetching week of {target_monday}...")
        data = fetch_week(target_monday)
        if not data:
            print("  No data returned, skipping.")
            continue

        days = data.get("days", [])
        for day_data in days:
            day_date_str = day_data.get("date")
            if not day_date_str:
                continue

            try:
                day_date = date.fromisoformat(day_date_str[:10])
            except ValueError:
                continue

            if day_date.weekday() >= 5:
                continue

            menu_items = day_data.get("menu_items", [])
            if not menu_items:
                continue

            items = extract_lunch_items(menu_items)
            if not items:
                continue

            primary = items[0]
            summary = f"🍽  {primary}"
            if len(items) > 1:
                summary += f" (+{len(items)-1} more)"

            description = "\n".join(f"• {e}" for e in items)

            all_events.append({
                "date": day_date,
                "summary": summary,
                "description": description,
            })
            print(f"  {day_date}: {', '.join(items)}")

    if not all_events:
        print("No menu events found.")
        return

    ical_content = build_ical(all_events)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ical_content)

    print(f"\n✅ Written {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
