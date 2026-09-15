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
                clicked =
