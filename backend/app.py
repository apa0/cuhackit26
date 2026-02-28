import json
import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# Load .env before anything else so credentials are available immediately
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars

from routes.map import map_bp
from routes.auth import auth_bp, init_oauth

_FRONTEND_DIR   = os.path.join(os.path.dirname(__file__), "..", "frontend")
_TEMPLATE_DIR   = os.path.join(_FRONTEND_DIR, "templates")
_STATIC_DIR     = os.path.join(_FRONTEND_DIR, "static")


def _load_county_data():
    """Load county electricity + DC data from S3 via load_master_json()."""
    from utils.electricity import load_master_json
    return load_master_json()


def create_app():
    app = Flask(__name__, template_folder=_TEMPLATE_DIR, static_folder=_STATIC_DIR)
    CORS(app)

    # Secret key required for session (Auth0 tokens stored here)
    app.secret_key = os.environ.get("APP_SECRET_KEY", "dev-secret-change-me")

    # Register blueprints
    app.register_blueprint(map_bp, url_prefix="/api/map")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # Bind Auth0 OAuth client
    init_oauth(app)

    # Inject current user into every Jinja template
    from flask import session as _session
    @app.context_processor
    def inject_user():
        return {"current_user": _session.get("user")}

    # ── Frontend ──────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        counties = _load_county_data()
        return render_template("index.html", counties=counties)

    # ── Petition ──────────────────────────────────────────────────────────
    @app.route("/api/petition", methods=["POST"])
    def petition():
        body = request.get_json(silent=True) or {}
        name   = body.get("name", "").strip()
        email  = body.get("email", "").strip()
        county = body.get("county", "").strip()
        if not name or not email or not county:
            return jsonify({"ok": False, "error": "All fields are required."}), 400
        # TODO: persist to DynamoDB / S3
        return jsonify({"ok": True, "message": f"Thank you, {name}! Your signature has been recorded."})

    # ── External petitions (Change.org scrape) ────────────────────────────
    @app.route("/api/petitions/external")
    def external_petitions():
        from utils.changeorg import fetch_related_petitions
        petitions = fetch_related_petitions()
        return jsonify({"ok": True, "petitions": petitions})

    @app.route("/api/petitions/refresh")
    def refresh_petitions():
        from utils.changeorg import bust_cache, fetch_related_petitions
        bust_cache()
        petitions = fetch_related_petitions()
        return jsonify({"ok": True, "petitions": petitions})

    # ── Health / AWS ──────────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "RootWatch API", "version": "0.1.0"})

    @app.route("/api/admin/aws-check")
    def aws_check():
        from utils.s3 import verify_credentials
        result = verify_credentials()
        return jsonify(result), (200 if result["ok"] else 500)

    # ── Electricity impact ────────────────────────────────────────────────
    @app.route("/api/impact/electricity", methods=["GET"])
    def electricity_impact():
        """
        Project electricity cost impact for a county via lambda_handler.

        Query params:
          county             SC county name (defaults to Oconee for testing)
          months             months to project, default 1
          override_base_cost override the avg cost from the dataset
          save               pass save=true to persist result to S3

        Example: GET /api/impact/electricity?county=Oconee&months=3
        """
        from utils.electricity import lambda_handler, save_projection_to_s3

        county = request.args.get("county", "Oconee").strip()
        months = request.args.get("months", 1, type=int)
        override = request.args.get("override_base_cost", None, type=float)
        should_save = request.args.get("save", "false").lower() == "true"

        event = {
            "county": county,
            "months_to_project": months,
        }
        if override is not None:
            event["override_base_cost"] = override

        lambda_response = lambda_handler(event, None)
        status_code = lambda_response.get("statusCode", 500)
        body = json.loads(lambda_response.get("body", "{}"))

        if status_code != 200:
            return jsonify(body), status_code

        if should_save:
            s3_uri = save_projection_to_s3(body)
            body["saved_to"] = s3_uri

        return jsonify(body), 200

    # ── Timeline (farmland + DC growth) ──────────────────────────────────
    @app.route("/api/timeline")
    def timeline():
        """
        Returns per-county data for the timeline slider.
        Combines:
          - USDA NASS farmland acres (2002, 2007, 2012, 2017, 2022)
          - Estimated DC growth over the same years (hardcoded milestones
            based on known SC data center expansion waves)

        Response shape:
          {
            "years": [2002, 2007, 2012, 2017, 2022],
            "counties": {
              "Spartanburg": {
                "farmland": {2002: 112000, 2007: 108000, ...},
                "dc_count":  {2002: 0, 2007: 0, 2012: 2, 2017: 8, 2022: 14}
              }, ...
            }
          }
        """
        from utils.nass import fetch_farmland_by_county

        years = [2002, 2007, 2012, 2017, 2022]
        counties = _load_county_data()
        farmland = fetch_farmland_by_county()

        # DC timeline estimates — SC major campus openings by era:
        # Pre-2010: almost none | 2010-2016: small wave | 2017-2022: boom
        def estimate_dc_timeline(current_count: int) -> dict:
            if current_count == 0:
                return {y: 0 for y in years}
            if current_count == 1:
                return {2002: 0, 2007: 0, 2012: 0, 2017: 1, 2022: 1}
            if current_count == 2:
                return {2002: 0, 2007: 0, 2012: 1, 2017: 2, 2022: 2}
            if current_count <= 4:
                return {2002: 0, 2007: 0, 2012: 1, 2017: 2, 2022: current_count}
            # Large clusters (Berkeley=12, Spartanburg=14): grew sharply post-2017
            return {
                2002: 0,
                2007: 0,
                2012: max(1, current_count // 7),
                2017: max(2, current_count // 3),
                2022: current_count,
            }

        result = {}
        for c in counties:
            name = c["county"]
            dc_timeline = estimate_dc_timeline(c["dc_count"])
            farm_data = farmland.get(name, {})
            # Convert year keys to strings for JSON
            result[name] = {
                "dc_count":  {str(y): dc_timeline[y] for y in years},
                "farmland":  {str(k): v for k, v in farm_data.items()} if farm_data else {},
            }

        return jsonify({"years": years, "counties": result})

    @app.route("/api/timeline/refresh")
    def timeline_refresh():
        """Bust the NASS farmland cache and re-fetch from the API."""
        from utils.nass import bust_cache
        bust_cache()
        return jsonify({"ok": True, "message": "Cache cleared. Next /api/timeline call will re-fetch from NASS."})

    # ── Chatbot (Bedrock Knowledge Base + Claude) ─────────────────────────
    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Retrieves relevant chunks from the Bedrock Knowledge Base then
        invokes Claude Sonnet to answer the farmer's question.

        Body: { "message": "your question here" }
        Response: { "reply": "answer text" }

        Required env vars:
          BEDROCK_KB_ID      — your Bedrock Knowledge Base ID
          AWS_REGION         — defaults to us-east-1
          BEDROCK_MODEL_ID   — defaults to anthropic.claude-sonnet-4-20250514-v1:0
        """
        from utils.bedrock_chat import chat as bedrock_chat

        body = request.get_json(silent=True) or {}
        user_msg = body.get("message", "").strip()
        if not user_msg:
            return jsonify({"reply": "Please enter a question."}), 400

        reply = bedrock_chat(user_msg)
        return jsonify({"reply": reply})

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, port=port)
