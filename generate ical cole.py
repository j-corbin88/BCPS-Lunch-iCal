#!/usr/bin/env python3
"""
Cole's Loyola Calendar Splitter
Fetches two iCal feeds and splits into:
- cole-classes.ics: daily class periods
- cole-assignments.ics: homework, quizzes, tests (no participation)
- loyola-activities.ics: school-wide activities and events
"""

import uuid
import urllib.request
from datetime import datetime, date

COLE_URL       = "https://loyolablakefield.myschoolapp.com/podium/feed/iCal.aspx?z=k6iFwgj9%2fEhEfcHbQ22wmoztitIrCRWyqm3Zq3cJiA0HYpbk5UEaR%2b1DMmp%2fNwzfWse9IV6dQly4TXEzoMlDmA%3d%3d"
LOYOLA_URL     = "https://loyolablakefield.myschoolapp.com/podium/feed/iCal.aspx?z=4v3FTQSOQLhVE7HULRWuIlXF7Qq8mOIyhBfETVEyH4I%2fodvKb2dTEnQjMZnc75Pi%2b7yRatmAORt2Q6P3dPtmVA%3d%3d"

OUTPUT_CLASSES     = "cole-classes.ics"
OUTPUT_ASSIGNMENTS = "cole-assignments.ics"
OUTPUT_ACTIVITIES  = "loyola-activities.ics"

# Keywords that indicate participation grades — filter these out
PARTICIPATION_KEYWORDS = [
    "participation",
    "class participation",
    "quarter participation",
]

# Keywords that indicate it's a timed class period (not all-day)
# These come through as non-all-day events with period info in title
CLASS_KEYWORDS = [
    "(period", "(homeroom", "(recess", "(lunch",
]

# All-day events to exclude from assignments (day labels, etc.)
DAY_LABEL_KEYWORDS = [
    "a day", "b day", "c day", "d day", "e day",
    "late start", "no school", "holiday",
]


def fetch_ical(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_events(ical_text):
    """Parse raw iCal text into a list of event dicts."""
    events = []
    current = {}
    in_event = False
    current_key = None
    current_val = ""

    for line in ical_text.splitlines():
        # Handle line folding (continuation lines start with space or tab)
        if line.startswith((" ", "\t")) and current_key:
            current_val += line[1:]
            continue

        # Save previous key/val
        if current_key and in_event:
            current[current_key] = current_val

        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
            current_key = None
            current_val = ""
        elif line == "END:VEVENT":
            if current_key:
                current[current_key] = current_val
            in_event = False
            events.append(current)
            current = {}
            current_key = None
            current_val = ""
        elif in_event and ":" in line:
            idx = line.index(":")
            current_key = line[:idx].split(";")[0].upper()
            current_val = line[idx+1:]
        else:
            current_key = None
            current_val = ""

    return events


def is_all_day(event):
    """True if the event is an all-day event."""
    dtstart = event.get("DTSTART", "")
    # All-day events have DATE format (no T), not DATETIME
    return "T" not in dtstart


def title_contains(event, keywords):
    title = event.get("SUMMARY", "").lower()
    return any(kw in title for kw in keywords)


def make_ical(events, cal_name):
    """Build an iCal string from a list of parsed event dicts."""
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Cole Loyola {cal_name}//EN",
        f"X-WR-CALNAME:{cal_name}",
        "X-WR-TIMEZONE:America/New_York",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for ev in events:
        lines.append("BEGIN:VEVENT")
        # Preserve all original fields
        for key, val in ev.items():
            if key in ("SUMMARY", "DESCRIPTION", "LOCATION"):
                lines.append(f"{key}:{val}")
            else:
                lines.append(f"{key}:{val}")
        # Ensure UID exists
        if "UID" not in ev:
            lines.append(f"UID:{uuid.uuid4()}@cole-loyola")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    # Fetch Cole's calendar (classes + assignments)
    print("Fetching Cole's calendar...")
    cole_ical = fetch_ical(COLE_URL)
    cole_events = parse_events(cole_ical)
    print(f"  Parsed {len(cole_events)} events")

    # Fetch Loyola school activities calendar
    print("Fetching Loyola activities calendar...")
    loyola_ical = fetch_ical(LOYOLA_URL)
    loyola_events = parse_events(loyola_ical)
    print(f"  Parsed {len(loyola_events)} events")

    # Split Cole's events
    classes = []
    assignments = []

    for ev in cole_events:
        title = ev.get("SUMMARY", "").lower()

        # Skip participation events entirely
        if any(kw in title for kw in PARTICIPATION_KEYWORDS):
            print(f"  Skipping participation: {ev.get('SUMMARY', '')}")
            continue

        if not is_all_day(ev):
            # Timed event = class period
            classes.append(ev)
        else:
            # All-day event = assignment/quiz/test/homework
            # Skip day labels
            if any(kw in title for kw in DAY_LABEL_KEYWORDS):
                print(f"  Skipping day label: {ev.get('SUMMARY', '')}")
                continue
            assignments.append(ev)

    # Filter Loyola activities — remove participation if any
    activities = []
    for ev in loyola_events:
        title = ev.get("SUMMARY", "").lower()
        if any(kw in title for kw in PARTICIPATION_KEYWORDS):
            continue
        activities.append(ev)

    print(f"\nClasses: {len(classes)} events")
    print(f"Assignments: {len(assignments)} events")
    print(f"Activities: {len(activities)} events")

    # Write output files
    with open(OUTPUT_CLASSES, "w", encoding="utf-8") as f:
        f.write(make_ical(classes, "Cole's Class Schedule"))
    print(f"Written {OUTPUT_CLASSES}")

    with open(OUTPUT_ASSIGNMENTS, "w", encoding="utf-8") as f:
        f.write(make_ical(assignments, "Cole's Assignments"))
    print(f"Written {OUTPUT_ASSIGNMENTS}")

    with open(OUTPUT_ACTIVITIES, "w", encoding="utf-8") as f:
        f.write(make_ical(activities, "Loyola Activities"))
    print(f"Written {OUTPUT_ACTIVITIES}")


if __name__ == "__main__":
    main()
