import mysql.connector

# ⚠️ Sửa password cho đúng môi trường của bạn
db_conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',
    database='modern_savings_db'
)
db_cursor = db_conn.cursor()
