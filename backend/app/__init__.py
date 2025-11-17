import os
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
from .core.db import init_db
from .api.v1 import register_blueprints

BASE_DIR = Path(__file__).resolve().parents[1]   # .../backend
load_dotenv(BASE_DIR / ".env")


def create_app():
    """
    Application factory.
    Creates and configures the Flask app instance.
    """
    app = Flask(__name__)

    # -------- Config --------
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET", "change_this_in_env")
    app.config["JSON_SORT_KEYS"] = False

    # -------- Extensions --------
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
            }
        },
    )

    jwt = JWTManager(app)

    # -------- Database --------
    init_db(app)

    # -------- Blueprints --------
    register_blueprints(app)

    # -------- Health route --------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    # -------- Error handlers (basic) --------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "message": "Internal server error"}), 500

    return app
