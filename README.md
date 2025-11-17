# ShikshaSathi – Face Recognition Attendance System (Prototype, Free-Tier Ready)

## 1. Project Summary

ShikshaSathi ek AI-enabled Face Recognition Attendance System hai jo schools, colleges aur institutes ke liye design kiya gaya hai.  
Teachers camera se attendance le sakte hain, students apna attendance/stats dekhte hain, aur admin classes, users, aur reports manage karta hai.  

System abhi student-project / prototype level par hai, lekin architecture is tarah banaya gaya hai ki future me production-ready ban sakta hai.

---

## 2. Final Tech Stack (Simple & Free)

### Backend
- **Framework:** Flask (Python 3.11)
- **Auth:** JWT (flask-jwt-extended)
- **Database:** MongoDB Atlas Free Tier (512MB)
- **File Storage (optional):** Cloudinary Free (face images)
- **AI (Phase 1):** Demo data + basic structure
- **AI (Phase 2 – optional):** face-api.js / TensorFlow.js in browser

### Frontend
- **Framework:** React + Vite
- **UI:** Tailwind CSS / custom CSS
- **Charts:** Recharts, react-calendar-heatmap
- **Hosting Target:** Vercel free tier

### Hosting (target)
- **Backend:** Render / Railway free tier (single Flask app)
- **Frontend:** Vercel static hosting
- **DB:** MongoDB Atlas free cluster


# 🎓 Admin
Role Summary
The Admin is the superuser and system owner responsible for configuring the academic structure, managing all users, controlling AI face-recognition behavior, and overseeing system health, reports, and security.

Core Academic & Master Data Management

Create and manage departments (e.g., CSE, ECE, Mechanical).

Create and manage classes (standard, section, batch, program).

Create and manage subjects (subject code, name, credits, semester mapping).

Configure and manage academic years and semesters (e.g., 2025–2026, Semester 1).

User & Role Management

Create and manage teachers (onboard, update, deactivate).

Create and manage students (enroll, update, promote, deactivate).

Assign roles and permissions (admin/teacher/student) based on policy.

Maintain mappings such as assigning teachers to subjects and students to classes.

Timetable & Allocation

Define and manage class timetables (day/period/subject/teacher/room).

Update timetables when faculty or room changes occur.

Face Recognition & AI Governance

Upload and manage photos / face datasets for students (initial enrollment).

Approve / reject face data (quality, correctness).

Configure AI thresholds (similarity/confidence cut‑offs, liveness options in future versions).

Decide when AI‑based attendance is considered valid vs requiring manual review.

Attendance & Reporting Control

View global attendance dashboards (per class, subject, department, semester).

Export system‑wide reports (CSV/PDF) for:

Class-wise attendance

Subject-wise attendance

Student-wise summaries

Low‑attendance lists

Perform admin-level overrides of attendance in exceptional cases (with reason logging).

Operations, Backup & Compliance

Configure and trigger backup/restore procedures for MongoDB (as per hosting limits).

Monitor system logs and error reports for failures or misuse.

Ensure basic compliance with institute rules regarding data privacy and access.

Permissions (High level)

Full CRUD on departments, classes, subjects, timetables, users, face data.

Full read access to all attendance data and reports.

Authority to override permissions and correct attendance with audit logging.

# 👨‍🏫 Teacher
Role Summary
Teachers are the primary operational users who use the system daily to take attendance, review student records, and generate class-level reports. They only have access to their assigned classes and subjects.

Attendance Operations

Take attendance for assigned classes/subjects using:

AI‑based face recognition (where available in prototype), and

Manual override interface (mark present/absent/late, resolve mismatches).

Correct incorrect attendance for their own classes only, with reason.

Class & Student Access

View assigned classes list and drilldown into a specific class.

View students in their classes, including basic profiles and photos.

View class-wise and subject-wise attendance for their own subjects.

Reporting & Analytics

Generate class-level reports, including:

Daily/weekly attendance summary

Subject-wise percentages for their classes

List of students below threshold (e.g., <75%).

Export their own class reports as CSV/PDF (where supported).

Communication & Notices

Send announcements / notices to:

Their classes, and/or

Specific students (e.g., “extra class tomorrow”, “test on Friday”).

View and manage announcements they have created.

Timetable & Schedule

View timetable for their assigned subjects and classes.

Use timetable context (period, subject, class) when taking attendance.

Face Data Support (Optional)

Upload or suggest better photos for students in their class (e.g., clearer face images) – subject to Admin approval.

Permissions (High level)

Read/write attendance for their own classes & subjects.

Read class & student lists for assigned classes.

Generate reports limited to their classes.

Cannot create/delete users or classes; cannot change global AI settings.

# 🧑‍🎓 Student
Role Summary
Students are consumers of the system who primarily view their own attendance, timetable, and receive communications. They have read‑only access to most data, and limited ability to update their own profile.

Attendance Visibility

View overall attendance summary (total %, total attended vs total classes).

View subject-wise attendance:

Per subject: total lectures, attended lectures, percentage.

Visualizations (charts/heatmaps) on their dashboard.

Academic Information

View class timetable (for their enrolled class).

View upcoming classes for the day (optional).

Notifications & Announcements

View announcements/notices from teachers and admin.

Receive low-attendance alerts (e.g., below 75%) on dashboard and/or email/SMS (if configured).

Reports & Documents

Download personal attendance report (PDF/CSV) for a given date range or semester, for internship/college records.

Profile Management

Update basic profile information:

Profile photo (for display; Admin controls actual AI face dataset approval).

Name (minor corrections, or request change)

Contact details (phone, email)

View their registered face photos / status (optional UI in advanced versions).

Permissions (High level)

Read only their own attendance, timetable, and notifications.

Limited write on own profile (contact/photo) but not on academic records.

No access to other students’ data, no ability to modify attendance or AI settings.
---

## 3. Current Architecture (Simplified)

[ React + Vite (Vercel) ]
|
| HTTPS (REST)
v
[ Flask API (Render / local now) ]
|
v
[ MongoDB Atlas (Free Tier) ]

[ Cloudinary (optional) ] -> face images storage
[ face-api.js (Phase 2) ] -> browser-side face embeddings


- Ek single Flask backend jisme sab APIs hain: auth, users, classes, attendance, reports.
- Frontend React dashboard se yahi APIs hit ho rahe hain.
- MongoDB Atlas pe `shiksha_sathi` database me collections: `users`, `classrooms`, `students`, `teachers`, `attendance`.

---

## 4. Implemented Features (Till Now)

### Backend
- `.env` config (MONGODB_URI, JWT secrets, etc)
- MongoDB Atlas connection (SSL fix ke saath)
- Flask app with:
  - CORS
  - JWTManager
  - Blueprints for `auth`, `students`, `classrooms`, `attendance`
- Demo login:
  - `admin1 / admin123` (role: admin)
  - optionally `student1 / student123`, `teacher1 / teacher123` (can be seeded)
- Working endpoints (local):
  - `POST /api/v1/auth/login` – login with JWT
  - `GET /api/v1/classrooms/` – class list (demo + DB fallback)
  - `GET /api/v1/classrooms/<id>` – class detail
  - `GET /api/v1/attendance/stats` – analytics for admin
  - `GET /api/v1/students/me` – student profile (demo + DB)
  - `GET /api/v1/attendance/mystats` – student’s own attendance (demo)

### Frontend
- React app running via `npm start` (Vite / CRA style)
- Login page integrated with backend `/auth/login`
- Admin dashboard:
  - Shows total students, present, absent, overall %
  - Pie chart + bar chart (Recharts) wired to backend `/attendance/stats`
  - Class dropdown populated via `/classrooms/`
  - Keys/warnings fixed, console clean
- Student dashboard:
  - Welcome message
  - Placeholders for student details + attendance timeline
  - Hits `/students/me` and `/attendance/mystats` APIs (after recent code)

---

## 5. Target Scope (Prototype)

1. **Admin**
   - Login
   - See global dashboard (class-wise stats, graphs)
   - See class list, per-class attendance analytics (basic)

2. **Teacher**
   - Login
   - See assigned classes (demo scope: fix one or two classes)
   - Mark attendance:
     - Phase 1: manual or demo call
     - Phase 2: face recognition capture and auto-mark

3. **Student**
   - Login
   - See overall % and subject-wise % (basic table)
   - See last few days’ attendance (optional heatmap)

---

## 6. Minimal Collections (for this prototype)

### `users`
- username, password_hash, role (`admin/teacher/student`), email, name

### `classrooms`
- name (`10th A`), section, standard, student_ids, teacher_ids

### `attendance`
- student_id, class_id, subject (optional), date, period_number, status (`present/absent`), marked_by

### `face_embeddings` (Phase 2 optional)
- student_id, embedding (array), image_url, quality_score

---

## 7. Running Locally

Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py

Frontend
cd frontend
npm install
npm start


Open:
- Backend health: `http://localhost:5000/health`
- Frontend: `http://localhost:3000`
- Admin login: `admin1 / admin123`

---

## 8. Deployment Plan (Free Tier)

1. **MongoDB Atlas** – already used locally, same URI in production.
2. **Backend → Render**
   - Push backend to GitHub
   - Create new Web Service → connect repo
   - Build: `pip install -r requirements.txt`
   - Run: `gunicorn app:app` or `gunicorn app.main:app`
   - Env vars: MONGODB_URI, JWT_SECRET, etc.
3. **Frontend → Vercel**
   - Push frontend to GitHub
   - Import repo in Vercel
   - Add env: `VITE_API_URL=https://your-backend.onrender.com`
   - Build, deploy
4. Test full flow:
   - Login
   - Dashboard load
   - Attendance stats

---
