#!/usr/bin/env python3
"""
Cole's Loyola Calendar Splitter
Fetches two iCal feeds and splits into:
- cole-classes.ics: daily class periods
- cole-assignments.ics: homework, quizzes, tests (no participation)
- loyola-activities.ics: school-wide activities and events
"""

import uuid
import re
import urllib.request
from datetime import datetime, date, timedelta

COLE_URL       = "https://loyolablakefield.myschoolapp.com/podium/feed/iCal.aspx?z=k6iFwgj9%2fEhEfcHbQ22wmoztitIrCRWyqm3Zq3cJiA0HYpbk5UEaR%2b1DMmp%2fNwzfWse9IV6dQly4TXEzoMlDmA%3d%3d"
LOYOLA_URL     = "https://loyolablakefield.myschoolapp.com/podium/feed/iCal.aspx?z=4v3FTQSOQLhVE7HULRWuIlXF7Qq8mOIyhBfETVEyH4I%2fodvKb2dTEnQjMZnc75Pi%2b7yRatmAORt2Q6P3dPtmVA%3d%3d"

OUTPUT_CLASSES     = "cole-classes.ics"
OUTPUT_ASSIGNMENTS = "cole-assignments.ics"
OUTPUT_ACTIVITIES  = "loyola-activities.ics"

PARTICIPATION_KEYWORDS = [
    "participation",
    "class participation",
    "quarter participation",
]

DAY_LABEL_KEYWORDS = [
    "a day", "b day", "c day", "d day", "e day",
    "late start",
]

REMOVE_SPORT_LEVELS = [
    "middle school",
    "junior varsity",
    "freshman",
    " jv ",
]

REMOVE_SPORTS = [
    "water polo",
    "cross country",
]

REMOVE_NOISE_KEYWORDS = [
    "total # of student days",
    "q1 grades due",
    "q2 grades due",
    "q3 grades due",
    "q4 grades due",
    "report cards go live",
    "conference site",
    "department chair",
    "professional development",
    "grades due",
    "end date to drop",
    "drop down",
    "paying for college",
    "aims ",
    "don for a day",
]

REMOVE_SENIOR_KEYWORDS = [
    "senior prom",
    "senior trip",
    "senior exam",
    "senior grades",
    "senior mother",
    "baccalaureate",
    "graduation rehearsal",
    "graduation",
    "50th reunion",
    "senior prom experience",
]


def fetch_ical(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_events(ical_text):
    events = []
    current = {}
    in_event = False
    current_key = None
    current_val = ""

    for line in ical_text.splitlines():
        if line.startswith((" ", "\t")) and current_key:
            current_val += line[1:]
            continue

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
    dtstart = event.get("DTSTART", "")
    return "T" not in dtstart


def collapse_to_due_date(event):
    dtstart = event.get("DTSTART", "")
    dtend = event.get("DTEND", "")

    if not dtstart or not dtend or "T" in dtstart:
        return event

    try:
        start = date.fromisoformat(dtstart[:8])
        end = date.fromisoformat(dtend[:8])
    except ValueError:
        return event

    if (end - start).days > 1:
        due = (end - timedelta(days=1)).strftime("%Y%m%d")
        next_day = end.strftime("%Y%m%d")
        event["DTSTART"] = due
        event["DTEND"] = next_day
        print(f"  Collapsed to due date {due}: {event.get('SUMMARY', '')}")

    return event


def shorten_title(title):
    match = re.match(r"^.+?-\s*([A-Z]+)\s*\d+\s*-\s*\d+\s*:\s*(.+)$", title)
    if match:
        return f"{match.group(1)}: {match.group(2).strip()}"

    match = re.match(r"^.+?-\s*([A-Z]+)\s*\d+\s*:\s*(.+)$", title)
    if match:
        return f"{match.group(1)}: {match.group(2).strip()}"

    return title


def should_keep_activity(title):
    t = title.lower()

    if any(t == kw or t.startswith(kw + " ") for kw in DAY_LABEL_KEYWORDS):
        return False

    if any(kw in t for kw in REMOVE_SPORT_LEVELS):
        return False

    if any(kw in t for kw in REMOVE_SPORTS):
        return False

    if any(kw in t for kw in REMOVE_NOISE_KEYWORDS):
        return False

    if any(kw in t for kw in REMOVE_SENIOR_KEYWORDS):
        return False

    return True


def make_ical(events, cal_name):
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
        for key, val in ev.items():
            lines.append(f"{key}:{val}")
        if "UID" not in ev:
            lines.append(f"UID:{uuid.uuid4()}@cole-loyola")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    print("Fetching Cole's calendar...")
    cole_ical = fetch_ical(COLE_URL)
    cole_events = parse_events(cole_ical)
    print(f"  Parsed {len(cole_events)} events")

    print("Fetching Loyola activities calendar...")
    loyola_ical = fetch_ical(LOYOLA_URL)
    loyola_events = parse_events(loyola_ical)
    print(f"  Parsed {len(loyola_events)} events")

    classes = []
    assignments = []

    for ev in cole_events:
        title = ev.get("SUMMARY", "")
        title_lower = title.lower()

        if any(kw in title_lower for kw in PARTICIPATION_KEYWORDS):
            print(f"  Skipping participation: {title}")
            continue

        if not is_all_day(ev):
            classes.append(ev)
        else:
            if any(kw in title_lower for kw in DAY_LABEL_KEYWORDS):
                print(f"  Skipping day label: {title}")
                continue

            ev = collapse_to_due_date(ev)
            ev["SUMMARY"] = shorten_title(title)
            assignments.append(ev)

    activities = []
    for ev in loyola_events:
        title = ev.get("SUMMARY", "").strip()
        if any(kw in title.lower() for kw in PARTICIPATION_KEYWORDS):
            continue
        if not should_keep_activity(title):
            print(f"  Removing: {title}")
            continue
        activities.append(ev)

    print(f"\nClasses: {len(classes)} events")
    print(f"Assignments: {len(assignments)} events")
    print(f"Activities: {len(activities)} events")

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
