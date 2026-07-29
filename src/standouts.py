"""Detect genuinely notable individual performances from box scores.

Design note (this is the part that matters):

We do NOT trust headlines to tell us what was impressive. Headlines are
driven by market size and narrative. Instead we compute a "wow score" from
the actual stat line, using per-sport rules with explicit thresholds.

Every rule returns (points, human_readable_reason). A performance's score is
the sum of its triggered rules, capped at 100. Rules are tuned so that:
    ~45  = worth a mention
    ~65  = clearly a big night
    ~85+ = you would have texted someone about it

Stats are read BY LABEL, never by index. ESPN reorders columns between
sports and occasionally between seasons; index-based parsing is how these
scripts rot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Standout:
    player: str
    team: str
    league: str
    game: str
    line: str            # e.g. "42 PTS, 12 REB, 9 AST"
    reasons: list[str] = field(default_factory=list)
    score: int = 0
    headshot: str | None = None
    game_link: str | None = None

    def __post_init__(self) -> None:
        self.score = min(100, self.score)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _num(v: Any) -> float:
    """Coerce an ESPN stat cell to a number. '1-5', '--', '.247' all appear."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if s in ("", "--", "-"):
        return 0.0
    m = re.match(r"^-?\d+(\.\d+)?$", s)
    if m:
        return float(s)
    # "7-10" (made-attempted) -> take the made side
    m = re.match(r"^(\d+)[-/](\d+)$", s)
    if m:
        return float(m.group(1))
    return 0.0


def _headshot(athlete: dict[str, Any]) -> str | None:
    """ESPN returns headshot as either {'href': ...} or a bare URL string."""
    h = athlete.get("headshot")
    if isinstance(h, dict):
        return h.get("href")
    if isinstance(h, str) and h.startswith("http"):
        return h
    return None


def _row(labels: list[str], stats: list[str]) -> dict[str, Any]:
    return {str(l).upper(): s for l, s in zip(labels, stats)}


def _g(row: dict[str, Any], *names: str) -> float:
    for n in names:
        if n.upper() in row:
            return _num(row[n.upper()])
    return 0.0


def _raw(row: dict[str, Any], *names: str) -> str:
    for n in names:
        if n.upper() in row:
            return str(row[n.upper()])
    return ""


# --------------------------------------------------------------------------
# per-sport rule sets
# --------------------------------------------------------------------------

def _basketball(group: str, row: dict[str, Any]) -> tuple[int, list[str], str]:
    pts, reb, ast = _g(row, "PTS"), _g(row, "REB"), _g(row, "AST")
    stl, blk, tpm = _g(row, "STL"), _g(row, "BLK"), _num(_raw(row, "3PT").split("-")[0] or 0)
    score, why = 0, []

    if pts >= 50: score += 85; why.append(f"{int(pts)}-point game")
    elif pts >= 40: score += 62; why.append(f"{int(pts)} points")
    elif pts >= 35: score += 48; why.append(f"{int(pts)} points")
    elif pts >= 30: score += 41; why.append(f"{int(pts)} points")
    elif pts >= 25: score += 16; why.append(f"{int(pts)} points")

    doubles = sum(1 for v in (pts, reb, ast, stl, blk) if v >= 10)
    if doubles >= 4: score += 80; why.append("quadruple-double")
    elif doubles == 3: score += 55; why.append("triple-double")

    if reb >= 20: score += 35; why.append(f"{int(reb)} rebounds")
    elif reb >= 16: score += 18; why.append(f"{int(reb)} rebounds")
    if ast >= 15: score += 35; why.append(f"{int(ast)} assists")
    elif ast >= 12: score += 18; why.append(f"{int(ast)} assists")
    if blk >= 5: score += 30; why.append(f"{int(blk)} blocks")
    if stl >= 5: score += 30; why.append(f"{int(stl)} steals")
    if tpm >= 8: score += 25; why.append(f"{int(tpm)} threes")

    line = f"{int(pts)} PTS, {int(reb)} REB, {int(ast)} AST"
    return score, why, line


def _baseball(group: str, row: dict[str, Any]) -> tuple[int, list[str], str]:
    score, why = 0, []
    if group == "batting":
        h, ab = _num(_raw(row, "H-AB").split("-")[0] or 0), _g(row, "AB")
        h = h or _g(row, "H")
        hr, rbi, r = _g(row, "HR"), _g(row, "RBI"), _g(row, "R")
        if hr >= 3: score += 85; why.append("3-homer game")
        elif hr >= 2: score += 45; why.append("2 home runs")
        if rbi >= 7: score += 55; why.append(f"{int(rbi)} RBI")
        elif rbi >= 5: score += 35; why.append(f"{int(rbi)} RBI")
        if h >= 5: score += 46; why.append(f"{int(h)} hits")
        elif h >= 4: score += 24; why.append(f"{int(h)} hits")
        if r >= 4: score += 12; why.append(f"{int(r)} runs")
        line = f"{_raw(row, 'H-AB') or int(h)}, {int(hr)} HR, {int(rbi)} RBI"
        return score, why, line

    if group == "pitching":
        ip, k, er = _g(row, "IP"), _g(row, "K", "SO"), _g(row, "ER")
        hits, bb = _g(row, "H"), _g(row, "BB")
        if ip >= 9 and hits == 0: score += 100; why.append("NO-HITTER")
        elif ip >= 9 and er == 0: score += 70; why.append("complete-game shutout")
        elif ip >= 7 and er == 0: score += 42; why.append(f"{ip:g} scoreless innings")
        elif ip >= 6 and er == 0 and k >= 7: score += 32; why.append(f"{ip:g} scoreless, {int(k)} K")
        if k >= 14: score += 60; why.append(f"{int(k)} strikeouts")
        elif k >= 11: score += 44; why.append(f"{int(k)} strikeouts")
        elif k >= 9: score += 22; why.append(f"{int(k)} strikeouts")
        line = f"{ip:g} IP, {int(hits)} H, {int(er)} ER, {int(bb)} BB, {int(k)} K"
        return score, why, line

    return 0, [], ""


def _football(group: str, row: dict[str, Any]) -> tuple[int, list[str], str]:
    score, why = 0, []
    if group == "passing":
        yds, td, ints = _g(row, "YDS"), _g(row, "TD"), _g(row, "INT")
        if yds >= 450: score += 55; why.append(f"{int(yds)} passing yards")
        elif yds >= 350: score += 32; why.append(f"{int(yds)} passing yards")
        if td >= 5: score += 60; why.append(f"{int(td)} passing TDs")
        elif td >= 4: score += 40; why.append(f"{int(td)} passing TDs")
        elif td >= 3: score += 18; why.append(f"{int(td)} passing TDs")
        if score and ints >= 3: score -= 20; why.append(f"(but {int(ints)} INTs)")
        return score, why, f"{_raw(row, 'C/ATT')}, {int(yds)} YDS, {int(td)} TD, {int(ints)} INT"

    if group == "rushing":
        yds, td = _g(row, "YDS"), _g(row, "TD")
        if yds >= 200: score += 65; why.append(f"{int(yds)} rushing yards")
        elif yds >= 150: score += 40; why.append(f"{int(yds)} rushing yards")
        elif yds >= 120: score += 20; why.append(f"{int(yds)} rushing yards")
        if td >= 3: score += 50; why.append(f"{int(td)} rushing TDs")
        elif td >= 2: score += 22; why.append(f"{int(td)} rushing TDs")
        return score, why, f"{int(_g(row,'CAR'))} CAR, {int(yds)} YDS, {int(td)} TD"

    if group == "receiving":
        yds, td, rec = _g(row, "YDS"), _g(row, "TD"), _g(row, "REC")
        if yds >= 200: score += 65; why.append(f"{int(yds)} receiving yards")
        elif yds >= 150: score += 40; why.append(f"{int(yds)} receiving yards")
        elif yds >= 120: score += 20; why.append(f"{int(yds)} receiving yards")
        if td >= 3: score += 55; why.append(f"{int(td)} receiving TDs")
        elif td >= 2: score += 25; why.append(f"{int(td)} receiving TDs")
        return score, why, f"{int(rec)} REC, {int(yds)} YDS, {int(td)} TD"

    if group == "defensive":
        sacks, td = _g(row, "SACKS"), _g(row, "TD")
        if sacks >= 3: score += 55; why.append(f"{sacks:g} sacks")
        elif sacks >= 2: score += 25; why.append(f"{sacks:g} sacks")
        if td >= 1: score += 35; why.append("defensive touchdown")
        return score, why, f"{int(_g(row,'TOT'))} TKL, {sacks:g} SACK"

    if group == "interceptions":
        ints, td = _g(row, "INT"), _g(row, "TD")
        if ints >= 2: score += 45; why.append(f"{int(ints)} interceptions")
        if td >= 1: score += 35; why.append("pick-six")
        return score, why, f"{int(ints)} INT, {int(_g(row,'YDS'))} YDS"

    return 0, [], ""


def _hockey(group: str, row: dict[str, Any]) -> tuple[int, list[str], str]:
    score, why = 0, []
    g, a = _g(row, "G", "GOALS"), _g(row, "A", "AST", "ASSISTS")
    pts = _g(row, "P", "PTS") or (g + a)
    sv, ga = _g(row, "SV", "SAVES"), _g(row, "GA")
    sa = _g(row, "SA", "SHOTS AGAINST")

    if sa or sv:  # goalie line
        if sv >= 20 and ga == 0: score += 65; why.append(f"{int(sv)}-save shutout")
        elif sv >= 40: score += 45; why.append(f"{int(sv)} saves")
        elif sv >= 35: score += 22; why.append(f"{int(sv)} saves")
        return score, why, f"{int(sv)} SV, {int(ga)} GA"

    if g >= 4: score += 85; why.append(f"{int(g)}-goal game")
    elif g >= 3: score += 60; why.append("hat trick")
    elif g >= 2: score += 25; why.append("2 goals")
    if pts >= 5: score += 55; why.append(f"{int(pts)}-point night")
    elif pts >= 4: score += 32; why.append(f"{int(pts)} points")
    if a >= 4: score += 35; why.append(f"{int(a)} assists")
    return score, why, f"{int(g)}G, {int(a)}A, {int(pts)}P"


# group-name -> handler, per sport kind
KIND_RULES: dict[str, Callable[[str, dict[str, Any]], tuple[int, list[str], str]]] = {
    "basketball": _basketball,
    "baseball": _baseball,
    "football": _football,
    "hockey": _hockey,
}

# Sports with no per-player box score in ESPN's summary payload.
# For these we fall back to scoreboard leaders / scoring events.
NO_BOXSCORE = {"soccer", "golf", "tennis", "racing"}


def from_summary(summary: dict[str, Any], *, kind: str, league: str,
                 game_label: str, game_link: str | None) -> list[Standout]:
    """Extract standouts from a /summary payload."""
    if kind not in KIND_RULES:
        return []
    rule = KIND_RULES[kind]
    out: list[Standout] = []

    for team_block in summary.get("boxscore", {}).get("players", []) or []:
        team = (team_block.get("team") or {}).get("abbreviation", "")
        for grp in team_block.get("statistics", []) or []:
            gname = (grp.get("name") or grp.get("type") or "").lower()
            labels = grp.get("labels") or []
            for ath in grp.get("athletes", []) or []:
                person = ath.get("athlete") or {}
                stats = ath.get("stats") or []
                if not stats:
                    continue
                row = _row(labels, stats)
                pts, why, line = rule(gname, row)
                if pts <= 0 or not why:
                    continue
                out.append(Standout(
                    player=person.get("displayName", "Unknown"),
                    team=team, league=league, game=game_label,
                    line=line, reasons=why, score=pts,
                    headshot=_headshot(person),
                    game_link=game_link,
                ))
    return out


def from_leaders(competition: dict[str, Any], *, league: str,
                 game_label: str, game_link: str | None) -> list[Standout]:
    """Fallback for soccer/golf/tennis/racing: use ESPN's own game leaders.

    Deliberately scored low (35) so these never outrank a computed box-score
    standout. They exist so these sports are represented, not to compete.
    """
    out: list[Standout] = []
    for cat in competition.get("leaders", []) or []:
        for L in (cat.get("leaders") or [])[:1]:
            ath = L.get("athlete") or {}
            disp = L.get("displayValue") or ""
            if not disp:
                continue
            out.append(Standout(
                player=ath.get("displayName") or ath.get("shortName", "Unknown"),
                team=(L.get("team") or {}).get("abbreviation", ""),
                league=league, game=game_label, line=disp,
                reasons=[cat.get("displayName") or "Game leader"],
                score=35,
                headshot=_headshot(ath),
                game_link=game_link,
            ))
    return out


def dedupe_and_rank(items: list[Standout], *, min_score: int, limit: int,
                    floor_per_league: bool = True) -> list[Standout]:
    """Rank standouts, dropping anything below `min_score`.

    `floor_per_league` keeps the single best performance from each league that
    had games, even if it missed the bar. Without it a league with a quiet
    slate vanishes from the page entirely and you cannot tell "nothing
    happened" apart from "the fetch broke". Those rescued entries are tagged
    so the page never overstates them.
    """
    best: dict[tuple[str, str], Standout] = {}
    for s in items:
        k = (s.player.lower(), s.game)
        if k not in best or s.score > best[k].score:
            best[k] = s
    pool = sorted(best.values(), key=lambda s: -s.score)

    chosen = [s for s in pool if s.score >= min_score]

    if floor_per_league:
        have = {s.league for s in chosen}
        for s in pool:
            if s.league not in have and s.score > 0:
                s.reasons = [f"best of the {s.league} slate"] + s.reasons
                chosen.append(s)
                have.add(s.league)

    return sorted(chosen, key=lambda s: -s.score)[:limit]
