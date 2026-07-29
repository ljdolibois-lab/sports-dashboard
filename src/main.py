"""Entry point: build the daily sports dashboard.

    python -m src.main                 # yesterday (local tz)
    python -m src.main --date 2026-07-28
    python -m src.main --no-cache --open
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import collect, espn, standouts as so

ROOT = Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                    stream=sys.stderr)
log = logging.getLogger("dashboard")


def build(cfg: dict, date: datetime, *, fetch_boxscores: bool = True) -> Path:
    ymd = date.strftime("%Y%m%d")
    leagues = [l for l in cfg["leagues"] if l.get("enabled", True)]

    all_games: list[collect.Game] = []
    all_perf: list[so.Standout] = []
    errors: list[str] = []

    for lg in leagues:
        log.info("fetching %s ...", lg["label"])
        r = collect.collect_league(lg, ymd, fetch_boxscores=fetch_boxscores)
        all_games += r.games
        all_perf += r.standouts
        errors += r.errors
        if r.games:
            log.info("  %s: %d final(s), %d raw standout(s)",
                     lg["label"], len(r.games), len(r.standouts))

    scfg = cfg.get("standouts", {})
    top = so.dedupe_and_rank(all_perf,
                             min_score=scfg.get("min_score", 45),
                             limit=scfg.get("max_shown", 12))

    ncfg = cfg.get("news", {})
    stories = collect.collect_news(cfg["leagues"], ncfg.get("sources", []),
                                   ncfg.get("max_stories", 12))

    grouped: "OrderedDict[str, list[collect.Game]]" = OrderedDict()
    for lg in leagues:                       # preserve config order
        gs = [g for g in all_games if g.league_key == lg["key"]]
        if gs:
            grouped[lg["label"]] = gs

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    tpl = env.get_template("dashboard.html.j2")
    tz = ZoneInfo(cfg["output"].get("timezone", "America/Chicago"))

    html = tpl.render(
        title=cfg["output"].get("title", "Daily Sports Brief"),
        date_human=date.strftime("%A, %B %-d, %Y"),
        generated_at=datetime.now(tz).strftime("%-I:%M %p %Z"),
        standouts=top,
        games_by_league=list(grouped.items()),
        stories=stories,
        errors=errors,
    )

    out = ROOT / cfg["output"].get("path", "out/dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    # Keep a dated archive so you can scroll back through the season.
    arch = ROOT / "out" / "archive" / f"{date:%Y-%m-%d}.html"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text(html, encoding="utf-8")

    log.info("wrote %s (%d games, %d standouts, %d stories)",
             out, len(all_games), len(top), len(stories))
    build.last_counts = {"games": len(all_games), "standouts": len(top),
                         "stories": len(stories), "leagues": len(leagues),
                         "errored_leagues": len({e.split(':')[0] for e in errors})}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the daily sports dashboard.")
    ap.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--no-cache", action="store_true", help="ignore the on-disk cache")
    ap.add_argument("--no-boxscores", action="store_true",
                    help="skip per-game box scores (fast, much weaker standouts)")
    ap.add_argument("--open", action="store_true", help="open the result in a browser")
    ap.add_argument("--fail-if-empty", action="store_true",
                    help="exit non-zero on a build that looks broken rather than quiet "
                         "(for schedulers: a silent empty page is the real failure mode)")
    a = ap.parse_args()

    cfg = yaml.safe_load(Path(a.config).read_text())
    tz = ZoneInfo(cfg["output"].get("timezone", "America/Chicago"))

    if a.date:
        d = datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        d = datetime.now(tz) - timedelta(days=1)

    if a.no_cache:
        espn.CACHE_TTL = 0

    out = build(cfg, d, fetch_boxscores=not a.no_boxscores)
    print(out)
    if a.open:
        webbrowser.open(f"file://{out}")

    if a.fail_if_empty:
        c = getattr(build, "last_counts", {})
        # Why these two conditions and not "games == 0":
        #   There are a handful of genuinely dead sports days each year, so an
        #   empty score list alone is not proof of breakage. But zero games AND
        #   zero stories across every league at once has no innocent
        #   explanation - that is the API changing under us. Likewise, every
        #   single league erroring is a network or endpoint failure, not a
        #   quiet Tuesday.
        if c.get("games", 0) == 0 and c.get("stories", 0) == 0:
            log.error("SANITY CHECK FAILED: no games and no stories from any "
                      "league. The ESPN endpoints have probably changed.")
            return 2
        if c.get("errored_leagues", 0) >= c.get("leagues", 1):
            log.error("SANITY CHECK FAILED: every league errored.")
            return 2
        if c.get("games", 0) == 0:
            log.warning("no completed games found - plausible on a dead day, "
                        "but check if this repeats.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
