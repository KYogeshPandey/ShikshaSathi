from ..core.db import get_db
from ..models.teacher import (
    create_teacher,
    list_teachers,
    get_teacher,
    update_teacher,
    delete_teacher,
    assign_classroom,
    remove_classroom,
)
# User creation imports
from ..utils.auth import hash_password

def add_teacher(data: dict):
    """
    Creates a Teacher Profile AND a Login User Account.
    Default password: '123456'
    """
    data = data or {}
    db = get_db()
    email = data.get("email")
    
    # 1. Create User Account (For Login)
    if email:
        # Check if user already exists
        existing_user = db.users.find_one({"email": email})
        if not existing_user:
            # Default password is '123456' unless provided
            raw_password = data.get("password") or "123456"
            hashed_pw = hash_password(raw_password)
            
            user_doc = {
                "email": email,
                "password": hashed_pw,
                "role": "teacher",
                "username": data.get("name", "Teacher"),
                "is_active": True
            }
            # Create user and get ID
            res = db.users.insert_one(user_doc)
            
            # Optional: You can link the user_id to teacher profile if needed
            # data["user_id"] = str(res.inserted_id)
            
            print(f"✅ User created for Teacher: {email} (Pass: {raw_password})")
        else:
            print(f"⚠️ User already exists for email: {email}")

    # 2. Create Teacher Profile
    return create_teacher(data)


def get_all_teachers(include_inactive: bool = False):
    """
    List all teachers. Default: active only.
    """
    return list_teachers(include_inactive=include_inactive)


def get_teacher_by_id(tid: str):
    return get_teacher(tid)


def update_teacher_data(tid: str, data: dict):
    data = data or {}
    update_teacher(tid, data)


def delete_teacher_data(tid: str, hard: bool = False):
    """
    Soft delete (is_active=False) by default to preserve history.
    """
    delete_teacher(tid, hard=hard)


def assign_classroom_to_teacher(tid: str, cid: str):
    assign_classroom(tid, cid)


def remove_classroom_from_teacher(tid: str, cid: str):
    remove_classroom(tid, cid)
