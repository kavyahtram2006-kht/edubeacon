"""
migrate_db2.py — Safe DB migration for EduBeacon 48-feature upgrade.
Creates new tables (IF NOT EXISTS) and adds missing columns (DESCRIBE check).
Never drops or destructively alters existing tables.
"""

import sys
import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "kavya@123",
    "database": "edubeacon",
}

# ── helpers ────────────────────────────────────────────────────────────────────

def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (DB_CONFIG["database"], table_name),
    )
    return cursor.fetchone()[0] > 0


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (DB_CONFIG["database"], table_name, column_name),
    )
    return cursor.fetchone()[0] > 0


def run(cursor, sql, label):
    try:
        cursor.execute(sql)
        print(f"  [OK]  {label}")
    except mysql.connector.Error as e:
        print(f"  [ERR] {label}: {e}")
        sys.exit(1)


# ── new tables ─────────────────────────────────────────────────────────────────

NEW_TABLES = {
    "notifications": """
        CREATE TABLE IF NOT EXISTS notifications (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            user_type   ENUM('student','faculty','cr') NOT NULL,
            notif_type  VARCHAR(50) DEFAULT 'general',
            title       VARCHAR(200),
            message     TEXT,
            is_read     TINYINT(1) DEFAULT 0,
            link        VARCHAR(300),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "attendance": """
        CREATE TABLE IF NOT EXISTS attendance (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            student_id  INT NOT NULL,
            subject     VARCHAR(100) NOT NULL,
            att_date    DATE NOT NULL,
            status      ENUM('present','absent','late') DEFAULT 'present',
            faculty_id  INT,
            department  VARCHAR(50),
            semester    VARCHAR(10),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "student_activity": """
        CREATE TABLE IF NOT EXISTS student_activity (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            student_id  INT NOT NULL,
            action      VARCHAR(100),
            detail      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "feedback": """
        CREATE TABLE IF NOT EXISTS feedback (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            user_type   ENUM('student','faculty','cr') DEFAULT 'student',
            subject     VARCHAR(200),
            message     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
}

# ── columns to add: (table, column, definition) ───────────────────────────────

NEW_COLUMNS = [
    # students
    ("students", "profile_photo", "VARCHAR(200)"),
    ("students", "dark_mode",     "TINYINT(1) DEFAULT 0"),
    ("students", "reset_token",   "VARCHAR(100)"),
    # faculty
    ("faculty",  "profile_photo", "VARCHAR(200)"),
    ("faculty",  "reset_token",   "VARCHAR(100)"),
    # cr
    ("cr",       "profile_photo", "VARCHAR(200)"),
    ("cr",       "reset_token",   "VARCHAR(100)"),
    # assignments
    ("assignments", "description", "TEXT"),
]

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== EduBeacon DB Migration (migrate_db2.py) ===\n")

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print(f"Connected to database '{DB_CONFIG['database']}' on {DB_CONFIG['host']}.\n")

    # 1. Create new tables
    print("--- Creating new tables ---")
    for tname, ddl in NEW_TABLES.items():
        existed = table_exists(cursor, tname)
        run(cursor, ddl, f"CREATE TABLE IF NOT EXISTS `{tname}`")
        if existed:
            print(f"       (table already existed — no changes made)")
    print()

    # 2. Add missing columns
    print("--- Adding missing columns ---")
    for table, col, defn in NEW_COLUMNS:
        if column_exists(cursor, table, col):
            print(f"  [SKIP] `{table}`.`{col}` already exists")
        else:
            run(cursor, f"ALTER TABLE `{table}` ADD COLUMN `{col}` {defn}", f"ALTER `{table}` ADD `{col}`")
    print()

    conn.commit()
    cursor.close()
    conn.close()

    print("=== Migration complete — all changes committed. ===")


if __name__ == "__main__":
    main()
