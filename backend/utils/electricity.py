import json
import boto3

s3_client = boto3.client("s3", region_name="us-east-1")
S3_BUCKET_NAME = "root-watch-data"


def lambda_handler(event, context):

    # -----------------------------
    # READ PARAMETERS
    # -----------------------------
    annual_growth_rate = event.get("annual_growth_rate", 0.03)
    adjacency_weight = event.get("adjacency_weight", 0.25)
    months_to_project = event.get("months_to_project", 3)

    counties = event["counties"]
    adjacency = event.get("adjacency", {})

    # Convert annual growth to monthly compounded rate
    monthly_growth_rate = (1 + annual_growth_rate) ** (1 / 12) - 1

    # Lookup table for center presence
    center_lookup = {c["county"]: c["has_center"] for c in counties}

    # -----------------------------
    # COMPUTE SPATIAL WEIGHTS
    # -----------------------------
    for county_data in counties:
        county_name = county_data["county"]
        weight = 1.0

        neighbors = adjacency.get(county_name, [])
        for neighbor in neighbors:
            if center_lookup.get(neighbor, 0) == 1:
                weight += adjacency_weight

        county_data["weight"] = weight

    # -----------------------------
    # PROJECT NEXT 3 MONTHS
    # -----------------------------
    for county_data in counties:
        base_cost = county_data["monthly_cost"]
        base_plant_cost = county_data["plant_operating_cost"]
        weight = county_data["weight"]

        for month in range(1, months_to_project + 1):
            growth_factor = (1 + monthly_growth_rate) ** month

            county_data[f"month_{month}_projected_cost"] = round(
                base_cost * growth_factor, 2
            )

            county_data[f"month_{month}_projected_plant_cost"] = round(
                base_plant_cost * growth_factor * weight, 2
            )

    # -----------------------------
    # SAVE RESULTS TO S3
    # -----------------------------
    output_payload = {
        "monthly_growth_rate": monthly_growth_rate,
        "projection_months": months_to_project,
        "results": counties
    }

    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key="3_month_projection.json",
        Body=json.dumps(output_payload),
        ContentType="application/json"
    )

    # -----------------------------
    # RETURN RESPONSE
    # -----------------------------
    return {
        "statusCode": 200,
        "body": json.dumps(output_payload)
    }
