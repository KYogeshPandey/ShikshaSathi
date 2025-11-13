import pandas as pd
import os, zipfile
from werkzeug.utils import secure_filename
from PIL import Image

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def process_student_excel(file_path):
    df = pd.read_excel(file_path)
    students = []
    for _, row in df.iterrows():
        students.append({
            "name": row.get("name"),
            "roll_no": str(row.get("roll_no")),
            "classroom_id": str(row.get("classroom_id")) if "classroom_id" in row else None,
            "email": row.get("email")
        })
    return students

def extract_student_photos(zip_file, dest_folder):
    with zipfile.ZipFile(zip_file) as zf:
        for file in zf.namelist():
            if allowed_image(file):
                filename = secure_filename(file)
                image_path = os.path.join(dest_folder, filename)
                zf.extract(file, dest_folder)
                os.rename(os.path.join(dest_folder, file), image_path)
                # Validate image
                try:
                    img = Image.open(image_path)
                    img.verify()
                except:
                    os.remove(image_path)  # Remove invalid images

def process_teacher_excel(file_path):
    df = pd.read_excel(file_path)
    teachers = []
    for _, row in df.iterrows():
        teachers.append({
            "name": row.get("name"),
            "email": row.get("email"),
            "classroom_ids": row.get("classroom_ids", "").split(",") if "classroom_ids" in row else []
        })
    return teachers

def extract_teacher_photos(zip_file, dest_folder):
    # Bilkul student wali logic, yahan bhi applied hai
    with zipfile.ZipFile(zip_file) as zf:
        for file in zf.namelist():
            if allowed_image(file):
                filename = secure_filename(file)
                image_path = os.path.join(dest_folder, filename)
                zf.extract(file, dest_folder)
                os.rename(os.path.join(dest_folder, file), image_path)
                # Validate image
                try:
                    img = Image.open(image_path)
                    img.verify()
                except:
                    os.remove(image_path)
