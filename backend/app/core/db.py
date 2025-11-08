from pymongo import MongoClient
from flask import current_app
import certifi  # Good!

def get_db():
    uri = current_app.config["MONGODB_URI"]
    # Perfect fix for Windows/Atlas SSL!
    client = MongoClient(uri, tlsCAFile=certifi.where())
    db = client["shiksha_sathi"]
    return db
