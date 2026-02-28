import json
import csv
import io
import math
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "root-watch-data")
S3_MASTER_CSV_KEY = os.environ.get("S3_MASTER_CSV_KEY", "data/master_electricity.csv")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Expected CSV columns (case-insensitive after strip):
#   county, has_center, monthly_cost, plant_operating_cost,
#   datacenter_name, capacity_mw, lat, lng
#
# Upload your CSV to S3 at: s3://root-watch-data/data/master_electricity.csv

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# Load master CSV from S3
# ---------------------------------------------------------------------------

def load_master_csv() -> list[dict]:
    """
    Fetch the master electricity CSV from S3 and return it as a list of row dicts.
    Columns are lower-cased and stripped for consistent access.

    Expected S3 key: data/master_electricity.csv
    """
    s3 = _get_s3()
    obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_MASTER_CSV_KEY)
    raw = obj["Body"].read().decode("utf-8")

    reader = csv.DictReader(io.StringIO(raw))
    rows = []
    for row in reader:
        cleaned = {k.strip().lower(): v.strip() for k, v in row.items()}
        # Coerce numeric fields
        for field in ("monthly_cost", "plant_operating_cost", "capacity_mw", "lat", "lng", "has_center"):
            if field in cleaned:
                try:
                    cleaned[field] = float(cleaned[field])
                except (ValueError, TypeError):
                    cleaned[field] = 0.0
        rows.append(cleaned)
    return rows


# ---------------------------------------------------------------------------
# Proximity helpers
# ---------------------------------------------------------------------------

def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_datacenters(
    county_lat: float,
    county_lng: float,
    rows: list[dict],
    radius_miles: float = 50.0,
) -> list[dict]:
    """
    From the master CSV rows, return only data centers whose lat/lng falls
    within `radius_miles` of the given county centroid.

    Each returned row is enriched with a `distance_miles` field.
    Rows without valid lat/lng are matched by has_center == 1 as a fallback.
    """
    nearby = []
    for row in rows:
        if not row.get("has_center"):
            continue
        lat = row.get("lat", 0.0)
        lng = row.get("lng", 0.0)
        if lat and lng:
            dist = _haversine_miles(county_lat, county_lng, lat, lng)
            if dist <= radius_miles:
                nearby.append({**row, "distance_miles": round(dist, 1)})
        # fallback: same county name match
        elif row.get("county", "").lower() == row.get("county", "").lower():
            nearby.append({**row, "distance_miles": 0.0})

    nearby.sort(key=lambda r: r["distance_miles"])
    return nearby


# ---------------------------------------------------------------------------
# Core prediction (reads from S3)
# ---------------------------------------------------------------------------

def predict_electricity_impact(
    county: str,
    county_lat: float,
    county_lng: float,
    farm_monthly_cost: float,
    farm_plant_cost: float,
    radius_miles: float = 50.0,
    months_to_project: int = 3,
    annual_growth_rate: float = 0.03,
    adjacency_weight: float = 0.25,
) -> dict:
    """
    Pull the master CSV from S3, find all data centers within `radius_miles`
    of the county centroid, then project the farmer's monthly electricity costs
    over `months_to_project` months.

    Each nearby data center raises the weight (cost pressure) proportionally
    to its capacity relative to baseline.

    Returns a dict with:
      nearby_datacenters   list  — data centers found within radius
      weight               float — compounded spatial pressure multiplier
      projections          list  — month-by-month projected costs
      plain_english        str   — human-readable summary for the dashboard
    """
    rows = load_master_csv()
    nearby = find_nearby_datacenters(county_lat, county_lng, rows, radius_miles)

    # Build spatial weight: each nearby center adds pressure scaled by capacity
    weight = 1.0
    for dc in nearby:
        mw = dc.get("capacity_mw", 0.0)
        # 100 MW baseline adds full adjacency_weight; scales linearly
        weight += adjacency_weight * (mw / 100.0)

    monthly_growth_rate = (1 + annual_growth_rate) ** (1 / 12) - 1

    projections = []
    for month in range(1, months_to_project + 1):
        growth_factor = (1 + monthly_growth_rate) ** month
        projected_bill = round(farm_monthly_cost * growth_factor, 2)
        projected_plant = round(farm_plant_cost * growth_factor * weight, 2)
        projections.append({
            "month": month,
            "projected_monthly_bill_usd": projected_bill,
            "projected_plant_operating_cost_usd": projected_plant,
            "growth_factor": round(growth_factor, 6),
        })

    total_increase = projections[-1]["projected_monthly_bill_usd"] - farm_monthly_cost
    pct_increase = round((total_increase / farm_monthly_cost) * 100, 2) if farm_monthly_cost else 0

    # Plain-English summary
    dc_names = [dc.get("datacenter_name", dc.get("county", "Unknown")) for dc in nearby]
    if dc_names:
        dc_list = ", ".join(dc_names[:3]) + (" and others" if len(dc_names) > 3 else "")
        plain = (
            f"There are {len(nearby)} data center(s) within {radius_miles:.0f} miles of {county} County "
            f"({dc_list}). Based on their combined power demand, your monthly electricity bill "
            f"is projected to rise from ${farm_monthly_cost:,.2f} to "
            f"${projections[-1]['projected_monthly_bill_usd']:,.2f} "
            f"over {months_to_project} months — a {pct_increase}% increase."
        )
    else:
        plain = (
            f"No data centers were found within {radius_miles:.0f} miles of {county} County "
            f"in the current dataset. Your projected bill increase over {months_to_project} months "
            f"reflects the baseline grid growth rate only ({pct_increase}%)."
        )

    return {
        "county": county,
        "radius_miles": radius_miles,
        "nearby_datacenters": nearby,
        "weight": round(weight, 4),
        "monthly_growth_rate": round(monthly_growth_rate, 6),
        "projections": projections,
        "baseline_monthly_bill_usd": farm_monthly_cost,
        "pct_increase_over_period": pct_increase,
        "plain_english": plain,
    }


# ---------------------------------------------------------------------------
# Save results to S3
# ---------------------------------------------------------------------------

def save_projection_to_s3(result: dict, key: str = "3_month_projection.json") -> str:
    """Write a projection result dict to S3 as JSON. Returns the S3 URI."""
    s3 = _get_s3()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(result, indent=2),
        ContentType="application/json",
    )
    return f"s3://{S3_BUCKET}/{key}"


# ---------------------------------------------------------------------------
# Lambda entry point (kept for AWS Lambda compatibility)
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    AWS Lambda entry point. Expects event keys:
      county              string  SC county name
      county_lat          float   County centroid latitude
      county_lng          float   County centroid longitude
      farm_monthly_cost   float   Farmer's current monthly electricity bill (USD)
      farm_plant_cost     float   Monthly plant/equipment operating cost (USD)
      radius_miles        float   Search radius for nearby data centers (default 50)
      months_to_project   int     How many months to project (default 3)
      annual_growth_rate  float   Baseline annual rate increase (default 0.03)
      adjacency_weight    float   Per-100MW pressure multiplier (default 0.25)
    """
    try:
        result = predict_electricity_impact(
            county=event["county"],
            county_lat=float(event["county_lat"]),
            county_lng=float(event["county_lng"]),
            farm_monthly_cost=float(event["farm_monthly_cost"]),
            farm_plant_cost=float(event.get("farm_plant_cost", 0)),
            radius_miles=float(event.get("radius_miles", 50)),
            months_to_project=int(event.get("months_to_project", 3)),
            annual_growth_rate=float(event.get("annual_growth_rate", 0.03)),
            adjacency_weight=float(event.get("adjacency_weight", 0.25)),
        )

        s3_uri = save_projection_to_s3(result, key=f"projections/{event['county'].lower()}_projection.json")
        result["saved_to"] = s3_uri

        return {"statusCode": 200, "body": json.dumps(result)}

    except KeyError as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Missing required field: {e}"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
