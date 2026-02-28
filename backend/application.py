"""Thin wrapper so `python backend/application.py` still works locally."""
import os
from app import create_app

application = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    application.run(debug=True, port=port)
