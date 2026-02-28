"""
routes/map.py

Map-related endpoints for RootWatch API.
"""

from flask import Blueprint, jsonify

map_bp = Blueprint("map", __name__)


@map_bp.route("/")
def map_index():
    return jsonify({"status": "ok", "route": "map"})
