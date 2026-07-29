# Daily Sports Brief

A dashboard that rebuilds itself every morning with **yesterday's final scores**,
**computed standout individual performances**, and **top stories** across MLB, NFL,
NBA, NHL, WNBA, college football/basketball, soccer, F1, golf, and tennis.

## Setup

```bash
cd ~/Desktop/sports-dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.main --open          # yesterday
python -m src.main --date 2026-07-28 --open
```

Schedule it (7:15am daily):

```bash
chmod +x scripts/*.sh
./scripts/install-schedule.sh 7 15
```

The built page lands at `out/dashboard.html`, with a dated copy in `out/archive/`.
Bookmark the `out/dashboard.html` file path in your browser and it will always
show the latest build.

## How it works, and why it's built this way

**Data source: ESPN's public JSON API, not scraped HTML.**
`site.api.espn.com/apis/site/v2/sports/{sport}/{league}/...` powers ESPN's own
apps. It has been stable for years, needs no key, and returns full box scores.
Scraping ESPN's or CBS's rendered pages instead would work until their next
redesign and then break silently — which is the failure mode that kills these
projects.

**Standouts are computed, not borrowed.** `src/standouts.py` reads each player's
actual stat line and applies explicit per-sport thresholds (3-homer game, triple-
double, hat trick, 350+ passing yards, 14-strikeout start...). Each triggered rule
adds to a 0–100 "wow score." This is deliberate: headlines track market size, so a
Yankees player having a good night outranks a Royals player having a great one. The
box score doesn't care who you play for.

Rough calibration:

| score | meaning |
|-------|---------|
| ~40   | worth a mention |
| ~65   | clearly a big night |
| ~85+  | you'd have texted someone about it |

Tune the thresholds in `src/standouts.py` and the cutoff in `config.yaml`
(`standouts.min_score`). **You should expect to tune these** — thresholds are
opinions, and yours will differ from mine after a week of looking at the output.

**Stats are read by column label, never by index.** ESPN reorders columns between
sports and occasionally between seasons. Index-based parsing is how scripts like
this rot after six months.

**Per-league floor.** If a league played games but nobody cleared the bar, the best
performance is shown anyway, tagged "best of the *X* slate." Without this you can't
distinguish "quiet night" from "the fetch broke."

## Known limits — read these before you trust it

- **Soccer, golf, tennis, and F1 have no per-player box score** in ESPN's summary
  payload, so they fall back to ESPN's own game leaders and score a flat 35. They
  will essentially never appear in the standouts section. Fixing this properly
  means parsing `keyEvents` for soccer goals and a different endpoint shape for
  the individual sports. It's the most obvious next piece of work.
- **Seasonality.** In late July only MLB and WNBA are live, so the page is thin.
  Out-of-season leagues cost one cheap API call and render nothing.
- **College slates are trimmed** to 12 games (ranked teams and close finals first)
  via `top_only: true` in `config.yaml`. Set it false to see all ~60.
- **The cache is aggressive** (6 hours, `src/espn.py`). Yesterday's finals never
  change, so this is safe — but pass `--no-cache` when you're debugging a parser
  and wondering why your change did nothing.
- **These endpoints are undocumented.** ESPN can change or restrict them without
  notice. If everything goes empty at once, that's the first thing to check.

## Layout

```
config.yaml           leagues, thresholds, output settings
src/espn.py           HTTP client: caching, retries, pacing
src/collect.py        scoreboard/news -> normalized Game/Story objects
src/standouts.py      the scoring rules (this is the interesting file)
src/main.py           CLI entry point
templates/            single-file HTML template
scripts/              run + launchd install
out/                  dashboard.html and dated archive
```

## Fully automated (GitHub Actions + Pages)

The laptop is the weak link in the launchd setup: it sleeps, and a scheduled
job on a sleeping laptop is a scheduled job that doesn't run. `.github/workflows/daily.yml`
moves the build to GitHub's runners, publishes the page to GitHub Pages, and
emails it to you.

```bash
brew install gh && gh auth login
./scripts/setup-github.sh sports-dashboard ljdolibois@gmail.com
```

You'll be prompted for a **Gmail App Password** — a 16-character string from
https://myaccount.google.com/apppasswords, not your account password. Google
blocks normal passwords for SMTP, and this requires 2-Step Verification to be
enabled first. If you'd rather not, delete the "Email the dashboard" step from
the workflow; Pages publishing works without it.

Then:

```bash
gh workflow run 'Daily sports brief'
gh run watch
```

The page lands at `https://<your-username>.github.io/sports-dashboard/`.

### Why `--fail-if-empty` exists

This code fails soft on purpose — one league erroring must not kill the build.
The cost of that choice is that a broken parser yields a clean, attractive,
completely empty dashboard, and you'd read a stale page for a week without
noticing. The scheduled run passes `--fail-if-empty`, which exits non-zero when:

- zero games **and** zero stories came back from every league (no innocent
  explanation for that — the API changed), or
- every enabled league errored (network or endpoint failure).

Zero games *alone* only logs a warning, because a handful of genuinely dead
sports days exist each year. GitHub emails you on workflow failure by default,
so a non-zero exit is the alert.

### Things to know before you rely on it

- **GitHub cron is best-effort.** Runs land 5–20 minutes late under load and
  slots are occasionally skipped. Irrelevant for a yesterday-in-review page.
- **No DST handling.** `15 12 * * *` is 7:15am Central in summer, 6:15am in
  winter. Adjust the cron in November if that bothers you.
- **A public repo means a public dashboard URL.** It's sports scores, but the
  URL is guessable. Private repos can't use Pages on the free plan — you'd
  keep the email step and drop the deploy job.
- **No archive on Pages.** Each run replaces the page. `out/archive/` only
  accumulates on local runs. Committing archives back to the repo daily would
  work but adds a bot commit and merge-conflict surface for little gain.
