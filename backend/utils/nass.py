"""
utils/nass.py

Fetches SC county-level farmland acreage from the USDA NASS QuickStats API.
Census of Agriculture years: 2002, 2007, 2012, 2017, 2022.

Set NASS_API_KEY in your .env file.
Get a free key at: https://quickstats.nass.usda.gov/api
"""

import os
import json
import logging
import requests
from functools import lru_cache

logger = logging.getLogger(__name__)

_API_KEY  = os.environ.get("NASS_API_KEY", "")
_BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "farmland_cache.json")

# SC county name normalizations (NASS uses uppercase)
def _normalize(name: str) -> str:
    return name.strip().title()


def fetch_farmland_by_county() -> dict[str, dict[int, int]]:
    """
    Returns a dict keyed by county name → {year: acres}.
    Example: {"Spartanburg": {2002: 112000, 2007: 108000, ...}}

    Uses a local JSON cache to avoid hitting the API on every request.
    """
    # Return cache if it exists
    if os.path.exists(_CACHE_PATH):
        with open(_CACHE_PATH, "r") as f:
            return json.load(f)

    if not _API_KEY or _API_KEY == "your_nass_key_here":
        logger.warning("NASS_API_KEY not set — returning empty farmland data.")
        return {}

    params = {
        "key":              _API_KEY,
        "source_desc":      "CENSUS",
        "sector_desc":      "ECONOMICS",
        "group_desc":       "FARMS & LAND & ASSETS",
        "commodity_desc":   "FARM OPERATIONS",
        "statisticcat_desc":"AREA OPERATED",
        "unit_desc":        "ACRES",
        "state_alpha":      "SC",
        "agg_level_desc":   "COUNTY",
        "format":           "JSON",
    }

    try:
        resp = requests.get(_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    except Exception as e:
        logger.error(f"NASS API error: {e}")
        return {}

    result: dict[str, dict[int, int]] = {}
    for row in raw:
        county = _normalize(row.get("county_name", ""))
        year   = int(row.get("year", 0))
        value  = row.get("Value", "").replace(",", "").strip()
        if not county or not year or not value.lstrip("-").isdigit():
            continue
        if county not in result:
            result[county] = {}
        result[county][year] = int(value)

    # Persist cache
    with open(_CACHE_PATH, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"NASS farmland data cached: {len(result)} counties")
    return result


def bust_cache():
    """Delete local cache so next request re-fetches from NASS."""
    if os.path.exists(_CACHE_PATH):
        os.remove(_CACHE_PATH)
        logger.info("NASS cache cleared.")
