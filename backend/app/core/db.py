import os
from flask import current_app
from pymongo import MongoClient

_client = None
_db = None


def init_db(app):
    """
    Initialize MongoDB connection and attach db to app.config['db'].
    """
    global _client, _db

    uri = os.getenv("MONGODB_URI")
    print("DEBUG MONGODB_URI:", uri)
    if not uri:
        raise RuntimeError("MONGODB_URI is not set in environment variables")

    try:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client["shiksha_sathi"]
        app.config["db"] = _db

        print("✅ MongoDB connected")
        print(f"📊 Database: {_db.name}")
        print("📁 Collections:", _db.list_collection_names())
    except Exception as e:
        print(f"❌ MongoDB connection error: {e}")
        _client = None
        _db = None
        app.config["db"] = None


def get_db():
    """
    Convenience helper to fetch db from current_app.
    """
    db = current_app.config.get("db")
    if db is None:
        raise RuntimeError("Database is not initialized")
    return db
