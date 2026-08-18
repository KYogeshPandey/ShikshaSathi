from ..core.db import get_db
from ..models.teacher import (
    create_teacher,
    list_teachers,
    get_teacher,
    update_teacher,
    delete_teacher,
    assign_classroom,
    remove_classroom,
    get_teacher_by_email,
    get_teacher_by_user_id,
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
    email = (data.get("email") or "").strip().lower()
    
    # 1. Create User Account (For Login)
    if email:
        # Check if user already exists
        existing_user = db.users.find_one({"email": email})
        if not existing_user:
            # Default password is '123456' unless provided
            raw_password = data.get("password") or "123456"
            hashed_pw = hash_password(raw_password)
            
            print(f"DEBUG: Creating user for {email} with role 'teacher'")
            
            user_doc = {
                "email": email,
                "password": hashed_pw, 
                "role": "teacher",
                # 👇 FIX: Use email as username to ensure uniqueness and prevent E11000 error
                "username": email, 
                "name": data.get("name", "Teacher"), # Store name separately if needed in user schema
                "is_active": True
            }
            # Create user and get ID
            res = db.users.insert_one(user_doc)
            
            # Link the user_id to teacher profile
            data["user_id"] = str(res.inserted_id)
            
            
            print(f"DEBUG: Inserted User ID: {res.inserted_id}")
        else:
            print(f"⚠️ User already exists for email: {email}")
            # If user exists, try to link existing user ID if not already linked
            if not data.get("user_id"):
                data["user_id"] = str(existing_user["_id"])

    # 2. Create Teacher Profile
    return create_teacher(data)


def get_all_teachers(include_inactive: bool = False):
    return list_teachers(include_inactive=include_inactive)

def get_teacher_by_id(tid: str):
    return get_teacher(tid)

def get_teacher_profile_by_user(user_id: str, email: str = None):
    t = get_teacher_by_user_id(user_id)
    if t: return t
    if email:
        return get_teacher_by_email(email)
    return None

def update_teacher_data(tid: str, data: dict):
    data = data or {}
    update_teacher(tid, data)

def delete_teacher_data(tid: str, hard: bool = False):
    delete_teacher(tid, hard=hard)

def assign_classroom_to_teacher(tid: str, cid: str):
    assign_classroom(tid, cid)

def remove_classroom_from_teacher(tid: str, cid: str):
    remove_classroom(tid, cid)
