"""
db.py — Shared database connection helper for EduBeacon blueprints.
"""
import mysql.connector


def get_db_connection():
    """Return a new MySQL connection to the EduBeacon database."""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="kavya@123",
        database="edubeacon"
    )
