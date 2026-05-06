import sqlite3
import os

db_path = "plc_monitor.db"
if not os.path.exists(db_path):
    # Try alternate path if any? No, based on logs it's there.
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- register_library schema ---")
cursor.execute("PRAGMA table_info(register_library)")
for row in cursor.fetchall():
    print(dict(row))

print("\n--- io_list_config schema ---")
cursor.execute("PRAGMA table_info(io_list_config)")
for row in cursor.fetchall():
    print(dict(row))

conn.close()
