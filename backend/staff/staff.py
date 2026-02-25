from flask import Blueprint, request, jsonify
from common.db import db_cursor, db_conn
from common.requireRole import require_role

transactions_bp = Blueprint('transactions', __name__)


@transactions_bp.route('/api/transactions', methods=['GET'])
@require_role(['STAFF', 'ADMIN'])
def get_all_transactions():
    """Chỉ STAFF và ADMIN mới được xem danh sách giao dịch."""
    status_filter = request.args.get('status')
    
    query = """
        SELECT
            t.transaction_id,
            u.full_name AS customer_name,
            t.amount,
            t.transaction_type,
            t.status,
            t.created_at
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
    """
    params = []
    
    if status_filter:
        query += " WHERE t.status = %s"
        params.append(status_filter)
        
    query += " ORDER BY t.created_at DESC"
    
    try:
        db_cursor.execute(query, tuple(params))
        rows = db_cursor.fetchall()

        transactions = [
            {
                'transaction_id':   row[0],
                'customer_name':    row[1],
                'amount':           float(row[2]),
                'transaction_type': row[3],
                'status':           row[4],
                'created_at':       str(row[5]),
            }
            for row in rows
        ]
        return jsonify({
            'message':      'Danh sách lịch sử giao dịch',
            'total':        len(transactions),
            'transactions': transactions
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/transactions/<int:transaction_id>/approve', methods=['PUT'])
@require_role(['STAFF', 'ADMIN'])
def approve_transaction(transaction_id):
    """Duyệt phiếu yêu cầu và thực thi thay đổi vào Database."""
    staff_id = request.user_data.get('user_id')
    try:
        db_cursor.execute("SELECT user_id, account_id, amount, transaction_type, status FROM transactions WHERE transaction_id = %s", (transaction_id,))
        txn = db_cursor.fetchone()
        
        if not txn:
            return jsonify({'message': 'Không tìm thấy giao dịch!'}), 404
            
        user_id, account_id, amount, transaction_type, status = txn
        amount = float(amount)
        
        if status != 'PENDING':
            return jsonify({'message': f'Giao dịch không ở trạng thái PENDING (Hiện tại: {status})'}), 400
            
        if transaction_type == 'DEPOSIT_TO_WALLET':
            db_cursor.execute("UPDATE users SET wallet_balance = wallet_balance + %s WHERE user_id = %s", (amount, user_id))
            
        elif transaction_type == 'WITHDRAW_FROM_WALLET':
            db_cursor.execute("SELECT wallet_balance FROM users WHERE user_id = %s", (user_id,))
            wallet = float(db_cursor.fetchone()[0])
            if wallet < amount:
                return jsonify({'message': 'Số dư ví không đủ để rút!'}), 400
            db_cursor.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE user_id = %s", (amount, user_id))
            
        elif transaction_type == 'OPEN_SAVINGS':
            db_cursor.execute("SELECT wallet_balance FROM users WHERE user_id = %s", (user_id,))
            wallet = float(db_cursor.fetchone()[0])
            if wallet < amount:
                return jsonify({'message': 'Số dư trong ví không đủ để mở sổ tiết kiệm!'}), 400
            db_cursor.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE user_id = %s", (amount, user_id))
            # The savings_account might only need its status updated to ACTIVE if it was created in a sort of PENDING state 
            # Or if it's already ACTIVE, we just deduct money from wallet. 
            pass
            
        elif transaction_type == 'CLOSE_SAVINGS':
            db_cursor.execute("UPDATE users SET wallet_balance = wallet_balance + %s WHERE user_id = %s", (amount, user_id))
            if account_id:
                db_cursor.execute("UPDATE savings_accounts SET status = 'CLOSED' WHERE account_id = %s", (account_id,))

        db_cursor.execute("UPDATE transactions SET status = 'APPROVED', processed_by = %s WHERE transaction_id = %s", (staff_id, transaction_id))
        db_conn.commit()
        return jsonify({'message': 'Duyệt giao dịch thành công!'}), 200
        
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/transactions/<int:transaction_id>/reject', methods=['PUT'])
@require_role(['STAFF', 'ADMIN'])
def reject_transaction(transaction_id):
    """Từ chối phiếu yêu cầu."""
    staff_id = request.user_data.get('user_id')
    try:
        db_cursor.execute("SELECT status, transaction_type, account_id FROM transactions WHERE transaction_id = %s", (transaction_id,))
        txn = db_cursor.fetchone()
        
        if not txn:
            return jsonify({'message': 'Không tìm thấy giao dịch!'}), 404
            
        status, transaction_type, account_id = txn
        if status != 'PENDING':
            return jsonify({'message': f'Giao dịch không ở trạng thái PENDING (Hiện tại: {status})'}), 400
            
        db_cursor.execute("UPDATE transactions SET status = 'REJECTED', processed_by = %s WHERE transaction_id = %s", (staff_id, transaction_id))
        
        # We can close the savings account if it was somehow created right away during OPEN_SAVINGS request.
        if transaction_type == 'OPEN_SAVINGS' and account_id:
            db_cursor.execute("UPDATE savings_accounts SET status = 'CLOSED' WHERE account_id = %s", (account_id,))
            
        db_conn.commit()
        return jsonify({'message': 'Đã từ chối giao dịch!'}), 200
        
    except Exception as e:
        db_conn.rollback()
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/balance-system', methods=['GET'])
@require_role(['STAFF', 'ADMIN'])
def get_system_balance():
    """Xem tổng số dư ví và tổng tiền gốc tiết kiệm của toàn hệ thống."""
    try:
        db_cursor.execute("SELECT SUM(wallet_balance) FROM users WHERE role = 'CUSTOMER'")
        total_wallet = db_cursor.fetchone()[0] or 0.0
        
        db_cursor.execute("SELECT SUM(principal_balance) FROM savings_accounts WHERE status = 'ACTIVE'")
        total_savings = db_cursor.fetchone()[0] or 0.0
        
        return jsonify({
            'message': 'Cân đối hệ thống',
            'total_wallet_balance': float(total_wallet),
            'total_savings_principal': float(total_savings)
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/users', methods=['GET'])
@require_role(['STAFF', 'ADMIN'])
def get_customers():
    """Lấy danh sách thông tin khách hàng (role CUSTOMER)."""
    try:
        db_cursor.execute("""
            SELECT user_id, full_name, email, identity_card, wallet_balance, status, created_at 
            FROM users 
            WHERE role = 'CUSTOMER'
            ORDER BY created_at DESC
        """)
        rows = db_cursor.fetchall()
        users = [
            {
                'user_id': row[0],
                'full_name': row[1],
                'email': row[2],
                'identity_card': row[3],
                'wallet_balance': float(row[4]),
                'status': row[5],
                'created_at': str(row[6])
            }
            for row in rows
        ]
        return jsonify({
            'message': 'Danh sách khách hàng',
            'total': len(users),
            'users': users
        })
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/savings-accounts', methods=['GET'])
@require_role(['STAFF', 'ADMIN'])
def get_all_savings_accounts():
    """Lấy danh sách toàn bộ sổ tiết kiệm."""
    try:
        db_cursor.execute("""
            SELECT 
                s.account_id, u.full_name AS customer_name, p.name AS product_name,
                s.principal_balance, s.opened_at, s.status, p.interest_rate, p.term_months
            FROM savings_accounts s
            JOIN users u ON s.user_id = u.user_id
            JOIN savings_products p ON s.product_id = p.product_id
            ORDER BY s.opened_at DESC
        """)
        rows = db_cursor.fetchall()
        accounts = [
            {
                'account_id': row[0],
                'customer_name': row[1],
                'product_name': row[2],
                'principal_balance': float(row[3]),
                'opened_at': str(row[4]),
                'status': row[5],
                'interest_rate': float(row[6]),
                'term_months': row[7]
            }
            for row in rows
        ]
        return jsonify({
            'message': 'Danh sách sổ tiết kiệm',
            'total': len(accounts),
            'accounts': accounts
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500


@transactions_bp.route('/api/savings-accounts/<int:account_id>', methods=['GET'])
@require_role(['STAFF', 'ADMIN'])
def get_savings_account_detail(account_id):
    """Xem chi tiết một sổ tiết kiệm cụ thể."""
    try:
        db_cursor.execute("""
            SELECT 
                s.account_id, u.full_name, u.identity_card, p.name,
                s.principal_balance, s.opened_at, s.status, p.interest_rate, p.term_months, p.min_days_hold
            FROM savings_accounts s
            JOIN users u ON s.user_id = u.user_id
            JOIN savings_products p ON s.product_id = p.product_id
            WHERE s.account_id = %s
        """, (account_id,))
        row = db_cursor.fetchone()
        
        if not row:
            return jsonify({'message': 'Không tìm thấy sổ tiết kiệm!'}), 404
            
        account = {
            'account_id': row[0],
            'customer_name': row[1],
            'identity_card': row[2],
            'product_name': row[3],
            'principal_balance': float(row[4]),
            'opened_at': str(row[5]),
            'status': row[6],
            'interest_rate': float(row[7]),
            'term_months': row[8],
            'min_days_hold': row[9]
        }
        return jsonify({
            'message': 'Chi tiết sổ tiết kiệm',
            'account': account
        }), 200
    except Exception as e:
        return jsonify({'message': 'Lỗi server!', 'error': str(e)}), 500

