from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from common.db import db_cursor, db_conn
from common.requireRole import require_role

admin_bp = Blueprint('admin', __name__)


# ============================================================
#  1. DASHBOARD - THỐNG KÊ TỔNG QUAN
# ============================================================

@admin_bp.route('/api/admin/dashboard', methods=['GET'])
@require_role(['ADMIN'])
def admin_dashboard():
    """Lấy thống kê tổng quan cho Admin Dashboard."""
    try:
        # Tổng số khách hàng
        db_cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'CUSTOMER'")
        total_customers = db_cursor.fetchone()[0]

        # Tổng số nhân viên
        db_cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'STAFF'")
        total_staff = db_cursor.fetchone()[0]

        # Tổng số admin
        db_cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
        total_admins = db_cursor.fetchone()[0]

        # Tổng số sổ tiết kiệm đang hoạt động
        db_cursor.execute("SELECT COUNT(*) FROM savings_accounts WHERE status = 'ACTIVE'")
        active_savings = db_cursor.fetchone()[0]

        # Tổng tiền gốc đang gửi tiết kiệm
        db_cursor.execute("SELECT COALESCE(SUM(principal_balance), 0) FROM savings_accounts WHERE status = 'ACTIVE'")
        total_savings_amount = float(db_cursor.fetchone()[0])

        # Tổng số giao dịch đang chờ duyệt
        db_cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'PENDING'")
        pending_transactions = db_cursor.fetchone()[0]

        # Số gói tiết kiệm đang hoạt động
        db_cursor.execute("SELECT COUNT(*) FROM savings_products WHERE is_active = TRUE")
        active_products = db_cursor.fetchone()[0]

        # Tổng số tài khoản bị khóa
        db_cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'LOCKED'")
        locked_accounts = db_cursor.fetchone()[0]

        return jsonify({
            'message': 'Thống kê tổng quan',
            'data': {
                'total_customers': total_customers,
                'total_staff': total_staff,
                'total_admins': total_admins,
                'active_savings_accounts': active_savings,
                'total_savings_amount': total_savings_amount,
                'pending_transactions': pending_transactions,
                'active_products': active_products,
                'locked_accounts': locked_accounts
            }
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


# ============================================================
#  2. QUẢN LÝ NGƯỜI DÙNG (USER MANAGEMENT)
# ============================================================

@admin_bp.route('/api/admin/users', methods=['GET'])
@require_role(['ADMIN'])
def get_all_users():
    """Lấy danh sách tất cả người dùng, hỗ trợ filter theo role và status."""
    role_filter = request.args.get('role')       # VD: ?role=STAFF
    status_filter = request.args.get('status')   # VD: ?status=ACTIVE
    search = request.args.get('search')          # VD: ?search=Nguyen

    query = """
        SELECT user_id, email, full_name, identity_card, role,
               wallet_balance, status, created_at
        FROM users
        WHERE 1=1
    """
    params = []

    if role_filter:
        query += " AND role = %s"
        params.append(role_filter)

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if search:
        query += " AND (full_name LIKE %s OR email LIKE %s OR identity_card LIKE %s)"
        like_pattern = f"%{search}%"
        params.extend([like_pattern, like_pattern, like_pattern])

    query += " ORDER BY created_at DESC"

    try:
        db_cursor.execute(query, tuple(params))
        rows = db_cursor.fetchall()

        users = [
            {
                'user_id': row[0],
                'email': row[1],
                'full_name': row[2],
                'identity_card': row[3],
                'role': row[4],
                'wallet_balance': float(row[5]),
                'status': row[6],
                'created_at': str(row[7])
            }
            for row in rows
        ]
        return jsonify({
            'message': 'Danh sách người dùng',
            'total': len(users),
            'users': users
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['GET'])
@require_role(['ADMIN'])
def get_user_detail(user_id):
    """Xem chi tiết thông tin một người dùng."""
    try:
        db_cursor.execute("""
            SELECT user_id, email, full_name, identity_card, role,
                   wallet_balance, status, created_at
            FROM users WHERE user_id = %s
        """, (user_id,))
        row = db_cursor.fetchone()

        if not row:
            return jsonify({'message': 'Không tìm thấy người dùng!'}), 404

        user = {
            'user_id': row[0],
            'email': row[1],
            'full_name': row[2],
            'identity_card': row[3],
            'role': row[4],
            'wallet_balance': float(row[5]),
            'status': row[6],
            'created_at': str(row[7])
        }

        # Lấy thêm danh sách sổ tiết kiệm của user này
        db_cursor.execute("""
            SELECT s.account_id, p.name AS product_name, s.principal_balance,
                   s.opened_at, s.status
            FROM savings_accounts s
            JOIN savings_products p ON s.product_id = p.product_id
            WHERE s.user_id = %s
            ORDER BY s.opened_at DESC
        """, (user_id,))
        savings_rows = db_cursor.fetchall()

        user['savings_accounts'] = [
            {
                'account_id': sr[0],
                'product_name': sr[1],
                'principal_balance': float(sr[2]),
                'opened_at': str(sr[3]),
                'status': sr[4]
            }
            for sr in savings_rows
        ]

        return jsonify({
            'message': 'Chi tiết người dùng',
            'user': user
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/users', methods=['POST'])
@require_role(['ADMIN'])
def create_user():
    """Tạo tài khoản Staff hoặc Admin mới."""
    data = request.get_json()

    email         = data.get('email')
    password      = data.get('password')
    full_name     = data.get('full_name')
    identity_card = data.get('identity_card')
    role          = data.get('role', 'STAFF')  # Mặc định tạo STAFF

    # Validate đầu vào
    if not email or not password or not full_name:
        return jsonify({'message': 'Vui lòng điền đủ thông tin (email, password, full_name)!'}), 400

    if role not in ('CUSTOMER', 'STAFF', 'ADMIN'):
        return jsonify({'message': 'Role không hợp lệ! Chỉ chấp nhận: CUSTOMER, STAFF, ADMIN'}), 400

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    try:
        sql = """INSERT INTO users (email, password_hash, full_name, identity_card, role)
                 VALUES (%s, %s, %s, %s, %s)"""
        db_cursor.execute(sql, (email, hashed_password, full_name, identity_card, role))
        db_conn.commit()

        return jsonify({
            'message': f'Tạo tài khoản {role} thành công!',
            'user_id': db_cursor.lastrowid
        }), 201
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Email hoặc CMND/CCCD đã tồn tại!', 'error': str(e)}), 400


@admin_bp.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
@require_role(['ADMIN'])
def change_user_role(user_id):
    """Thay đổi role của một người dùng (CUSTOMER ↔ STAFF ↔ ADMIN)."""
    data = request.get_json()
    new_role = data.get('role')

    if new_role not in ('CUSTOMER', 'STAFF', 'ADMIN'):
        return jsonify({'message': 'Role không hợp lệ! Chỉ chấp nhận: CUSTOMER, STAFF, ADMIN'}), 400

    admin_id = request.user_data.get('user_id')
    if user_id == admin_id:
        return jsonify({'message': 'Không thể thay đổi role của chính mình!'}), 400

    try:
        db_cursor.execute("SELECT user_id, role FROM users WHERE user_id = %s", (user_id,))
        user = db_cursor.fetchone()

        if not user:
            return jsonify({'message': 'Không tìm thấy người dùng!'}), 404

        old_role = user[1]
        if old_role == new_role:
            return jsonify({'message': f'Người dùng đã có role {new_role} rồi!'}), 400

        db_cursor.execute("UPDATE users SET role = %s WHERE user_id = %s", (new_role, user_id))
        db_conn.commit()

        return jsonify({
            'message': f'Đã thay đổi role từ {old_role} sang {new_role}!',
            'user_id': user_id,
            'old_role': old_role,
            'new_role': new_role
        }), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@require_role(['ADMIN'])
def toggle_user_status(user_id):
    """Khóa hoặc mở khóa tài khoản người dùng (ACTIVE ↔ LOCKED)."""
    data = request.get_json()
    new_status = data.get('status')

    if new_status not in ('ACTIVE', 'LOCKED'):
        return jsonify({'message': 'Status không hợp lệ! Chỉ chấp nhận: ACTIVE, LOCKED'}), 400

    admin_id = request.user_data.get('user_id')
    if user_id == admin_id:
        return jsonify({'message': 'Không thể khóa chính tài khoản của mình!'}), 400

    try:
        db_cursor.execute("SELECT user_id, status FROM users WHERE user_id = %s", (user_id,))
        user = db_cursor.fetchone()

        if not user:
            return jsonify({'message': 'Không tìm thấy người dùng!'}), 404

        old_status = user[1]
        if old_status == new_status:
            return jsonify({'message': f'Tài khoản đã ở trạng thái {new_status} rồi!'}), 400

        db_cursor.execute("UPDATE users SET status = %s WHERE user_id = %s", (new_status, user_id))
        db_conn.commit()

        action = 'Khóa' if new_status == 'LOCKED' else 'Mở khóa'
        return jsonify({
            'message': f'{action} tài khoản thành công!',
            'user_id': user_id,
            'old_status': old_status,
            'new_status': new_status
        }), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


# ============================================================
#  3. QUẢN LÝ GÓI TIẾT KIỆM (SAVINGS PRODUCTS - QĐ6)
# ============================================================

@admin_bp.route('/api/admin/savings-products', methods=['GET'])
@require_role(['ADMIN'])
def get_all_products():
    """Lấy danh sách tất cả gói tiết kiệm (kể cả đã tắt)."""
    try:
        db_cursor.execute("""
            SELECT product_id, name, term_months, interest_rate,
                   min_days_hold, is_active, description
            FROM savings_products
            ORDER BY term_months ASC
        """)
        rows = db_cursor.fetchall()

        products = [
            {
                'product_id': row[0],
                'name': row[1],
                'term_months': row[2],
                'interest_rate': float(row[3]),
                'min_days_hold': row[4],
                'is_active': bool(row[5]),
                'description': row[6]
            }
            for row in rows
        ]
        return jsonify({
            'message': 'Danh sách gói tiết kiệm',
            'total': len(products),
            'products': products
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/savings-products', methods=['POST'])
@require_role(['ADMIN'])
def create_product():
    """Thêm gói tiết kiệm mới (QĐ6)."""
    data = request.get_json()

    name          = data.get('name')
    term_months   = data.get('term_months')
    interest_rate = data.get('interest_rate')
    min_days_hold = data.get('min_days_hold', 0)
    description   = data.get('description', '')

    # Validate
    if not name or term_months is None or interest_rate is None:
        return jsonify({'message': 'Vui lòng điền đủ thông tin (name, term_months, interest_rate)!'}), 400

    if not isinstance(term_months, int) or term_months < 0:
        return jsonify({'message': 'term_months phải là số nguyên >= 0!'}), 400

    if float(interest_rate) < 0:
        return jsonify({'message': 'interest_rate phải >= 0!'}), 400

    try:
        sql = """INSERT INTO savings_products (name, term_months, interest_rate, min_days_hold, description)
                 VALUES (%s, %s, %s, %s, %s)"""
        db_cursor.execute(sql, (name, term_months, interest_rate, min_days_hold, description))
        db_conn.commit()

        return jsonify({
            'message': 'Thêm gói tiết kiệm thành công!',
            'product_id': db_cursor.lastrowid
        }), 201
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/savings-products/<int:product_id>', methods=['PUT'])
@require_role(['ADMIN'])
def update_product(product_id):
    """Cập nhật thông tin gói tiết kiệm (QĐ6): lãi suất, min_days_hold, mô tả..."""
    data = request.get_json()

    try:
        # Kiểm tra gói có tồn tại không
        db_cursor.execute("SELECT product_id FROM savings_products WHERE product_id = %s", (product_id,))
        if not db_cursor.fetchone():
            return jsonify({'message': 'Không tìm thấy gói tiết kiệm!'}), 404

        # Xây dựng câu UPDATE động dựa trên các field được gửi lên
        updatable_fields = ['name', 'term_months', 'interest_rate', 'min_days_hold', 'is_active', 'description']
        set_clauses = []
        values = []

        for field in updatable_fields:
            if field in data:
                set_clauses.append(f"{field} = %s")
                values.append(data[field])

        if not set_clauses:
            return jsonify({'message': 'Không có trường nào để cập nhật!'}), 400

        values.append(product_id)
        sql = f"UPDATE savings_products SET {', '.join(set_clauses)} WHERE product_id = %s"
        db_cursor.execute(sql, tuple(values))
        db_conn.commit()

        return jsonify({
            'message': 'Cập nhật gói tiết kiệm thành công!',
            'product_id': product_id
        }), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/savings-products/<int:product_id>/toggle', methods=['PUT'])
@require_role(['ADMIN'])
def toggle_product(product_id):
    """Bật/Tắt gói tiết kiệm (is_active toggle)."""
    try:
        db_cursor.execute("SELECT product_id, is_active FROM savings_products WHERE product_id = %s", (product_id,))
        row = db_cursor.fetchone()

        if not row:
            return jsonify({'message': 'Không tìm thấy gói tiết kiệm!'}), 404

        new_active = not bool(row[1])
        db_cursor.execute("UPDATE savings_products SET is_active = %s WHERE product_id = %s", (new_active, product_id))
        db_conn.commit()

        status_text = 'Bật' if new_active else 'Tắt'
        return jsonify({
            'message': f'{status_text} gói tiết kiệm thành công!',
            'product_id': product_id,
            'is_active': new_active
        }), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


# ============================================================
#  4. CẤU HÌNH THAM SỐ HỆ THỐNG (SYSTEM CONFIGS - QĐ6)
# ============================================================

@admin_bp.route('/api/admin/configs', methods=['GET'])
@require_role(['ADMIN'])
def get_all_configs():
    """Lấy tất cả tham số cấu hình hệ thống."""
    try:
        db_cursor.execute("SELECT config_key, config_value, description FROM system_configs ORDER BY config_key")
        rows = db_cursor.fetchall()

        configs = [
            {
                'config_key': row[0],
                'config_value': row[1],
                'description': row[2]
            }
            for row in rows
        ]
        return jsonify({
            'message': 'Danh sách tham số hệ thống',
            'total': len(configs),
            'configs': configs
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/configs/<string:config_key>', methods=['PUT'])
@require_role(['ADMIN'])
def update_config(config_key):
    """Cập nhật giá trị của một tham số hệ thống (QĐ6)."""
    data = request.get_json()
    new_value = data.get('config_value')

    if new_value is None:
        return jsonify({'message': 'Vui lòng cung cấp config_value!'}), 400

    try:
        db_cursor.execute("SELECT config_key FROM system_configs WHERE config_key = %s", (config_key,))
        if not db_cursor.fetchone():
            return jsonify({'message': f'Không tìm thấy tham số: {config_key}'}), 404

        # Cập nhật mô tả nếu có gửi kèm
        description = data.get('description')
        if description:
            db_cursor.execute(
                "UPDATE system_configs SET config_value = %s, description = %s WHERE config_key = %s",
                (str(new_value), description, config_key)
            )
        else:
            db_cursor.execute(
                "UPDATE system_configs SET config_value = %s WHERE config_key = %s",
                (str(new_value), config_key)
            )

        db_conn.commit()

        return jsonify({
            'message': f'Cập nhật tham số {config_key} thành công!',
            'config_key': config_key,
            'config_value': str(new_value)
        }), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@admin_bp.route('/api/admin/configs', methods=['POST'])
@require_role(['ADMIN'])
def create_config():
    """Thêm tham số hệ thống mới."""
    data = request.get_json()

    config_key   = data.get('config_key')
    config_value = data.get('config_value')
    description  = data.get('description', '')

    if not config_key or config_value is None:
        return jsonify({'message': 'Vui lòng điền đủ config_key và config_value!'}), 400

    try:
        sql = "INSERT INTO system_configs (config_key, config_value, description) VALUES (%s, %s, %s)"
        db_cursor.execute(sql, (config_key, str(config_value), description))
        db_conn.commit()

        return jsonify({
            'message': 'Thêm tham số hệ thống thành công!',
            'config_key': config_key
        }), 201
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Tham số đã tồn tại hoặc lỗi server!', 'error': str(e)}), 400


@admin_bp.route('/api/admin/configs/<string:config_key>', methods=['DELETE'])
@require_role(['ADMIN'])
def delete_config(config_key):
    """Xóa một tham số hệ thống."""
    try:
        db_cursor.execute("SELECT config_key FROM system_configs WHERE config_key = %s", (config_key,))
        if not db_cursor.fetchone():
            return jsonify({'message': f'Không tìm thấy tham số: {config_key}'}), 404

        db_cursor.execute("DELETE FROM system_configs WHERE config_key = %s", (config_key,))
        db_conn.commit()

        return jsonify({'message': f'Đã xóa tham số {config_key}!'}), 200
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500
