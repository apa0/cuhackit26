import os
from flask import Flask, jsonify
from flask_cors import CORS

# Load .env before anything else so credentials are available immediately
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars

from routes.map import map_bp



def create_app():
    app = Flask(__name__)
    CORS(app)

    # Register blueprints
    app.register_blueprint(map_bp, url_prefix="/api/map")
    #app.register_blueprint(impact_bp, url_prefix="/api/impact")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "RootWatch API", "version": "0.1.0"})

    @app.route("/api/admin/aws-check")
    def aws_check():
        """Test that AWS credentials are valid and the S3 bucket is reachable."""
        from utils.s3 import verify_credentials
        result = verify_credentials()
        status_code = 200 if result["ok"] else 500
        return jsonify(result), status_code

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, port=port)
