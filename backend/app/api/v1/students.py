from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint('students', __name__)

@bp.route('/me', methods=['GET'])
@jwt_required(optional=True)   # 👈 optional, taki student dashboard bhi token ke bina demo pe chale
def get_my_profile():
    try:
        identity = get_jwt_identity()
        print(f"✅ GET /api/v1/students/me for user: {identity}")
        
        db = current_app.config.get('db')
        
        # ===== Try from MongoDB if available =====
        if db is not None and identity:
            try:
                user = db['users'].find_one(
                    {"username": identity},
                    {'_id': 0, 'password': 0}
                )
                student = db['students'].find_one(
                    {"username": identity},
                    {'_id': 0}
                )
                if student:
                    if user:
                        student.setdefault("email", user.get("email"))
                        student.setdefault("name", user.get("name", identity))
                    return jsonify({"success": True, "data": student}), 200
            except Exception as e:
                print(f"⚠️ MongoDB error in get_my_profile, falling back to demo: {e}")
        
        # ===== DEMO fallback data =====
        username = identity or "student1"
        profile = {
            "name": "Student One",
            "className": "Class 10-A",
            "rollNumber": "S001",
            "email": f"{username}@school.com",
            "username": username
        }
        return jsonify({"success": True, "data": profile}), 200
    
    except Exception as e:
        print(f"❌ Error in get_my_profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500


@bp.route('/', methods=['GET'])
@jwt_required(optional=True)
def get_all_students():
    try:
        print("✅ GET /api/v1/students/ called")
        
        db = current_app.config.get('db')
        
        # ===== Try from MongoDB if available =====
        if db is not None:
            try:
                students = list(db['students'].find({}, {'_id': 0}))
                if students:
                    return jsonify({"success": True, "data": students}), 200
            except Exception as e:
                print(f"⚠️ MongoDB error in get_all_students, falling back to demo: {e}")
        
        # ===== DEMO data =====
        demo_students = [
            {"name": "Student One", "rollNumber": "S001", "className": "Class 10-A"},
            {"name": "Student Two", "rollNumber": "S002", "className": "Class 10-B"},
            {"name": "Student Three", "rollNumber": "S003", "className": "Class 9-A"},
        ]
        return jsonify({"success": True, "data": demo_students}), 200
    
    except Exception as e:
        print(f"❌ Error in get_all_students: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
