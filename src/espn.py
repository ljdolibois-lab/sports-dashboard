"""Thin, defensive client for ESPN's public JSON endpoints.

These endpoints are undocumented but stable and have been public for years.
They are the reason this project does not scrape HTML: scraping breaks on
every redesign, JSON does not.

Base:  https://site.api.espn.com/apis/site/v2/sports/{path}/...
  /scoreboard?dates=YYYYMMDD   -> all games for a date, incl. per-game leaders
  /summary?event={id}          -> full box score, play-by-play, recap article
  /news                        -> league headlines
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 sports-dashboard/1.0"

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_TTL = 60 * 60 * 6  # 6h. Yesterday's finals never change, so cache hard.


class ESPNError(RuntimeError):
    pass


def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def get(url: str, *, use_cache: bool = True, retries: int = 3) -> dict[str, Any]:
    """GET a JSON URL with on-disk caching, retries, and polite pacing."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(url)

    if use_cache and cp.exists() and (time.time() - cp.stat().st_mtime) < CACHE_TTL:
        try:
            return json.loads(cp.read_text())
        except json.JSONDecodeError:
            cp.unlink(missing_ok=True)

    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cp.write_text(json.dumps(data))
            time.sleep(0.25)  # be a good citizen
            return data
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
            last = exc
            log.warning("fetch failed (%s/%s) %s: %s", attempt + 1, retries, url, exc)
            time.sleep(1.5 * (attempt + 1))

    raise ESPNError(f"giving up on {url}: {last}")


def scoreboard(path: str, date: str) -> dict[str, Any]:
    """date is YYYYMMDD."""
    return get(f"{BASE}/{path}/scoreboard?dates={date}&limit=200")


def summary(path: str, event_id: str) -> dict[str, Any]:
    return get(f"{BASE}/{path}/summary?event={event_id}")


def news(path: str, limit: int = 12) -> dict[str, Any]:
    return get(f"{BASE}/{path}/news?limit={limit}", use_cache=True)
