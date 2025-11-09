
# 📘 ShikshaSathi API Documentation

---

✅ POST /api/register  
**Roles:** All  
**Description:** User registration  

### Request
```json
{"username": "raj", "email": "raj@gmail.com", "password": "abc123", "role": "teacher"}

Response
{"success": true, "user_id": "65d..."}

✅ POST /api/login

Roles: All
Description: User login (JWT)

Request
{"username": "raj", "password": "abc123"}

Response
{
  "success": true,
  "message": "Login successful",
  "access_token": "<JWT>",
  "user": {"username": "raj", "role": "teacher"}
}

✅ GET /api/attendance/

Roles: admin, teacher
Description: List / filter attendance

Query Example
/api/attendance/?student_id=<sid>&classroom_id=<cid>&date=2025-11-09

Response
{"success": true, "data": [...]}

✅ POST /api/attendance/

Roles: admin, teacher
Description: Mark attendance

Request
{"student_id": "61...", "date": "2025-11-09", "present": true, "remarks": ""}

Response
{"success": true, "id": "65d..."}

✅ GET /api/attendance/<aid>

Roles: admin, teacher, student
Description: Get attendance by ID

Response
{"success": true, "data": {...}}

✅ PUT /api/attendance/<aid>

Roles: admin
Description: Update attendance

Request
{...updated_fields}

Response
{"success": true}

✅ DELETE /api/attendance/<aid>

Roles: admin
Description: Delete attendance

Response
{"success": true}

✅ GET /api/classrooms/

Roles: admin, teacher
Description: List classrooms

Response
{"success": true, "data": [...]}

✅ POST /api/classrooms/

Roles: admin
Description: Create classroom

Request
{"name": "12A", "student_ids": [...]}

Response
{"success": true, "id": "65f..."}

✅ GET /api/classrooms/<cid>

Roles: admin, teacher, student
Description: Get classroom by ID

Response
{"success": true, "data": {...}}

✅ PUT /api/classrooms/<cid>

Roles: admin
Description: Update classroom

Request
{...updated_fields}

Response
{"success": true}

✅ DELETE /api/classrooms/<cid>

Roles: admin
Description: Delete classroom

Response
{"success": true}

✅ POST /api/classrooms/<cid>/add_students

Roles: admin, teacher
Description: Add students

Request
{"student_ids": ["id1", "id2"]}

Response
{"success": true}

✅ POST /api/classrooms/<cid>/remove_students

Roles: admin, teacher
Description: Remove students

Request
{"student_ids": ["id1"]}

Response
{"success": true}

✅ GET /api/classrooms/<cid>/students

Roles: admin, teacher
Description: List students in a classroom

Response
{"success": true, "student_ids": [...]}

✅ GET /api/students/

Roles: admin, teacher
Description: List all students

Response
{"success": true, "data": [...]}

✅ POST /api/students/

Roles: admin
Description: Add student

Request
{"name": "Ravi", ...}

Response
{"success": true, "id": "66..."}

✅ GET /api/teachers/

Roles: admin
Description: List all teachers

Response
{"success": true, "data": [...]}

✅ POST /api/teachers/

Roles: admin
Description: Add teacher

Request
{"name": "Sonia", ...}

Response
{"success": true, "id": "678..."}

✅ GET /api/teachers/<tid>

Roles: admin, teacher
Description: Get teacher info

Response
{"success": true, "data": {...}}

✅ PUT /api/teachers/<tid>

Roles: admin
Description: Update teacher

Request
{...updated_fields}

Response
{"success": true}

✅ DELETE /api/teachers/<tid>

Roles: admin
Description: Delete teacher

Response
{"success": true}

✅ POST /api/teachers/<tid>/assign_classroom

Roles: admin
Description: Assign classroom to teacher

Request
{"classroom_id": "66..."}

Response
{"success": true}

✅ POST /api/teachers/<tid>/remove_classroom

Roles: admin
Description: Remove classroom from teacher

Request
{"classroom_id": "66..."}

Response
{"success": true}

✅ GET /api/report

Roles: admin, teacher
Description: Attendance report

Example
/api/report?student_id=...&month=2025-11

Response
{
  "success": true,
  "data": {
    "student_id": "...",
    "attendance_percent": 94.5
  }
}

✅ GET /api/report
Roles: admin, teacher
Description: Attendance report

Example
/api/report?student_id=...&month=2025-11

Response
{
  "success": true,
  "data": {
    "student_id": "...",
    "attendance_percent": 94.5
  }
}

# API Documentation

| Endpoint                    | Method | Roles                   | Description           | Sample Request / Response |
|-----------------------------|--------|--------------------------|------------------------|----------------------------|
| `/api/register`            | POST   | All                      | User registration      | Req: `{ "username": "raj","email": "raj@gmail.com","password": "abc123","role": "teacher" }`<br>Res: `{ "success": true,"user_id": "65d..." }` |

| `/api/login`               | POST   | All                      | User login (JWT)       | Req: `{ "username": "raj","password": "abc123" }`<br>Res: `{ "success": true,"message": "Login successful","access_token": "<JWT>","user": {"username":"raj","role":"teacher"} }` |

---

## ✅ Attendance Routes

| Endpoint                    | Method | Roles                   | Description           | Sample |
|-----------------------------|--------|--------------------------|------------------------|---------|
| `/api/attendance/`         | GET    | admin, teacher          | List / filter attendance | `/api/attendance?student_id=<sid>&classroom_id=<cid>&date=2025-11-09`<br>Res: `{ "success": true, "data": [...] }` |


| `/api/attendance/`         | POST   | admin, teacher          | Mark attendance       | Req: `{ "student_id": "61...","date": "2025-11-09","present": true,"remarks": "" }`<br>Res: `{ "success": true, "id": "65d..." }` |


| `/api/attendance/<aid>`    | GET    | admin, teacher, student | Get attendance by ID  | Res: `{ "success": true, "data": {...} }

` |
| `/api/attendance/<aid>`    | PUT    | admin                   | Update attendance     | Req: `{ ...updated fields... }`<br>Res: 
`{ "success": true }` |

| `/api/attendance/<aid>`    | DELETE | admin                   | Delete attendance     | Res: `{ "success": true }` |

---

## ✅ Classroom Routes

| Endpoint                      | Method | Roles                   | Description         | Sample |
|-------------------------------|--------|--------------------------|----------------------|--------|
| `/api/classrooms/`           | GET    | admin, teacher          | List classrooms     | Res: `{ "success": true, "data": [...] }` |

| `/api/classrooms/`           | POST   | admin                   | Create classroom    | Req: `{ "name": "12A", "student_ids": [...] }`<br>Res: `{ "success": true,"id": "65f..." }` |

| `/api/classrooms/<cid>`      | GET    | admin, teacher, student | Get classroom by ID | Res: `{ "success": true, "data": {...} }` |

| `/api/classrooms/<cid>`      | PUT    | admin                   | Update classroom    | Req: `{ ...updated fields... }`<br>Res: `{ "success": true }` |

---

✅ बस इतना ही — अब ये एकदम compact, clean, readable और horizontally कम जगह लेने वाला table है।  
अगर चाहो तो मैं इसका **dark theme**, **emoji variants**, या **Redoc/OpenAPI style** version भी बना दूँ।
