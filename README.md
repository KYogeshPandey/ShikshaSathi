# ShikshaSathi 🎓

AI-Powered Smart Classroom & Learning Platform

## 🌟 Features
- 📸 Face Recognition Attendance
- 👨‍🎓 Student Management  
- 🏫 Classroom Administration
- 📊 Analytics Dashboard
- 🤖 AI-Powered Remediation

## ✅ Backend Status: FULLY WORKING

All API endpoints tested and functional:
- ✅ Health check
- ✅ Authentication (Login/Register)
- ✅ JWT token generation
- ✅ Protected routes

## 🚀 Quick Start

### Backend Setup
\\\ash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python wsgi.py
\\\

Server: http://localhost:5000

### Test API
\\\powershell
# Health check
Invoke-RestMethod -Uri 'http://localhost:5000/health'

# Login
\ = @{username='admin'; password='admin123'} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5000/api/v1/auth/login' -Method POST -Body \ -ContentType 'application/json'
\\\

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | \/\ | API info |
| GET | \/health\ | Health check |
| POST | \/api/v1/auth/login\ | User login |
| POST | \/api/v1/auth/register\ | User registration |
| GET | \/api/v1/auth/me\ | Get current user |

## 🛠️ Tech Stack

**Backend:** Flask 3.0, PyMongo 4.6, Flask-JWT-Extended 4.6, OpenCV 4.9, MTCNN 0.1

**Frontend (Coming Soon):** React 18, Vite, TailwindCSS 3, Zustand

## 📁 Project Structure
\\\
ShikshaSathi/
├── backend/
│   ├── app/api/v1/
│   ├── app/core/
│   ├── app/services/
│   ├── app/models/
│   └── wsgi.py
├── docs/
└── README.md
\\\

## 📊 Development Progress

### Completed ✅
- Backend setup
- API versioning
- JWT authentication
- Health check endpoints
- All API testing successful

### Coming Soon 🚧
- MongoDB integration
- Face recognition module
- Frontend development

## 🤝 Contributing

Built for **HackwithUttarpradesh** initiative.

## 📄 License

MIT License

---

**Built with ❤️ for better education in India**
