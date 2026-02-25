from functools import wraps
from flask import request, jsonify, current_app
import jwt


def require_role(allowed_roles):
    """Decorator bảo vệ route – chỉ cho phép các role trong allowed_roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')

            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'message': 'Thiếu token hoặc sai định dạng!'}), 401

            token = auth_header.split(' ')[1]

            try:
                payload = jwt.decode(
                    token,
                    current_app.config['SECRET_KEY'],
                    algorithms=['HS256']
                )

                user_role = payload.get('role')
                if user_role not in allowed_roles:
                    return jsonify({'message': 'Cấm truy cập: Bạn không đủ quyền!'}), 403

                request.user_data = payload

            except jwt.ExpiredSignatureError:
                return jsonify({'message': 'Token đã hết hạn, vui lòng đăng nhập lại!'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'message': 'Token không hợp lệ!'}), 401

            return f(*args, **kwargs)
        return decorated_function
    return decorator