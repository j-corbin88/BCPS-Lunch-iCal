#!/usr/bin/env python3
"""
Loyola Blakefield Lunch Menu → iCal Generator
Uses Playwright to scrape LunchTab and writes loyola-lunch.ics
"""

import os
import re
import uuid
from datetime import datetime, date, timedelta
from playwright.sync_api import sync_playwright

# ── Configuration ────────────────────────────────────────────────────────────
LUNCHTAB_URL   = "https://loyolablakefield.lunchtab.app/menus/1/?salesBusinessTypeName=Cafeteria"
EMAIL          = os.environ["LUNCHTAB_EMAIL"]
PASSWORD       = os.environ["LUNCHTAB_PASSWORD"]
OUTPUT_FILE    = "loyola-lunch.ics"
CALENDAR_NAME  = "Loyola Blakefield Daily Schedule"
WEEKS_AHEAD    = 4
# ─────────────────────────────────────────────────────────────────────────────


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


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


def parse_date_from_heading(heading: str) -> date | None:
    """Parse 'Monday 14th September' or 'Monday 14th September 2026' into a date."""
    # Strip ordinal suffixes
    heading = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", heading)
    for fmt in ("%A %d %B %Y", "%A %d %B"):
        try:
            parsed = datetime.strptime(heading.strip(), fmt)
            if fmt == "%A %d %B":
                parsed = parsed.replace(year=date.today().year)
            return parsed.date()
        except ValueError:
            continue
    return None


def scrape_week(page, target_monday: date) -> list[dict]:
    """Navigate to a specific week and scrape menu items."""
    # Set the week date in the input field
    week_str = target_monday.strftime("%m/%d/%Y")
    print(f"  Setting week to {week_str}...")

    # Click the week input and set its value
    week_input = page.locator("input[type='date'], input[placeholder*='week'], input[placeholder*='Week']").first
    if week_input.count() == 0:
        # Try finding by label
        week_input = page.get_by_label("Week").first

    try:
        week_input.fill(target_monday.strftime("%Y-%m-%d"))
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  Could not set week input: {e}")

    events = []
    # Find all day cards
    day_cards = page.locator("div[class*='card'], div[class*='day'], section[class*='day']").all()

    # Fallback: find by heading pattern
    headings = page.locator("text=/Monday|Tuesday|Wednesday|Thursday|Friday/").all()
    print(f"  Found {len(headings)} day headings")

    for heading_el in headings:
        try:
            heading_text = heading_el.inner_text().strip()
            day_date = parse_date_from_heading(heading_text)
            if not day_date:
                print(f"  Could not parse date from: {heading_text}")
                continue

            # Skip weekends
            if day_date.weekday() >= 5:
                continue

            # Get the parent card containing this heading
            card = heading_el.locator("xpath=ancestor::*[contains(@class,'card') or contains(@class,'day') or contains(@class,'week')]").last
            if card.count() == 0:
                card = heading_el.locator("xpath=../..")

            card_text = card.inner_text()

            # Extract item lines — skip the heading itself and "No items" messages
            lines = [
                l.strip() for l in card_text.split("\n")
                if l.strip()
                and l.strip() != heading_text
                and "no items" not in l.lower()
                and len(l.strip()) > 2
            ]

            # Deduplicate (LunchTab shows name twice — bold + normal)
            seen = set()
            items = []
            for line in lines:
                if line.lower() not in seen:
                    seen.add(line.lower())
                    items.append(line)

            if not items:
                print(f"  {day_date}: no items")
                continue

            primary = items[0]
            summary = f"🎓 {primary}"
            if len(items) > 1:
                summary += f" (+{len(items)-1} more)"

            description = "\n".join(f"• {i}" for i in items)

            events.append({
                "date": day_date,
                "summary": summary,
                "description": description,
            })
            print(f"  {day_date}: {', '.join(items)}")

        except Exception as e:
            print(f"  Error parsing day: {e}")
            continue

    return events


def main():
    all_events = []
    today = date.today()
    monday = get_monday(today)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to LunchTab...")
        page.goto(LUNCHTAB_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Check if login is required
        if "login" in page.url.lower() or page.locator("input[type='email'], input[type='password']").count() > 0:
            print("Login required, authenticating...")
            # Fill email
            email_input = page.locator("input[type='email']").first
            email_input.fill(EMAIL)

            # Fill password
            password_input = page.locator("input[type='password']").first
            password_input.fill(PASSWORD)

            # Submit
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            print(f"  Logged in, now at: {page.url}")

            # Navigate to menu page after login
            page.goto(LUNCHTAB_URL, wait_until="networkidle")
            page.wait_for_timeout(2000)

        # Select the most recent/current menu from dropdown
        print("Selecting current menu...")
        try:
            menu_dropdown = page.locator("select").first
            if menu_dropdown.count() > 0:
                # Get all options
                options = menu_dropdown.locator("option").all()
                option_texts = [o.inner_text() for o in options]
                print(f"  Menu options: {option_texts}")
                # Select the first option (most current)
                menu_dropdown.select_option(index=0)
                page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  Dropdown error: {e}")

        # Scrape each week
        for week_offset in range(WEEKS_AHEAD):
            target_monday = monday + timedelta(weeks=week_offset)
            print(f"\nFetching week of {target_monday}...")
            events = scrape_week(page, target_monday)
            all_events.extend(events)

        browser.close()

    if not all_events:
        print("No menu events found.")
        return

    ical_content = build_ical(all_events)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ical_content)

    print(f"\n✅ Written {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
