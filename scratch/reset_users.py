
import sqlite3
conn = sqlite3.connect('plc_monitor.db')
cursor = conn.cursor()

# Clear existing users to let the new seeding logic work with correct format
cursor.execute("DELETE FROM users;")
conn.commit()
print("Users table cleared. Restart the app to seed default accounts.")

conn.close()
