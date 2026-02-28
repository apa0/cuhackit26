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

_DATA_PATH = os.path.join(os.path.dirname(__file__), "electricity.json")


def _load_county_data():
    with open(_DATA_PATH, "r") as f:
        return json.load(f)


def create_app():
    app = Flask(__name__)
    CORS(app)

    # Register blueprints
    app.register_blueprint(map_bp, url_prefix="/api/map")

    # ── Frontend ──────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        counties = _load_county_data()
        return render_template("index.html", counties=counties)

    # ── Simple chatbot ────────────────────────────────────────────────────
    @app.route("/api/chat", methods=["POST"])
    def chat():
        body = request.get_json(silent=True) or {}
        user_msg = body.get("message", "").strip().lower()
        counties = _load_county_data()

        # Build quick stats
        with_dc = [c for c in counties if c["dc_count"] > 0]
        no_dc   = [c for c in counties if c["dc_count"] == 0]
        avg_with = round(sum(c["avg_monthly_cost"] for c in with_dc) / len(with_dc), 2) if with_dc else 0
        avg_without = round(sum(c["avg_monthly_cost"] for c in no_dc) / len(no_dc), 2) if no_dc else 0
        top = sorted(counties, key=lambda c: c["dc_count"], reverse=True)[:3]

        if any(w in user_msg for w in ["most data center", "highest dc", "most dc"]):
            reply = f"The county with the most data centers is {top[0]['county']} with {top[0]['dc_count']} DCs, followed by {top[1]['county']} ({top[1]['dc_count']}) and {top[2]['county']} ({top[2]['dc_count']})."
        elif any(w in user_msg for w in ["average", "avg", "cost"]):
            reply = (f"Counties WITH data centers average ${avg_with}/month. "
                     f"Counties WITHOUT data centers average ${avg_without}/month — "
                     f"a difference of ${round(avg_with - avg_without, 2)}/month.")
        elif any(w in user_msg for w in ["how many", "total", "count"]):
            total_dc = sum(c["dc_count"] for c in counties)
            reply = f"There are {total_dc} data centers across {len(with_dc)} of SC's 46 counties."
        else:
            # Try to match a county name
            match = next((c for c in counties if c["county"].lower() in user_msg), None)
            if match:
                adj_with_dc = [a for a in match["adjacent"] if any(c["county"] == a and c["dc_count"] > 0 for c in counties)]
                reply = (f"{match['county']} County has {match['dc_count']} data center(s) "
                         f"and an average monthly electricity cost of ${match['avg_monthly_cost']}. "
                         f"Adjacent counties with DCs: {', '.join(adj_with_dc) if adj_with_dc else 'none'}.")
            else:
                reply = ("I can answer questions about SC county electricity costs, data center counts, "
                         "and cost comparisons. Try asking: 'Which county has the most data centers?' "
                         "or 'What is the average cost in Spartanburg?'")

        return jsonify({"reply": reply})

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

    # ── Health / AWS ──────────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "RootWatch API", "version": "0.1.0"})

    @app.route("/api/admin/aws-check")
    def aws_check():
        from utils.s3 import verify_credentials
        result = verify_credentials()
        return jsonify(result), (200 if result["ok"] else 500)

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, port=port)
