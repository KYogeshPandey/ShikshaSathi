from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId
import datetime

bp = Blueprint('auth', __name__)

# Fallback demo users if DB not connected
DEMO_USERS = {
    "admin1": {"password": "admin123", "role": "admin", "name": "Admin User"},
    "teacher1": {"password": "teacher123", "role": "teacher", "name": "Teacher One"},
    "student1": {"password": "student123", "role": "student", "name": "Student One"}
}

@bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400
        
        print(f"📥 Login attempt: {username}")
        
        # Get database
        db = current_app.config.get('db')
        
        # If DB connected, use MongoDB
        if db is not None:
            users_collection = db['users']
            user = users_collection.find_one({"username": username})
            
            if user and check_password_hash(user.get('password', ''), password):
                token = create_access_token(
                    identity=str(user['_id']),
                    additional_claims={
                        "role": user.get('role', 'student'),
                        "username": username
                    }
                )
                
                print(f"✅ Login successful (DB): {username}")
                
                return jsonify({
                    "success": True,
                    "message": "Login successful",
                    "access_token": token,
                    "user": {
                        "username": username,
                        "role": user.get('role', 'student'),
                        "name": user.get('name', username)
                    }
                }), 200
        
        # Fallback to demo users
        user = DEMO_USERS.get(username)
        if not user or user['password'] != password:
            print(f"❌ Invalid credentials: {username}")
            return jsonify({"success": False, "message": "Invalid credentials"}), 401
        
        token = create_access_token(
            identity=username,
            additional_claims={"role": user["role"]}
        )
        
        print(f"✅ Login successful (Demo): {username}")
        
        return jsonify({
            "success": True,
            "message": "Login successful",
            "access_token": token,
            "user": {
                "username": username,
                "role": user["role"],
                "name": user.get("name", username)
            }
        }), 200
    
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'student')
        name = data.get('name', username)
        
        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400
        
        db = current_app.config.get('db')
        
        if db is not None:
            users_collection = db['users']
            
            # Check if user exists
            if users_collection.find_one({"username": username}):
                return jsonify({"success": False, "message": "User already exists"}), 409
            
            # Create new user
            hashed_password = generate_password_hash(password)
            new_user = {
                "username": username,
                "password": hashed_password,
                "role": role,
                "name": name,
                "created_at": datetime.datetime.utcnow()
            }
            
            result = users_collection.insert_one(new_user)
            print(f"✅ User registered in DB: {username}")
            
            return jsonify({
                "success": True,
                "message": "User registered successfully",
                "user_id": str(result.inserted_id)
            }), 201
        
        # Fallback to demo
        if username in DEMO_USERS:
            return jsonify({"success": False, "message": "User already exists"}), 409
        
        DEMO_USERS[username] = {"password": password, "role": role, "name": name}
        print(f"✅ User registered (Demo): {username}")
        
        return jsonify({"success": True, "message": "User registered successfully"}), 201
    
    except Exception as e:
        print(f"❌ Register error: {str(e)}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
