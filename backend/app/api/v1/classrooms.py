from flask import Blueprint, jsonify, current_app
# from flask_jwt_extended import jwt_required   # ab iski zarurat nahi

bp = Blueprint('classrooms', __name__)

DEMO_CLASSROOMS = [
    {
        "_id": "10th A",
        "name": "10th A",
        "label": "10th A",
        "section": "A",
        "standard": "10",
        "subjects": ["Maths", "Science", "English"]
    },
    {
        "_id": "10th B",
        "name": "10th B",
        "label": "10th B",
        "section": "B",
        "standard": "10",
        "subjects": ["Physics", "Chemistry", "English"]
    },
    {
        "_id": "9th A",
        "name": "9th A",
        "label": "9th A",
        "section": "A",
        "standard": "9",
        "subjects": ["Biology", "Maths", "English"]
    },
]

@bp.route('/', methods=['GET'])
def get_classrooms():    # 👈 no decorator
    print("✅ GET /api/v1/classrooms/ called")
    
    db = current_app.config.get('db')
    
    if db is not None:
        try:
            classrooms = list(db['classrooms'].find({}, {'_id': 0}))
            if classrooms:
                return jsonify({"success": True, "data": classrooms}), 200
        except Exception as e:
            print(f"⚠️ MongoDB error in get_classrooms, falling back to demo: {e}")
    
    return jsonify({"success": True, "data": DEMO_CLASSROOMS}), 200


@bp.route('/<classroom_id>', methods=['GET'])
def get_classroom(classroom_id):   # 👈 no decorator
    print(f"✅ GET /api/v1/classrooms/{classroom_id} called")
    
    db = current_app.config.get('db')
    
    if db is not None:
        try:
            classroom = db['classrooms'].find_one(
                {
                    "$or": [
                        {"_id": classroom_id},
                        {"name": classroom_id},
                        {"label": classroom_id}
                    ]
                },
                {'_id': 0}
            )
            if classroom:
                return jsonify({"success": True, "data": classroom}), 200
        except Exception as e:
            print(f"⚠️ MongoDB error in get_classroom, falling back to demo: {e}")
    
    classroom = next(
        (
            c for c in DEMO_CLASSROOMS
            if c["_id"] == classroom_id
               or c.get("name") == classroom_id
               or c.get("label") == classroom_id
        ),
        None
    )
    
    if not classroom:
        return jsonify({"success": False, "message": "Classroom not found"}), 404
    
    return jsonify({"success": True, "data": classroom}), 200
