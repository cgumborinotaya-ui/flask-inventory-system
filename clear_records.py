import sqlite3

conn = sqlite3.connect("instance/inventory.db")
cursor = conn.cursor()

# Tables you WANT to clear
tables_to_clear = [
    "asset",
    "audit_log",
    "password_reset_token"
]

for table in tables_to_clear:
    cursor.execute(f"DELETE FROM {table}")



conn.commit()
conn.close()

print("✅ Records cleared. Users preserved.")
