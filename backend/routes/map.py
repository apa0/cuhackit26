"""
routes/map.py

Map-related endpoints for RootWatch API.
"""

import json
import os
from flask import Blueprint, jsonify, Response

map_bp = Blueprint("map", __name__)

_BACKEND_DIR  = os.path.dirname(os.path.dirname(__file__))
_DATA_PATH    = os.path.join(_BACKEND_DIR, "electricity.json")
_WATER_DIR    = os.path.join(_BACKEND_DIR, "..", "data", "water")

_WATER_ACCESS_PATH  = os.path.join(_WATER_DIR, "sc_water_access_slim.geojson")
_WATER_INTAKES_PATH = os.path.join(_WATER_DIR, "Public_Water_Supply_Intakes.geojson")
_WATER_COUNTY_PATH  = os.path.join(_WATER_DIR, "sc_water_by_county.json")


def _load_data():
    with open(_DATA_PATH, "r") as f:
        return json.load(f)


def _load_json(path):
    with open(path, "r") as f:
        return json.load(f)


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
    (boat ramps, piers, bank access, paddle launches).

    Optional query params:
      type      filter by WaterAccessType  e.g. ?type=Boat+Ramp
      water     filter by WaterType        e.g. ?water=Freshwater
      county    filter by County           e.g. ?county=Richland

    Example: GET /api/map/water/access?water=Freshwater&county=Richland
    """
    from flask import request
    data = _load_json(_WATER_ACCESS_PATH)

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

    # Return as raw JSON to preserve GeoJSON content-type
    return Response(
        json.dumps(data, separators=(",", ":")),
        mimetype="application/geo+json",
    )


@map_bp.route("/water/intakes")
def water_intakes():
    """
    GeoJSON FeatureCollection of SC public water supply intakes.
    These are the actual drinking water intake points — key for DC water stress modeling.

    Example: GET /api/map/water/intakes
    """
    data = _load_json(_WATER_INTAKES_PATH)
    return Response(
        json.dumps(data, separators=(",", ":")),
        mimetype="application/geo+json",
    )


@map_bp.route("/water/county")
@map_bp.route("/water/county/<county>")
def water_by_county(county=None):
    """
    Per-county water summary: access point counts, waterbody types,
    public water intake counts. Useful for prediction model joins.

    GET /api/map/water/county           — all counties
    GET /api/map/water/county/Richland  — single county
    """
    data = _load_json(_WATER_COUNTY_PATH)
    if county:
        match = next((c for c in data if c["county"].lower() == county.lower()), None)
        if not match:
            return jsonify({"error": f"County '{county}' not found"}), 404
        return jsonify(match)
    return jsonify(data)
