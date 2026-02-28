"""
routes/map.py

Map-related endpoints for RootWatch API.

All data is loaded exclusively from S3. S3 keys are configurable via env vars:
  S3_WATER_ACCESS_KEY   default: data/water/sc_water_access_slim.geojson
  S3_WATER_INTAKES_KEY  default: data/water/Public_Water_Supply_Intakes.geojson
  S3_WATER_COUNTY_KEY   default: data/water/sc_water_by_county.json
"""

import json
import logging
import os
from flask import Blueprint, jsonify, Response, request

logger = logging.getLogger(__name__)

map_bp = Blueprint("map", __name__)

# S3 keys (override via env vars)
_S3_WATER_ACCESS_KEY  = os.environ.get("S3_WATER_ACCESS_KEY",  "data/water/sc_water_access_slim.geojson")
_S3_WATER_INTAKES_KEY = os.environ.get("S3_WATER_INTAKES_KEY", "data/water/Public_Water_Supply_Intakes.geojson")
_S3_WATER_COUNTY_KEY  = os.environ.get("S3_WATER_COUNTY_KEY",  "data/water/sc_water_by_county.json")

# Simple in-memory cache: { s3_key: parsed_data }
_cache: dict = {}


def _load_from_s3(s3_key: str):
    """
    Load JSON from S3 and cache in memory for the process lifetime.
    Raises immediately if S3 is unavailable — no local fallback.
    """
    if s3_key in _cache:
        return _cache[s3_key]

    import utils.s3 as s3_utils
    data = s3_utils.get_json(s3_key)
    logger.info(f"Loaded {s3_key} from S3")
    _cache[s3_key] = data
    return data


def _load_data():
    """Load county electricity + DC data from S3 via load_master_json()."""
    from utils.electricity import load_master_json
    return load_master_json()


@map_bp.route("/")
def map_index():
    return jsonify({"status": "ok", "route": "map"})


@map_bp.route("/data")
def map_data():
    """Return all county electricity + DC data."""
    return jsonify(_load_data())


@map_bp.route("/data/<county>")
def county_detail(county):
    """Return data for a single county (case-insensitive)."""
    data = _load_data()
    match = next((c for c in data if c["county"].lower() == county.lower()), None)
    if not match:
        return jsonify({"error": f"County '{county}' not found"}), 404
    return jsonify(match)


# ── Water routes ──────────────────────────────────────────────────────────

@map_bp.route("/water/access")
def water_access():
    """
    GeoJSON FeatureCollection of all active SC public water access points
    (boat ramps, piers, bank access, paddle launches). Loaded from S3.

    Optional query params:
      type      filter by WaterAccessType  e.g. ?type=Boat+Ramp
      water     filter by WaterType        e.g. ?water=Freshwater
      county    filter by County           e.g. ?county=Richland

    Example: GET /api/map/water/access?water=Freshwater&county=Richland
    """
    data = _load_from_s3(_S3_WATER_ACCESS_KEY)

    access_type = request.args.get("type", "").strip().lower()
    water_type  = request.args.get("water", "").strip().lower()
    county      = request.args.get("county", "").strip().lower()

    if any([access_type, water_type, county]):
        features = []
        for feat in data["features"]:
            p = feat["properties"]
            if access_type and (p.get("WaterAccessType") or "").lower() != access_type:
                continue
            if water_type and (p.get("WaterType") or "").lower() != water_type:
                continue
            if county and (p.get("County") or "").lower() != county:
                continue
            features.append(feat)
        data = {**data, "features": features}

    return Response(
        json.dumps(data, separators=(",", ":")),
        mimetype="application/geo+json",
    )


@map_bp.route("/water/intakes")
def water_intakes():
    """
    GeoJSON FeatureCollection of SC public water supply intakes. Loaded from S3.
    These are the actual drinking water intake points — key for DC water stress modeling.

    Example: GET /api/map/water/intakes
    """
    data = _load_from_s3(_S3_WATER_INTAKES_KEY)
    return Response(
        json.dumps(data, separators=(",", ":")),
        mimetype="application/geo+json",
    )


@map_bp.route("/water/county")
@map_bp.route("/water/county/<county>")
def water_by_county(county=None):
    """
    Per-county water summary: access point counts, waterbody types,
    public water intake counts. Loaded from S3.

    GET /api/map/water/county           — all counties
    GET /api/map/water/county/Richland  — single county
    """
    data = _load_from_s3(_S3_WATER_COUNTY_KEY)
    if county:
        match = next((c for c in data if c["county"].lower() == county.lower()), None)
        if not match:
            return jsonify({"error": f"County '{county}' not found"}), 404
        return jsonify(match)
    return jsonify(data)


@map_bp.route("/datacenters")
def datacenters():
    """
    Return all SC data centers with coordinates, operator, address, estimated year,
    and status. `est_year` is derived from `date_opened` when available; nulls are
    estimated by spreading co-located sibling buildings evenly from the campus's
    known start year to 2022, then falling back to operator-level defaults.

    Response: { "datacenters": [ { name, operator, lat, lng, address,
                                     est_year, status, era, region }, … ] }
    """
    LOCAL_PATH = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "datacenters", "sc_data_centers.json"
    )
    S3_DC_KEY = os.environ.get("S3_DC_KEY", "data/datacenters/sc_data_centers.json")

    try:
        import utils.s3 as s3_utils
        raw = s3_utils.get_json(S3_DC_KEY)
    except Exception:
        with open(LOCAL_PATH, "r") as fh:
            raw = json.load(fh)

    items = raw.get("south_carolina_data_centers", [])

    # ── Operator-level fallback years (SC first known presence) ──────────
    _OP_DEFAULTS: dict[str, int] = {
        "Google":                            2007,
        "DartPoints":                        2007,
        "DC BLOX Inc.":                      2023,
        "TigerDC":                           2019,
        "QTS Data Centers":                  2015,
        "Meta":                              2027,
        "Lumen":                             2012,
        "Segra":                             2016,
        "elink corp":                        2014,
        "Cogent Communications, Inc.":       2010,
        "Atos Group":                        2013,
        "NorthMark Strategies":              2020,
        "LightHouse Data Centers":           2018,
        "Overwatch Capital":                 2021,
        "Cielo Digital Infrastructure":      2022,
        "Technology Solutions of SC, Inc.": 2011,
        "Terra Nexus Ventures":              2021,
    }

    def _parse_year(val) -> int | None:
        if not val:
            return None
        s = str(val).strip()
        # Grab the first 4-digit year anywhere in the string
        import re
        m = re.search(r"(\d{4})", s)
        return int(m.group(1)) if m else None

    # ── Pass 1: resolve known years; group nulls by (operator, address) ──
    _CAMPUS_YEARS: dict[tuple, list[int]] = {}
    for dc in items:
        yr = _parse_year(dc.get("date_opened"))
        if yr:
            key = (dc.get("operator"), dc.get("address", ""))
            _CAMPUS_YEARS.setdefault(key, []).append(yr)

    def _est_year(dc, idx_in_campus: int, campus_size: int) -> int:
        known = _parse_year(dc.get("date_opened"))
        if known:
            return known
        op   = dc.get("operator", "")
        addr = dc.get("address", "")
        key  = (op, addr)
        campus_known = _CAMPUS_YEARS.get(key, [])
        start = min(campus_known) if campus_known else _OP_DEFAULTS.get(op, 2018)
        # Spread nulls evenly from start→2022 within the campus
        end   = 2022
        span  = max(1, end - start)
        step  = span / max(1, campus_size - len(campus_known))
        return min(2022, round(start + step * idx_in_campus))

    # Group items by campus key to track spread index
    from collections import defaultdict
    _campus_null_idx: dict[tuple, int] = defaultdict(int)

    def _era(year: int) -> str:
        if year < 2010:  return "pre-2010"
        if year < 2015:  return "2010–2014"
        if year < 2020:  return "2015–2019"
        return "2020-present"

    results = []
    for dc in items:
        coords = dc.get("coordinates") or {}
        lat = coords.get("lat")
        lng = coords.get("lng")
        if lat is None or lng is None:
            continue
        op   = dc.get("operator", "")
        addr = dc.get("address", "")
        key  = (op, addr)
        campus_items = [d for d in items if d.get("operator") == op and d.get("address", "") == addr]
        null_idx  = _campus_null_idx[key]
        if not _parse_year(dc.get("date_opened")):
            _campus_null_idx[key] += 1
        yr = _est_year(dc, null_idx, len(campus_items))
        results.append({
            "name":       dc.get("name", "Unknown"),
            "operator":   op,
            "address":    addr,
            "lat":        lat,
            "lng":        lng,
            "est_year":   yr,
            "date_opened": dc.get("date_opened"),
            "date_notes": dc.get("date_notes", ""),
            "status":     dc.get("status", "unknown"),
            "era":        _era(yr),
            "region":     dc.get("region", ""),
        })

    return jsonify({"datacenters": results})


@map_bp.route("/water/cache/clear", methods=["POST"])
def clear_water_cache():
    """
    Clear the in-memory water data cache so the next request re-fetches from S3.
    Useful after uploading updated water data files to S3.

    POST /api/map/water/cache/clear
    """
    cleared = list(_cache.keys())
    _cache.clear()
    return jsonify({"ok": True, "cleared_keys": cleared})
