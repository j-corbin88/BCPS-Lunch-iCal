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


def login(page):
    print("Navigating to LunchTab...")
    page.goto(LUNCHTAB_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL: {page.url}")
    page.screenshot(path="debug_01_initial.png")

    # Click Blackbaud button on LunchTab login page
    print("Clicking Blackbaud button...")
    page.locator("button:has-text('blackbaud'), button img[alt*='blackbaud' i]").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL after Blackbaud click: {page.url}")
    page.screenshot(path="debug_02_after_blackbaud.png")

    # On Blackbaud page — click "Continue with Email"
    print("Clicking Continue with Email...")
    page.locator("button:has-text('Continue with Email')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    print(f"  URL after email option: {page.url}")
    page.screenshot(path="debug_03_email_option.png")

    # Fill email
    print("Filling email...")
    page.locator("input[type='email'], input[name='email']").first.fill(EMAIL)
    page.wait_for_timeout(500)

    # Click Continue
    print("Clicking Continue...")
    page.locator("button:has-text('Continue')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL after email submit: {page.url}")
    page.screenshot(path="debug_04_after_email.png")

    # Fill password
    print("Filling password...")
    page.locator("input[type='password']").first.fill(PASSWORD)
    page.wait_for_timeout(500)

    # Click Continue
    print("Clicking Continue...")
    page.locator("button[type='submit'], button:has-text('Continue')").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(4000)
    print(f"  URL after password: {page.url}")
    page.screenshot(path="debug_05_after_password.png")

    # Navigate to menu
    print("Navigating to menu page...")
    page.goto(LUNCHTAB_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL on menu page: {page.url}")
    page.screenshot(path="debug_06_menu_page.png")


def scrape_week(page, target_monday: date) -> list[dict]:
    print(f"  Setting week to {target_monday.strftime('%m/%d/%Y')}...")

    try:
        for selector in [
            "input[type='date']",
            "input[placeholder*='week' i]",
            "input[placeholder*='date' i]",
        ]:
            if page.locator(selector).count() > 0:
                page.locator(selector).first.fill(target_monday.strftime("%Y-%m-%d"))
                page.keyboard.press("Enter")
                page.wait_for_timeout(2000)
                break
    except Exception as e:
        print(f"  Could not set week input: {e}")

    events = []
    headings = page.locator("text=/Monday|Tuesday|Wednesday|Thursday|Friday/").all()
    print(f"  Found {len(headings)} day headings")

    for heading_el in headings:
        try:
            heading_text = heading_el.inner_text().strip()
            day_date = parse_date_from_heading(heading_text)
            if not day_date:
                print(f"  Could not parse date from: {heading_text}")
                continue

            if day_date.weekday() >= 5:
                continue

            card = heading_el.locator("xpath=ancestor::*[contains(@class,'card') or contains(@class,'day') or contains(@class,'week')]").last
            if card.count() == 0:
                card = heading_el.locator("xpath=../..")

            card_text = card.inner_text()

            lines = [
                l.strip() for l in card_text.split("\n")
                if l.strip()
                and l.strip() != heading_text
                and "no items" not in l.lower()
                and len(l.strip()) > 2
            ]

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

        login(page)

        print("Selecting current menu...")
        try:
            menu_dropdown = page.locator("select").first
            if menu_dropdown.count() > 0:
                options = menu_dropdown.locator("option").all()
                option_texts = [o.inner_text() for o in options]
                print(f"  Menu options: {option_texts}")
                menu_dropdown.select_option(index=0)
                page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  Dropdown error: {e}")

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
