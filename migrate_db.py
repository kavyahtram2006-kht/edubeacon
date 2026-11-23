import mysql.connector

conn = mysql.connector.connect(
    host="localhost", user="root",
    password="kavya@123", database="edubeacon"
)
cursor = conn.cursor()

# Add department to notes
cursor.execute("DESCRIBE notes")
cols = [r[0] for r in cursor.fetchall()]
if "department" not in cols:
    cursor.execute("ALTER TABLE notes ADD COLUMN department VARCHAR(50) DEFAULT 'All'")
    print("Added department to notes")

# Add department to assignments
cursor.execute("DESCRIBE assignments")
cols = [r[0] for r in cursor.fetchall()]
if "department" not in cols:
    cursor.execute("ALTER TABLE assignments ADD COLUMN department VARCHAR(50) DEFAULT 'All'")
    print("Added department to assignments")

# Add department to examinations
cursor.execute("DESCRIBE examinations")
cols = [r[0] for r in cursor.fetchall()]
if "department" not in cols:
    cursor.execute("ALTER TABLE examinations ADD COLUMN department VARCHAR(50) DEFAULT 'All'")
    print("Added department to examinations")

conn.commit()
cursor.close()
conn.close()
print("Migration done!")
