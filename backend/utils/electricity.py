import json
import os
from dotenv import load_dotenv
# import utils.s3 as s3_utils

load_dotenv()

S3_MASTER_JSON_KEY = os.environ.get("S3_MASTER_JSON_KEY", "data/master_electricity.json")

def load_master_json() -> list[dict]:
    """
    Pull the master electricity JSON from S3 and return a cleaned list of county rows.
    Uses s3_utils.get_json() so all AWS auth is handled in one place.
    """
    data = s3_utils.get_json(S3_MASTER_JSON_KEY)

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
# def load_master_json():
#     with open("C:/Users/hanna/PycharmProjects/cuhackit26/backend/electricity.json", "r") as f:
#         return json.load(f)


def predict_electricity_impact(
    county: str,
    months_to_project: int = 1, # CHANGE NUMBER OF MONTHS FOR PREDICTION HERE
    annual_growth_rate: float = 0.03,
    alpha: float = 0.015,
    beta: float = 0.35,
) -> dict:

    rows = load_master_json()

    county_data = next(
        (r for r in rows if r["county"].lower() == county.lower()),
        None
    )

    if not county_data:
        raise ValueError(f"County '{county}' not found in dataset.")

    county_dc = county_data["dc_count"]
    base_cost = county_data["avg_monthly_cost"]

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

    # Projected cost - initial cost
    total_increase = projections[-1]["projected_monthly_bill_usd"] - base_cost
    pct_increase = round(
        (total_increase / base_cost) * 100,
        2
    ) if base_cost else 0

    plain = (
        f"Starting from an average monthly cost of ${base_cost:,.2f}, "
        f"{county} County's projected cost after {months_to_project} month(s) is "
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


def save_projection_to_s3(result: dict, key: str = "projection.json") -> str:
    """
    Persist a projection result to S3 as JSON.
    Uses s3_utils.put_json() so all AWS auth is handled in one place.
    """
    return s3_utils.put_json(key, result)


def lambda_handler(event, context):
    try:
        print(f"[lambda_handler] invoked with event: {event}")
        result = predict_electricity_impact(
            county=event["county"],
        )

        return {"statusCode": 200, "body": json.dumps(result)}

    except KeyError as e:
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


# if __name__ == "__main__":
#     result = predict_electricity_impact(
#         county="Spartanburg"
#     )
#
#     print(json.dumps(result, indent=2))
