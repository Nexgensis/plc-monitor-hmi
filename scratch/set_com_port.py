import sqlite3
import os

db_path = 'plc_monitor.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE plc_profile SET com_port = 'COM4' WHERE id = 1")
    conn.commit()
    conn.close()
    print("Database updated: PLC COM Port set to COM4")
else:
    print("Database not found")
