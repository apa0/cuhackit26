"""
routes/map.py

Map-related endpoints for RootWatch API.

Water data is loaded from S3 (primary) with a local-file fallback for dev.
S3 keys are configurable via environment variables:
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

_ROUTES_DIR  = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_ROUTES_DIR)
_WATER_DIR   = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "data", "water"))

# S3 keys (override via env vars)
_S3_WATER_ACCESS_KEY  = os.environ.get("S3_WATER_ACCESS_KEY",  "data/water/sc_water_access_slim.geojson")
_S3_WATER_INTAKES_KEY = os.environ.get("S3_WATER_INTAKES_KEY", "data/water/Public_Water_Supply_Intakes.geojson")
_S3_WATER_COUNTY_KEY  = os.environ.get("S3_WATER_COUNTY_KEY",  "data/water/sc_water_by_county.json")

# Local fallback paths (used if S3 is unavailable)
_LOCAL_WATER_ACCESS  = os.path.join(_WATER_DIR, "sc_water_access_slim.geojson")
_LOCAL_WATER_INTAKES = os.path.join(_WATER_DIR, "original", "Public_Water_Supply_Intakes.geojson")
_LOCAL_WATER_COUNTY  = os.path.join(_WATER_DIR, "sc_water_by_county.json")

# Simple in-memory cache: { s3_key: parsed_data }
_cache: dict = {}


def _load_from_s3_or_local(s3_key: str, local_fallback: str):
    """
    Try S3 first (using s3_utils.get_json). On any failure, fall back to
    the local file. Results are cached in memory for the process lifetime.
    """
    if s3_key in _cache:
        return _cache[s3_key]

    data = None
    try:
        import utils.s3 as s3_utils
        data = s3_utils.get_json(s3_key)
        logger.info(f"Loaded {s3_key} from S3")
    except Exception as e:
        logger.warning(f"S3 load failed for '{s3_key}': {e} — falling back to local file")
        with open(local_fallback, "r") as f:
            data = json.load(f)
        logger.info(f"Loaded {s3_key} from local fallback: {local_fallback}")

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
    data = _load_from_s3_or_local(_S3_WATER_ACCESS_KEY, _LOCAL_WATER_ACCESS)

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
    data = _load_from_s3_or_local(_S3_WATER_INTAKES_KEY, _LOCAL_WATER_INTAKES)
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
    data = _load_from_s3_or_local(_S3_WATER_COUNTY_KEY, _LOCAL_WATER_COUNTY)
    if county:
        match = next((c for c in data if c["county"].lower() == county.lower()), None)
        if not match:
            return jsonify({"error": f"County '{county}' not found"}), 404
        return jsonify(match)
    return jsonify(data)


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
