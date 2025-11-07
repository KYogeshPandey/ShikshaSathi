from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    
    username = data['username']
    password = data['password']
    
    if username == 'admin' and password == 'admin123':
        access_token = create_access_token(
            identity=username,
            expires_delta=timedelta(hours=1)
        )
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'access_token': access_token,
            'user': {'username': username, 'role': 'admin'}
        }), 200
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not all(k in data for k in ['username', 'password', 'email']):
        return jsonify({'success': False, 'message': 'All fields required'}), 400
    
    return jsonify({
        'success': True,
        'message': 'User registered',
        'user': {'username': data['username'], 'email': data['email']}
    }), 201

@bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    current_user = get_jwt_identity()
    return jsonify({'success': True, 'user': {'username': current_user}}), 200