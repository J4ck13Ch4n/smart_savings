from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import db_cursor, db_conn
import jwt
import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()

    email         = data.get('email')
    password      = data.get('password')
    full_name     = data.get('full_name')
    identity_card = data.get('identity_card')

    if not email or not password or not full_name:
        return jsonify({'message': 'Vui lòng điền đủ thông tin!'}), 400

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    try:
        sql = """INSERT INTO users (email, password_hash, full_name, identity_card)
                 VALUES (%s, %s, %s, %s)"""
        db_cursor.execute(sql, (email, hashed_password, full_name, identity_card))
        db_conn.commit()
        return jsonify({'message': 'Đăng ký thành công!'}), 201
    except Exception as e:
        return jsonify({'message': 'Email hoặc CMND/CCCD đã tồn tại!', 'error': str(e)}), 400


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json()
    email    = data.get('email')
    password = data.get('password')

    db_cursor.execute(
        "SELECT user_id, password_hash, role, status FROM users WHERE email = %s",
        (email,)
    )
    user = db_cursor.fetchone()

    if not user:
        return jsonify({'message': 'Tài khoản không tồn tại!'}), 404

    user_id, password_hash, role, status = user

    if status == 'LOCKED':
        return jsonify({'message': 'Tài khoản đã bị khóa!'}), 403

    if check_password_hash(password_hash, password):
        payload = {
            'user_id': user_id,
            'role':    role,
            'exp':     datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        }
        token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({
            'message': 'Đăng nhập thành công!',
            'token':   token,
            'role':    role
        }), 200

    return jsonify({'message': 'Sai mật khẩu!'}), 401