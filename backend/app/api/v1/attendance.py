from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity  # jwt_required hata sakte ho

bp = Blueprint('attendance', __name__)

@bp.route('/stats', methods=['GET'])
def get_stats():   # 👈 koi decorator nahi
    try:
        print("✅ GET /api/v1/attendance/stats called")
        
        classroom_id = request.args.get('classroom_id')
        db = current_app.config.get('db')
        
        # ===== Try from MongoDB if available =====
        if db is not None:
            try:
                query = {}
                if classroom_id:
                    query['classroom_id'] = classroom_id
                attendance_data = list(db['attendance'].find(query, {'_id': 0}))
                return jsonify({"success": True, "data": attendance_data}), 200
            except Exception as e:
                print(f"⚠️ MongoDB error in get_stats, falling back to demo: {e}")
        
        # ===== DEMO fallback data =====
        demo_data = [
            {"student_id": "S001", "present_days": 22, "absent_days": 2, "attendance_percent": 91.7},
            {"student_id": "S002", "present_days": 18, "absent_days": 6, "attendance_percent": 75.0},
            {"student_id": "S003", "present_days": 20, "absent_days": 4, "attendance_percent": 83.3},
        ]
        return jsonify({"success": True, "data": demo_data}), 200
    
    except Exception as e:
        print(f"❌ Error in get_stats: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500


@bp.route('/mystats', methods=['GET'])
def my_stats():    # 👈 yahan bhi decorator hatao
    try:
        identity = get_jwt_identity()  # token ho to use hoga, warna None
        print(f"✅ GET /api/v1/attendance/mystats for user: {identity}")
        
        db = current_app.config.get('db')
        
        # ===== Try from MongoDB if available =====
        if db is not None and identity:
            try:
                attendance = list(
                    db['attendance'].find({"username": identity}, {'_id': 0})
                )
                return jsonify({"success": True, "data": attendance}), 200
            except Exception as e:
                print(f"⚠️ MongoDB error in my_stats, falling back to demo: {e}")
        
        # ===== DEMO fallback =====
        demo_attendance = [
            {"date": "2025-11-01", "status": "present"},
            {"date": "2025-11-02", "status": "present"},
            {"date": "2025-11-03", "status": "absent"},
            {"date": "2025-11-04", "status": "present"},
            {"date": "2025-11-05", "status": "present"}
        ]
        return jsonify({"success": True, "data": demo_attendance}), 200
    
    except Exception as e:
        print(f"❌ Error in my_stats: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
