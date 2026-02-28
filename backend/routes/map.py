"""
routes/map.py

Map-related endpoints for RootWatch API.
"""

import json
import os
from flask import Blueprint, jsonify

map_bp = Blueprint("map", __name__)

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "electricity.json")


def _load_data():
    with open(_DATA_PATH, "r") as f:
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
