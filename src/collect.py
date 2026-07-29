"""Turn raw ESPN payloads into the normalized shapes the template renders."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import espn, standouts as so

log = logging.getLogger(__name__)


@dataclass
class Team:
    abbr: str
    name: str
    score: int | None
    logo: str | None
    winner: bool
    record: str = ""


@dataclass
class Game:
    league: str
    league_key: str
    id: str
    label: str
    home: Team
    away: Team
    status: str
    note: str = ""          # "F/10", "Final/OT", series note, etc.
    link: str | None = None
    headline: str = ""
    ranked: bool = False
    margin: int = 999


@dataclass
class Story:
    title: str
    description: str
    link: str
    league: str
    image: str | None = None
    published: str = ""


@dataclass
class DayResult:
    games: list[Game] = field(default_factory=list)
    standouts: list[so.Standout] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _team(c: dict[str, Any]) -> Team:
    t = c.get("team") or {}
    recs = c.get("records") or []
    return Team(
        abbr=t.get("abbreviation") or t.get("shortDisplayName", "?"),
        name=t.get("displayName", "?"),
        score=int(c["score"]) if str(c.get("score", "")).lstrip("-").isdigit() else None,
        logo=t.get("logo"),
        winner=bool(c.get("winner")),
        record=(recs[0].get("summary", "") if recs else ""),
    )


def _is_ranked(c: dict[str, Any]) -> bool:
    r = c.get("curatedRank") or {}
    return bool(r.get("current") and r["current"] <= 25)


def collect_league(lg: dict[str, Any], date: str, *, fetch_boxscores: bool) -> DayResult:
    """Pull one league's finals for `date` (YYYYMMDD) plus its standouts."""
    res = DayResult()
    label, path, kind = lg["label"], lg["path"], lg["kind"]
    comp_by_id: dict[str, dict[str, Any]] = {}

    try:
        sb = espn.scoreboard(path, date)
    except espn.ESPNError as exc:
        res.errors.append(f"{label}: scoreboard unavailable ({exc})")
        return res

    for ev in sb.get("events", []) or []:
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        st = (ev.get("status") or {}).get("type") or {}
        state = st.get("state")
        if state != "post":            # only completed games
            continue
        # ESPN marks postponed/canceled/suspended games as state "post" too.
        # They have no result and must not be listed as finals.
        if st.get("name") in {"STATUS_POSTPONED", "STATUS_CANCELED",
                              "STATUS_SUSPENDED", "STATUS_RAIN_DELAY",
                              "STATUS_FORFEIT", "STATUS_ABANDONED"}:
            continue

        cs = comp.get("competitors") or []
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        h, a = _team(home), _team(away)
        margin = abs((h.score or 0) - (a.score or 0))
        heads = comp.get("headlines") or []
        link = next((l.get("href") for l in (ev.get("links") or [])
                     if "summary" in (l.get("rel") or [])), None)

        g = Game(
            league=label, league_key=lg["key"], id=ev["id"],
            label=ev.get("shortName") or ev.get("name", ""),
            home=h, away=a,
            status=st.get("shortDetail") or st.get("detail") or "Final",
            note=st.get("detail", ""),
            link=link,
            headline=(heads[0].get("shortLinkText") or heads[0].get("description", "")) if heads else "",
            ranked=_is_ranked(home) or _is_ranked(away),
            margin=margin,
        )
        res.games.append(g)
        comp_by_id[g.id] = comp

    # Trim BEFORE fetching box scores, not after. A college basketball
    # Saturday has ~350 finals; fetching a summary for every one of them to
    # then display 12 is both slow and abusive to an endpoint we don't pay for.
    max_box = int(lg.get("max_boxscores", 0) or 0)
    if lg.get("top_only") and len(res.games) > 12:
        res.games.sort(key=lambda g: (not g.ranked, g.margin))
        res.games = res.games[:12]

    box_targets = res.games if max_box <= 0 else res.games[:max_box]
    if len(box_targets) < len(res.games):
        log.info("  %s: box scores limited to %d of %d games",
                 label, len(box_targets), len(res.games))

    # --- standouts ---
    for g in box_targets:
        comp = comp_by_id[g.id]
        try:
            if kind in so.NO_BOXSCORE or not fetch_boxscores:
                res.standouts += so.from_leaders(
                    comp, league=label, game_label=g.label, game_link=g.link)
            else:
                summ = espn.summary(path, g.id)
                # No fallback to ESPN's own "leaders" here. For a league with a
                # real box score, "no rule fired" is a meaningful answer: nobody
                # did anything remarkable. Falling back would fill the page with
                # ordinary stat lines dressed up as highlights.
                res.standouts += so.from_summary(
                    summ, kind=kind, league=label, game_label=g.label, game_link=g.link)
        except espn.ESPNError:
            res.errors.append(f"{label} {g.label}: box score unavailable")
            log.warning("summary failed for %s", g.id)

    return res


def collect_news(leagues: list[dict[str, Any]], keys: list[str], limit: int) -> list[Story]:
    by_key = {l["key"]: l for l in leagues}
    stories: list[Story] = []
    seen: set[str] = set()

    for k in keys:
        lg = by_key.get(k)
        if not lg or not lg.get("enabled", True):
            continue
        try:
            payload = espn.news(lg["path"], limit=8)
        except espn.ESPNError:
            continue
        for art in payload.get("articles", []) or []:
            href = ((art.get("links") or {}).get("web") or {}).get("href", "")
            title = art.get("headline") or ""
            if not title or title in seen:
                continue
            seen.add(title)
            imgs = art.get("images") or []
            stories.append(Story(
                title=title,
                description=art.get("description", ""),
                link=href,
                league=lg["label"],
                image=(imgs[0].get("url") if imgs else None),
                published=(art.get("published") or "")[:10],
            ))

    # Interleave leagues so one busy league can't monopolize the top of the page.
    buckets: dict[str, list[Story]] = {}
    for s in stories:
        buckets.setdefault(s.league, []).append(s)
    mixed: list[Story] = []
    while len(mixed) < limit and any(buckets.values()):
        for lgname in list(buckets):
            if buckets[lgname]:
                mixed.append(buckets[lgname].pop(0))
            if len(mixed) >= limit:
                break
    return mixed[:limit]
