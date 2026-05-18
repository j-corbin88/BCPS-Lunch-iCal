# 🍽 BCPS Lunch Calendar

Automatically fetches the weekly BCPS lunch menu from Nutrislice and generates a
subscribable `.ics` calendar file — updated every Sunday night.

## Setup (one-time, ~10 minutes)

### 1. Create a GitHub account

If you don’t have one: [github.com/signup](https://github.com/signup)

### 2. Create a new repository

- Go to [github.com/new](https://github.com/new)
- Name it something like `bcps-lunch-cal`
- Set it to **Public** (required for free GitHub Pages hosting)
- Click **Create repository**

### 3. Add the files

Upload these three files to your repo:

- `generate_ical.py` — the scraper script
- `.github/workflows/lunch-ical.yml` — the automation schedule
- `README.md` — this file

### 4. Enable GitHub Pages

- Go to your repo → **Settings** → **Pages**
- Under **Source**, select **Deploy from a branch**
- Branch: `main`, folder: `/ (root)`
- Click **Save**

### 5. Run it for the first time

- Go to the **Actions** tab in your repo
- Click **Generate Lunch iCal** → **Run workflow**
- Wait ~30 seconds — a `lunch.ics` file will appear in your repo

### 6. Get your subscription URL

Your calendar URL will be:

```
https://{your-github-username}.github.io/{repo-name}/lunch.ics
```

Example:

```
https://jordan.github.io/bcps-lunch-cal/lunch.ics
```

### 7. Add to Skylight

- Open the Skylight app → **Settings** → **Calendars** → **Add Calendar**
- Choose **Subscribe via URL** (or iCal link)
- Paste your URL from step 6

-----

## Customization

Edit `generate_ical.py` to change:

|Variable       |What it does                                  |
|---------------|----------------------------------------------|
|`WEEKS_AHEAD`  |How many weeks of menu to fetch (default: 4)  |
|`CALENDAR_NAME`|Name shown in Skylight/calendar apps          |
|`DISTRICT`     |Your Nutrislice district (default: `bcps`)    |
|`SCHOOL_SLUG`  |School identifier in the Nutrislice URL       |
|`MENU_TYPE`    |Menu type slug (e.g., `lunch`, `weekly-menus`)|

### Finding your school’s slugs

Your current URL is:

```
https://bcps.nutrislice.com/menu/bcps-weekly-menus/weekly-menus
```

This maps to:

- **District**: `bcps`
- **School slug**: `bcps-weekly-menus`
- **Menu type**: `weekly-menus`

-----

## How it works

```
Every Sunday at 6 PM ET
        │
        ▼
GitHub Actions runs generate_ical.py
        │
        ▼
Script calls Nutrislice's (public) JSON API
https://bcps.api.nutrislice.com/menu/api/weeks/school/...
        │
        ▼
Builds a standard .ics file with one all-day event per school day
        │
        ▼
Commits lunch.ics back to the repo
        │
        ▼
GitHub Pages serves it at your public URL
        │
        ▼
Skylight syncs on its normal calendar refresh cycle
```

## Troubleshooting

**No events showing up?**

- Run the workflow manually from the Actions tab and check the logs
- The Nutrislice API sometimes returns empty data for future weeks — it’ll populate as the school loads menus

**Wrong school menu?**

- Update `SCHOOL_SLUG` and `MENU_TYPE` in `generate_ical.py` to match your kid’s specific school

**Skylight not updating?**

- Skylight typically refreshes subscribed calendars every few hours
- You can force a sync in the Skylight app settings