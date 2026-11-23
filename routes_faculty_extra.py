"""
routes_faculty_extra.py — Flask Blueprint: faculty_extra_bp
Covers EduBeacon features 21–22:
  - Faculty engagement statistics dashboard
  - Faculty CSV report download
"""
import csv
import io
from flask import (
    Blueprint, render_template, session, redirect,
    url_for, make_response
)
from db import get_db_connection

faculty_extra_bp = Blueprint("faculty_extra_bp", __name__)


# ─────────────────────────── helpers ──────────────────────────────

def _require_faculty():
    """Return (faculty_id, department) or None if not authorised."""
    if session.get("role") != "faculty":
        return None
    return session.get("user_id"), session.get("department")


# ─────────────── 7. GET /faculty/stats ───────────────────────────

@faculty_extra_bp.route("/faculty/stats", methods=["GET"])
def faculty_stats():
    """
    Render faculty_stats.html with:
      - Per-announcement: title, targeted_count, ack_count, ack_percentage
      - Per-subject assignment count
      - Total students in faculty's department
    """
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("login"))

    faculty_id, department = creds
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Total students in dept
        cursor.execute(
            "SELECT COUNT(*) AS total FROM students WHERE department = %s",
            (department,),
        )
        total_students = cursor.fetchone()["total"]

        # Per-announcement stats (target_department filter)
        cursor.execute(
            """
            SELECT
                a.id,
                a.title,
                (SELECT COUNT(*) FROM students s
                 WHERE s.department = a.target_department
                   AND (a.target_semester IS NULL OR a.target_semester = '' OR s.semester = a.target_semester)
                ) AS targeted_count,
                COUNT(ack.id) AS ack_count
            FROM announcements a
            LEFT JOIN acknowledgements ack ON ack.announcement_id = a.id
            WHERE a.target_department = %s
            GROUP BY a.id, a.title, a.target_department, a.target_semester
            ORDER BY a.created_at DESC
            """,
            (department,),
        )
        announcements = cursor.fetchall()

        # Compute ack_percentage safely
        for ann in announcements:
            targeted = ann["targeted_count"] or 0
            acked    = ann["ack_count"] or 0
            ann["ack_percentage"] = (
                round((acked / targeted) * 100, 1) if targeted > 0 else 0.0
            )

        # Per-subject assignment count
        cursor.execute(
            """
            SELECT subject, COUNT(*) AS assignment_count
            FROM assignments
            WHERE department = %s
            GROUP BY subject
            ORDER BY subject
            """,
            (department,),
        )
        subject_counts = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "faculty_stats.html",
        announcements=announcements,
        subject_counts=subject_counts,
        total_students=total_students,
        department=department,
    )


# ─────────────── 8. GET /faculty/report/download ─────────────────

@faculty_extra_bp.route("/faculty/report/download", methods=["GET"])
def faculty_report_download():
    """
    Generate and stream a CSV report containing:
      - Section 1: All students in faculty's department (name, usn, email, semester)
      - Section 2: All announcements with acknowledgement counts
    Returns as a file attachment.
    """
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("login"))

    _, department = creds
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Students
        cursor.execute(
            """
            SELECT name, usn, email, semester
            FROM students
            WHERE department = %s
            ORDER BY semester, name
            """,
            (department,),
        )
        students = cursor.fetchall()

        # Announcements with ack counts
        cursor.execute(
            """
            SELECT a.title, a.type, a.priority_label, a.deadline,
                   COUNT(ack.id) AS ack_count
            FROM announcements a
            LEFT JOIN acknowledgements ack ON ack.announcement_id = a.id
            WHERE a.target_department = %s
            GROUP BY a.id
            ORDER BY a.created_at DESC
            """,
            (department,),
        )
        announcements = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # --- Student section ---
    writer.writerow(["=== STUDENTS ==="])
    writer.writerow(["Name", "USN", "Email", "Semester"])
    for s in students:
        writer.writerow([s["name"], s["usn"], s["email"], s["semester"]])

    writer.writerow([])  # blank separator

    # --- Announcements section ---
    writer.writerow(["=== ANNOUNCEMENTS ==="])
    writer.writerow(["Title", "Type", "Priority", "Deadline", "Acknowledgements"])
    for ann in announcements:
        writer.writerow([
            ann["title"],
            ann["type"],
            ann["priority_label"],
            ann["deadline"],
            ann["ack_count"],
        ])

    csv_data = output.getvalue()
    output.close()

    response = make_response(csv_data)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="faculty_report_{department}.csv"'
    )
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response
