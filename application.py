"""Elastic Beanstalk WSGI entry point.

This ensures the backend package (./backend) is on sys.path so that imports
like `routes.map` continue to resolve when Elastic Beanstalk runs from the
repository root.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # pylint: disable=wrong-import-position

application = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    application.run(debug=True, port=port)
