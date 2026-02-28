import json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "root-watch-data")
S3_MASTER_JSON_KEY = os.environ.get("S3_MASTER_JSimport json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "root-watch-data")
S3_MASTER_JSON_KEY = os.environ.get("S3_MASTER_JSON_KEY", "data/master_electricity.json")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# Load master JSON from S3
# ---------------------------------------------------------------------------

def load_master_json() -> list[dict]:
    s3 = _get_s3()
    obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_MASTER_JSON_KEY)
    raw = obj["Body"].read().decode("utf-8")

    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError("Master JSON must be a list of county objects.")

    cleaned = []
    for row in data:
        cleaned.append({
            "county": str(row.get("county", "")).strip(),
            "dc_count": int(row.get("dc_count", 0)),
            "avg_monthly_cost": float(row.get("avg_monthly_cost", 0)),
            "adjacent": row.get("adjacent", []),
        })

    return cleaned

# ---------------------------------------------------------------------------
# Core Pressure Formula
# ---------------------------------------------------------------------------

def calculate_pressure_weight(
    county_dc: int,
    adjacent_dc_total: int,
    alpha: float = 0.015,   # 1.5% per direct DC
    beta: float = 0.35     # 35% spillover weight
) -> float:
    """
    W = 1 + αC + βαΣAi
    """
    return 1 + (alpha * county_dc) + (beta * alpha * adjacent_dc_total)


# ---------------------------------------------------------------------------
# Core Prediction
# ---------------------------------------------------------------------------

def predict_electricity_impact(
    county: str,
    months_to_project: int = 1,
    annual_growth_rate: float = 0.03,
    alpha: float = 0.015,
    beta: float = 0.35,
    override_base_cost: float | None = None,
) -> dict:

    rows = load_master_json()

    county_data = next(
        (r for r in rows if r["county"].lower() == county.lower()),
        None
    )

    if not county_data:
        raise ValueError(f"County '{county}' not found in dataset.")

    county_dc = county_data["dc_count"]
    base_cost = override_base_cost if override_base_cost is not None else county_data["avg_monthly_cost"]

    # Sum DCs in adjacent counties
    adjacent_dc_total = 0
    for adj in county_data["adjacent"]:
        adj_row = next(
            (r for r in rows if r["county"].lower() == adj.lower()),
            None
        )
        if adj_row:
            adjacent_dc_total += adj_row["dc_count"]

    # Structural pressure weight
    weight = 1 + (alpha * county_dc) + (beta * alpha * adjacent_dc_total)

    # Convert annual to monthly
    monthly_growth_rate = (1 + annual_growth_rate) ** (1 / 12) - 1

    projections = []
    for month in range(1, months_to_project + 1):
        growth_factor = (1 + monthly_growth_rate) ** month
        projected_bill = round(
            base_cost * growth_factor * weight,
            2
        )

        projections.append({
            "month": month,
            "projected_monthly_bill_usd": projected_bill,
            "growth_factor": round(growth_factor, 6),
        })

    total_increase = projections[-1]["projected_monthly_bill_usd"] - base_cost
    pct_increase = round(
        (total_increase / base_cost) * 100,
        2
    ) if base_cost else 0

    plain = (
        f"{county} County has {county_dc} data center(s). "
        f"Adjacent counties contribute {adjacent_dc_total} additional center(s). "
        f"Starting from an average monthly cost of ${base_cost:,.2f}, "
        f"the projected cost after {months_to_project} months is "
        f"${projections[-1]['projected_monthly_bill_usd']:,.2f} "
        f"({pct_increase}% increase)."
    )

    return {
        "county": county,
        "base_monthly_cost": base_cost,
        "county_dc": county_dc,
        "adjacent_dc_total": adjacent_dc_total,
        "pressure_weight": round(weight, 6),
        "monthly_growth_rate": round(monthly_growth_rate, 6),
        "projections": projections,
        "pct_increase_over_period": pct_increase,
        "plain_english": plain,
    }

# ---------------------------------------------------------------------------
# Save Results to S3
# ---------------------------------------------------------------------------

def save_projection_to_s3(result: dict, key: str = "projection.json") -> str:
    s3 = _get_s3()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(result, indent=2),
        ContentType="application/json",
    )
    return f"s3://{S3_BUCKET}/{key}"


# ---------------------------------------------------------------------------
# Lambda Entry Point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    try:
        result = predict_electricity_impact(
            county=event["county"]
        )

        return {"statusCode": 200, "body": json.dumps(result)}

    except KeyError as e:
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}ON_KEY", "data/master_electricity.json")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# Load master JSON from S3
# ---------------------------------------------------------------------------

def load_master_json() -> list[dict]:
    s3 = _get_s3()
    obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_MASTER_JSON_KEY)
    raw = obj["Body"].read().decode("utf-8")

    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError("Master JSON must be a list of county objects.")

    cleaned = []
    for row in data:
        cleaned.append({
            "county": str(row.get("county", "")).strip(),
            "dc_count": int(row.get("dc_count", 0)),
            "avg_monthly_cost": float(row.get("avg_monthly_cost", 0)),
            "adjacent": row.get("adjacent", []),
        })

    return cleaned

# ---------------------------------------------------------------------------
# Core Pressure Formula
# ---------------------------------------------------------------------------

def calculate_pressure_weight(
    county_dc: int,
    adjacent_dc_total: int,
    alpha: float = 0.015,   # 1.5% per direct DC
    beta: float = 0.35     # 35% spillover weight
) -> float:
    """
    W = 1 + αC + βαΣAi
    """
    return 1 + (alpha * county_dc) + (beta * alpha * adjacent_dc_total)


# ---------------------------------------------------------------------------
# Core Prediction
# ---------------------------------------------------------------------------

def predict_electricity_impact(
    county: str,
    months_to_project: int = 1,
    annual_growth_rate: float = 0.03,
    alpha: float = 0.015,
    beta: float = 0.35,
    override_base_cost: float | None = None,
) -> dict:

    rows = load_master_json()

    county_data = next(
        (r for r in rows if r["county"].lower() == county.lower()),
        None
    )

    if not county_data:
        raise ValueError(f"County '{county}' not found in dataset.")

    county_dc = county_data["dc_count"]
    base_cost = override_base_cost if override_base_cost is not None else county_data["avg_monthly_cost"]

    # Sum DCs in adjacent counties
    adjacent_dc_total = 0
    for adj in county_data["adjacent"]:
        adj_row = next(
            (r for r in rows if r["county"].lower() == adj.lower()),
            None
        )
        if adj_row:
            adjacent_dc_total += adj_row["dc_count"]

    # Structural pressure weight
    weight = 1 + (alpha * county_dc) + (beta * alpha * adjacent_dc_total)

    # Convert annual to monthly
    monthly_growth_rate = (1 + annual_growth_rate) ** (1 / 12) - 1

    projections = []
    for month in range(1, months_to_project + 1):
        growth_factor = (1 + monthly_growth_rate) ** month
        projected_bill = round(
            base_cost * growth_factor * weight,
            2
        )

        projections.append({
            "month": month,
            "projected_monthly_bill_usd": projected_bill,
            "growth_factor": round(growth_factor, 6),
        })

    total_increase = projections[-1]["projected_monthly_bill_usd"] - base_cost
    pct_increase = round(
        (total_increase / base_cost) * 100,
        2
    ) if base_cost else 0

    plain = (
        f"{county} County has {county_dc} data center(s). "
        f"Adjacent counties contribute {adjacent_dc_total} additional center(s). "
        f"Starting from an average monthly cost of ${base_cost:,.2f}, "
        f"the projected cost after {months_to_project} months is "
        f"${projections[-1]['projected_monthly_bill_usd']:,.2f} "
        f"({pct_increase}% increase)."
    )

    return {
        "county": county,
        "base_monthly_cost": base_cost,
        "county_dc": county_dc,
        "adjacent_dc_total": adjacent_dc_total,
        "pressure_weight": round(weight, 6),
        "monthly_growth_rate": round(monthly_growth_rate, 6),
        "projections": projections,
        "pct_increase_over_period": pct_increase,
        "plain_english": plain,
    }

# ---------------------------------------------------------------------------
# Save Results to S3
# ---------------------------------------------------------------------------

def save_projection_to_s3(result: dict, key: str = "projection.json") -> str:
    s3 = _get_s3()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(result, indent=2),
        ContentType="application/json",
    )
    return f"s3://{S3_BUCKET}/{key}"


# ---------------------------------------------------------------------------
# Lambda Entry Point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    try:
        result = predict_electricity_impact(
            county=event["county"]
        )

        return {"statusCode": 200, "body": json.dumps(result)}

    except KeyError as e:
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


