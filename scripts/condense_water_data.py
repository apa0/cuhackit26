"""
Condenses raw water GeoJSON data into two files:
  data/water/sc_water_access_slim.geojson  — map-ready, active access points only
  data/water/sc_water_by_county.json       — per-county summary for prediction model

Then uploads both files to S3 so the API can serve them from there.
Run from the repo root:
  python scripts/condense_water_data.py
"""

import json
import os
import sys
from collections import defaultdict

# Allow imports from backend/utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

ROOT = os.path.join(os.path.dirname(__file__), "..")
WATER_DIR = os.path.abspath(os.path.join(ROOT, "data", "water"))

# ── 1. sc_water_access_slim.geojson ──────────────────────────────────────
KEEP = [
    "WaterAccessID", "WaterAccessName", "WaterAccessType", "WaterAccessSubType",
    "Waterbody", "WaterbodyType", "WaterType", "County",
    "Owner", "Status", "PublicAccess", "Latitude", "Longitude",
]

with open(os.path.join(WATER_DIR, "original", "South_Carolina_Public_Water_Access_PUBLIC_VIEW.geojson")) as f:
    raw = json.load(f)

slim_features = []
for feat in raw["features"]:
    p = feat["properties"]
    if p.get("Status") != "Active":
        continue
    slim_features.append({
        "type": "Feature",
        "properties": {k: p.get(k) for k in KEEP},
        "geometry": feat["geometry"],
    })

slim = {
    "type": "FeatureCollection",
    "name": "sc_water_access_slim",
    "features": slim_features,
}

out_slim = os.path.join(WATER_DIR, "sc_water_access_slim.geojson")
with open(out_slim, "w") as f:
    json.dump(slim, f, separators=(",", ":"))

print(f"[1] sc_water_access_slim.geojson: {len(slim_features)} active features")

# ── 2. sc_water_by_county.json ────────────────────────────────────────────
county_access = defaultdict(lambda: {
    "access_points": 0,
    "freshwater_access": 0,
    "saltwater_access": 0,
    "waterbodies": set(),
    "waterbody_types": set(),
    "access_types": set(),
})

for feat in slim_features:
    p = feat["properties"]
    c = (p.get("County") or "Unknown").strip()
    county_access[c]["access_points"] += 1
    if p.get("WaterType") == "Freshwater":
        county_access[c]["freshwater_access"] += 1
    elif p.get("WaterType") == "Saltwater":
        county_access[c]["saltwater_access"] += 1
    if p.get("Waterbody"):
        county_access[c]["waterbodies"].add(p["Waterbody"])
    if p.get("WaterbodyType"):
        county_access[c]["waterbody_types"].add(p["WaterbodyType"])
    if p.get("WaterAccessType"):
        county_access[c]["access_types"].add(p["WaterAccessType"])

# Load public water supply intakes
with open(os.path.join(WATER_DIR, "original", "Public_Water_Supply_Intakes.geojson")) as f:
    intakes_raw = json.load(f)

county_intakes = defaultdict(list)
for feat in intakes_raw["features"]:
    p = feat["properties"]
    c = (p.get("COUNTY") or "Unknown").strip().title()
    county_intakes[c].append({
        "pws_id": p.get("PWSNO"),
        "pws_name": p.get("PWSNAME"),
        "facility": p.get("FACILITYNA"),
        "intake_id": p.get("INTAKE"),
        "pws_type": p.get("PWSTYPE"),
        "pws_status": p.get("PWSSTATUS"),
        "intake_status": p.get("INTAKESTAT"),
        "lat": p.get("LATITUDE"),
        "lon": p.get("LONGITUDE"),
    })

all_counties = sorted(set(list(county_access.keys()) + list(county_intakes.keys())))

result = []
for county in all_counties:
    acc = county_access[county]
    intakes = county_intakes.get(county, [])
    result.append({
        "county": county,
        "water_access_points": acc["access_points"],
        "freshwater_access_points": acc["freshwater_access"],
        "saltwater_access_points": acc["saltwater_access"],
        "unique_waterbodies": sorted(acc["waterbodies"]),
        "waterbody_types": sorted(acc["waterbody_types"]),
        "access_types": sorted(acc["access_types"]),
        "public_water_intakes": len(intakes),
        "active_intakes": sum(1 for i in intakes if i["intake_status"] == "A"),
        "intake_details": intakes,
    })

out_county = os.path.join(WATER_DIR, "sc_water_by_county.json")
with open(out_county, "w") as f:
    json.dump(result, f, indent=2)

print(f"[2] sc_water_by_county.json: {len(result)} counties")

sample = next(r for r in result if r["public_water_intakes"] > 0)
print(f"    Sample ({sample['county']}): {sample['water_access_points']} access pts, "
      f"{sample['public_water_intakes']} intakes ({sample['active_intakes']} active), "
      f"waterbodies: {sample['unique_waterbodies'][:3]}")

# ── Upload to S3 ──────────────────────────────────────────────────────────
print("\nUploading to S3...")
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

try:
    import utils.s3 as s3_utils

    # Upload slim GeoJSON
    with open(out_slim, "rb") as f:
        s3_utils.upload_document(
            f.read(),
            key="data/water/sc_water_access_slim.geojson",
            content_type="application/geo+json",
        )
    print("[S3] Uploaded data/water/sc_water_access_slim.geojson")

    # Upload county summary
    with open(out_county, "rb") as f:
        s3_utils.upload_document(
            f.read(),
            key="data/water/sc_water_by_county.json",
            content_type="application/json",
        )
    print("[S3] Uploaded data/water/sc_water_by_county.json")

    # Upload original intakes file
    intakes_src = os.path.join(WATER_DIR, "original", "Public_Water_Supply_Intakes.geojson")
    with open(intakes_src, "rb") as f:
        s3_utils.upload_document(
            f.read(),
            key="data/water/Public_Water_Supply_Intakes.geojson",
            content_type="application/geo+json",
        )
    print("[S3] Uploaded data/water/Public_Water_Supply_Intakes.geojson")

    print("\nAll files uploaded to S3 successfully.")

except Exception as e:
    print(f"[S3] Upload failed: {e}")
    print("Local files are still available as fallback.")
