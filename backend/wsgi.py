from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ShikshaSathi Backend Server Starting...")
    print("=" * 60)
    print("📍 Server: http://localhost:5000")
    print("🔍 Health: http://localhost:5000/health")
    print("🔐 API: http://localhost:5000/api/v1")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)