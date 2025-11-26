import pandas as pd
import os, zipfile
from werkzeug.utils import secure_filename
from PIL import Image

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def extract_photos(zip_file, dest_folder):
    """Extract images from zip to dest_folder, validate, and skip invalid."""
    with zipfile.ZipFile(zip_file) as zf:
        for file in zf.namelist():
            if allowed_image(file):
                filename = secure_filename(file)
                image_path = os.path.join(dest_folder, filename)
                zf.extract(file, dest_folder)
                os.rename(os.path.join(dest_folder, file), image_path)
                # Validate
                try:
                    img = Image.open(image_path)
                    img.verify()
                except:
                    os.remove(image_path)  # Remove invalid images

def process_student_excel(file_path):
    df = pd.read_excel(file_path)
    students = []
    for _, row in df.iterrows():
        students.append({
            "name": str(row.get("name")).strip(),
            "roll_no": str(row.get("roll_no")).strip(),
            "classroom_id": str(row.get("classroom_id")).strip() if not pd.isna(row.get("classroom_id")) else None,
            "email": str(row.get("email")).strip() if not pd.isna(row.get("email")) else None
        })
    return students

def process_teacher_excel(file_path):
    df = pd.read_excel(file_path)
    teachers = []
    for _, row in df.iterrows():
        teachers.append({
            "name": str(row.get("name")).strip(),
            "email": str(row.get("email")).strip() if not pd.isna(row.get("email")) else None,
            "classroom_ids": [
                cid.strip() for cid in str(row.get("classroom_ids", "")).split(",") if cid.strip()
            ] if "classroom_ids" in row else []
        })
    return teachers

# Use extract_photos(zipfile, destfolder) for both students and teachers.
# Backward compat:
extract_student_photos = extract_photos
extract_teacher_photos = extract_photos
