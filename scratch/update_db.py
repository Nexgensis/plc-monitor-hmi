import sqlite3
import os

db_path = 'plc_monitor.db'
if not os.path.exists(db_path):
    print(f"Database {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
try:
    # Check if columns exist
    cursor = conn.execute("PRAGMA table_info(plc_profile)")
    columns = [row['name'] for row in cursor.fetchall()]
    
    # If columns don't exist, we might need to run migration 001 first.
    # But I assume migration was applied based on logs.
    
    sql = """
    UPDATE plc_profile 
    SET brand='delta', 
        protocol='RTU', 
        com_port='COM2', 
        baud_rate=9600, 
        data_bits=7, 
        parity='E', 
        stop_bits=1, 
        serial_mode='ASCII' 
    WHERE id=1
    """
    conn.execute(sql)
    conn.commit()
    print("Database updated to Delta 9600 7E1 ASCII")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
