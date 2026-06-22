import sqlite3
import os

db_path = "newsdraftbot/database/news.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check the 'images' JSON column too
    cursor.execute("SELECT id, featured_image, images FROM articles WHERE id = 42")
    row = cursor.fetchone()
    if row:
        print(f"ID: {row[0]}")
        print(f"Featured Image: {row[1]}")
        print(f"Images: {row[2]}")
    conn.close()
