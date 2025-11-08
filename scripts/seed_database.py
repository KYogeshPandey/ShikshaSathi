import os
from dotenv import load_dotenv
from pymongo import MongoClient

backend_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/.env"))
load_dotenv(backend_env_path)

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)
db = client["shiksha_sathi"]  # Instead of get_default_database()

db["users"].create_index("username", unique=True)
db["students"].create_index([("classroom_id", 1), ("roll_no", 1)], unique=True)
print("✅ Indexes created or exist.")
