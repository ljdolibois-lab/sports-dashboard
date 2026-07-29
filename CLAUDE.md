# Context for Claude Code

Daily sports dashboard. Python 3.11+, no framework, no database. Reads ESPN's
public JSON API and writes one static HTML file.

## Run it

```bash
source .venv/bin/activate
python -m src.main --date 2026-07-28 --no-cache --open
```

`--no-cache` matters when iterating on parsers: `src/espn.py` caches responses
for 6 hours, so without it your parser change will appear to do nothing.

## Design rules — please don't violate these

1. **Never scrape HTML.** Everything comes from `site.api.espn.com`. If a piece
   of data isn't in the JSON, find a different JSON endpoint rather than
   reaching for BeautifulSoup. The whole point is that this doesn't break on a
   site redesign.
2. **Read box-score stats by column label, never by index.** Use the `_g(row, ...)`
   helper in `src/standouts.py`. ESPN reorders columns across sports and seasons.
3. **Don't use headlines to decide what was impressive.** Standouts are computed
   from stat lines. Headlines are a separate, clearly-labeled section.
4. **Fail soft, per league.** One league's endpoint erroring must never abort the
   build. Errors accumulate in `DayResult.errors` and render in the page footer.
5. **The template is a single self-contained file.** No build step, no CDN, no
   local storage. It must open correctly from `file://`.

## Where things live

- `src/espn.py` — HTTP + disk cache + retries. Change `CACHE_TTL` here.
- `src/collect.py` — normalizes scoreboard/news payloads into `Game` / `Story` /
  `Standout` lists. Also filters postponed games and trims college slates.
- `src/standouts.py` — the scoring rules. One function per sport kind
  (`_basketball`, `_baseball`, `_football`, `_hockey`), each returning
  `(points, reasons, display_line)`.
- `templates/dashboard.html.j2` — all markup and CSS.
- `config.yaml` — leagues on/off, thresholds, news sources.

## Useful endpoints

```
/apis/site/v2/sports/{path}/scoreboard?dates=YYYYMMDD   games + per-game leaders
/apis/site/v2/sports/{path}/summary?event={id}          full box score + recap
/apis/site/v2/sports/{path}/news?limit=N                headlines
```

`{path}` examples: `baseball/mlb`, `football/nfl`, `basketball/nba`,
`hockey/nhl`, `basketball/wnba`, `football/college-football`,
`basketball/mens-college-basketball`, `soccer/eng.1`, `soccer/uefa.champions`,
`soccer/usa.1`, `racing/f1`, `golf/pga`, `tennis/atp`.

Handy probe when adding a sport:

```bash
python - <<'EOF'
import json, urllib.request
u="https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event=EVENT_ID"
d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})))
for t in d['boxscore']['players']:
    for g in t['statistics']:
        print(g.get('name') or g.get('type'), '|', g.get('labels'))
    break
EOF
```

## Known gaps (good next tasks)

- **Soccer standouts are fake.** ESPN's soccer `summary` has no `boxscore.players`
  block, so soccer falls through to `from_leaders()` at a flat score of 35 and
  never surfaces. Real fix: parse `summary['keyEvents']` for goals/assists/red
  cards and write a `_soccer()` rule.
- **Golf / tennis / F1 need their own section**, not the standouts grid — a
  leaderboard shape, not a stat line. Currently they contribute almost nothing.
- **NHL rules are untested against live data** (written from label names during
  the offseason). Verify against a real playoff game before trusting them.
- **No "how rare was this" context.** A 40-point game means something different
  in 2026 than in 2004. Season-to-date percentile would be a big upgrade over
  fixed thresholds.
- **No email/push delivery.** Currently you have to open the file.
