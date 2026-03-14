import sqlite3
import os

db_path = "vibecoding_users.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id, username, email FROM users").fetchall()
    for user in users:
        print(f"ID: {user['id']} | Username: {user['username']} | Email: {user['email']}")
    conn.close()
else:
    print("Database not found")
