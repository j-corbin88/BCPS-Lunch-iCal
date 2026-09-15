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

    print("Clicking Blackbaud button...")
    clicked = False
    for selector in [
        "img[alt*='blackbaud' i]",
        "img[src*='blackbaud' i]",
        "button img[src*='blackbaud' i]",
        "[class*='blackbaud']",
        "button:has(img[src*='blackbaud' i])",
        "a:has(img[src*='blackbaud' i])",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                print(f"  Found Blackbaud element: {selector}")
                el.first.click()
                clicked = True
                break
        except Exception as e:
            print(f"  Selector {selector} failed: {e}")
            continue

    if not clicked:
        print("  Trying fallback — listing all buttons...")
        buttons = page.locator("button").all()
        print(f"  Found {len(buttons)} buttons")
        for btn in buttons:
            try:
                txt = btn.inner_text().strip().lower()
                print(f"    Button text: '{txt}'")
                if "blackbaud" in txt or "sso" in txt:
                    btn.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked and len(buttons) >= 2:
            print("  Last resort: clicking last button")
            buttons[-1].click()
            clicked = True

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL after Blackbaud click: {page.url}")
    page.screenshot(path="debug_02_after_blackbaud.png")

    print("Filling email on Blackbaud...")
    for selector in [
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='email' i]",
        "input[autocomplete='email']",
        "input[id*='email' i]",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                print(f"  Found email input: {selector}")
                el.first.fill(EMAIL)
                break
        except Exception:
            continue

    page.wait_for_timeout(500)

    print("Clicking Continue...")
    for selector in [
        "button:has-text('Continue')",
        "button[type='submit']",
        "input[type='submit']",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                print(f"  Clicking: {selector}")
                el.first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    print(f"  URL after email submit: {page.url}")
    page.screenshot(path="debug_03_after_email.png")

    print("Filling password on Blackbaud...")
    for selector in [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='password' i]",
        "input[id*='password' i]",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                print(f"  Found password input: {selector}")
                el.first.fill(PASSWORD)
                break
        except Exception:
            continue

    page.wait_for_timeout(500)

    print("Clicking Continue/Sign in...")
    for selector in [
        "button:has-text('Continue')",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "button[type='submit']",
        "input[type='submit']",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                print(f"  Clicking: {selector}")
                el.first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(4000)
                break
        except Exception:
            continue

    print(f"  URL after password submit: {page.url}")
    page.screenshot(path="debug_04_after_password.png")

    print("Navigating to menu page...")
    page.goto(LUNCHTAB_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    print(f"  URL on menu page: {page.url}")
    page.screenshot(path="debug_05_menu_page.png")


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
