"""
Auth0 authentication routes.

Endpoints:
  GET /auth/login      – redirect to Auth0 Universal Login
  GET /auth/callback   – handle the OAuth callback, store user in session
  GET /auth/logout     – clear session and redirect to Auth0 logout
  GET /auth/me         – return current user info as JSON (or 401)
"""

import os
from functools import wraps
from urllib.parse import urlencode, quote_plus

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint, redirect, render_template, request,
    session, url_for, jsonify, current_app
)

auth_bp = Blueprint("auth", __name__)

# OAuth instance – registered on the app in create_app()
oauth = OAuth()

# ── Helpers ───────────────────────────────────────────────────────

def init_oauth(app):
    """Call once during create_app() to bind the OAuth client to the app."""
    oauth.init_app(app)

    domain = os.environ.get("AUTH0_DOMAIN", "")
    oauth.register(
        "auth0",
        client_id=os.environ.get("AUTH0_CLIENT_ID", ""),
        client_secret=os.environ.get("AUTH0_CLIENT_SECRET", ""),
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{domain}/.well-known/openid-configuration",
    )


def login_required(f):
    """Decorator: require a logged-in session, else redirect to /auth/login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────

@auth_bp.route("/login")
def login():
    """Kick off Auth0 Universal Login redirect."""
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("auth.callback", _external=True)
    )


@auth_bp.route("/callback")
def callback():
    """Handle Auth0 callback: exchange code → tokens → store user in session."""
    token = oauth.auth0.authorize_access_token()
    # userinfo is embedded inside the id_token claims
    session["user"] = token.get("userinfo") or {}
    return redirect(url_for("index"))


@auth_bp.route("/logout")
def logout():
    """Clear local session then redirect to Auth0 logout endpoint."""
    session.clear()
    domain = os.environ.get("AUTH0_DOMAIN", "")
    client_id = os.environ.get("AUTH0_CLIENT_ID", "")
    return_to = url_for("index", _external=True)
    logout_url = (
        f"https://{domain}/v2/logout?"
        + urlencode({"returnTo": return_to, "client_id": client_id}, quote_via=quote_plus)
    )
    return redirect(logout_url)


# ── JSON API ──────────────────────────────────────────────────────

@auth_bp.route("/me")
def me():
    """Return the current user profile as JSON (GET /auth/me), or 401 if not logged in."""
    user = session.get("user")
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "name":     user.get("name"),
        "email":    user.get("email"),
        "picture":  user.get("picture"),
        "sub":      user.get("sub"),
    })
