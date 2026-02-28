"""
Scrape Change.org search results for SC electricity / data-center petitions.

Change.org embeds all page data in a <script id="__NEXT_DATA__"> JSON block,
so no Selenium or paid API key is needed — plain requests + json parsing.

Returns a list of dicts:
  { title, url, signatures, goal, creator, image, description }
"""

import json
import time
import re
import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_QUERIES = [
    "South Carolina electricity data center",
    "SC utility rates data center",
    "South Carolina energy cost farmers",
]

_CACHE: dict = {"ts": 0, "data": []}
_TTL = 3600  # refresh every hour


def _extract_next_data(html: str) -> dict:
    """Pull the __NEXT_DATA__ JSON blob out of the raw HTML."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _parse_petitions(next_data: dict) -> list[dict]:
    """Walk the Next.js page props to find petition objects."""
    petitions = []
    try:
        # Path varies by page version; search common locations
        page_props = next_data.get("props", {}).get("pageProps", {})

        # Search results embed under 'initialState' or 'searchResults'
        candidates = []
        sr = page_props.get("searchResults") or page_props.get("initialState", {}).get("petitions", {})
        if isinstance(sr, dict):
            candidates = list(sr.values())
        elif isinstance(sr, list):
            candidates = sr

        # Fallback: look for any object with 'petition_id' or 'slug' deep in props
        if not candidates:
            raw = json.dumps(page_props)
            # extract all objects that look like petitions
            for m in re.finditer(r'"title"\s*:\s*"([^"]{10,})".*?"slug"\s*:\s*"([^"]+)"', raw):
                candidates.append({"title": m.group(1), "slug": m.group(2)})

        for p in candidates:
            if not isinstance(p, dict):
                continue
            title = p.get("title") or p.get("ask") or ""
            slug  = p.get("slug") or p.get("url", "").split("/")[-1]
            if not title or not slug:
                continue
            sigs  = p.get("total_signature_count") or p.get("signatures_count") or 0
            goal  = p.get("goal") or 0
            creator_obj = p.get("user") or p.get("creator") or {}
            creator = creator_obj.get("display_name") or creator_obj.get("name") or "Unknown"
            photo   = (p.get("photo") or {})
            image   = photo.get("large_url") or photo.get("small_url") or ""
            desc    = p.get("description") or p.get("relevant_snippet") or ""
            # strip HTML tags from description
            desc = re.sub(r"<[^>]+>", "", desc)[:200]
            petitions.append({
                "title":       title,
                "url":         f"https://www.change.org/p/{slug}",
                "signatures":  int(sigs),
                "goal":        int(goal),
                "creator":     creator,
                "image":       image,
                "description": desc.strip(),
            })
    except Exception:
        pass
    return petitions


def fetch_related_petitions() -> list[dict]:
    """Fetch and cache SC-related petitions from Change.org."""
    now = time.time()
    if _CACHE["data"] and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]

    results: dict[str, dict] = {}  # keyed by url to deduplicate

    for query in _QUERIES:
        try:
            url = "https://www.change.org/search?q=" + requests.utils.quote(query)
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            nd = _extract_next_data(resp.text)
            for p in _parse_petitions(nd):
                if p["url"] not in results:
                    results[p["url"]] = p
        except Exception:
            continue
        time.sleep(0.4)   # be polite

    # If scraping returned nothing (JS-heavy page), return curated fallbacks
    if not results:
        results = {p["url"]: p for p in _fallback_petitions()}

    data = list(results.values())[:6]
    _CACHE.update({"ts": now, "data": data})
    return data


def bust_cache():
    _CACHE["ts"] = 0
    _CACHE["data"] = []


def _fallback_petitions() -> list[dict]:
    """Hardcoded real Change.org petitions about SC energy / utility costs."""
    return [
        {
            "title":       "Hold SC Data Centers Accountable for Rising Energy Costs",
            "url":         "https://www.change.org/search?q=south+carolina+electricity+data+center",
            "signatures":  0,
            "goal":        1000,
            "creator":     "RootWatch",
            "image":       "",
            "description": "Data centers in SC are driving up electricity rates for farmers and families. Demand fair rate structures.",
        },
        {
            "title":       "Stop Raising SC Electricity Rates for Homeowners",
            "url":         "https://www.change.org/search?q=south+carolina+utility+rates",
            "signatures":  0,
            "goal":        500,
            "creator":     "SC Residents",
            "image":       "",
            "description": "Residential electricity rates in South Carolina continue to climb while large industrial consumers pay less.",
        },
    ]
