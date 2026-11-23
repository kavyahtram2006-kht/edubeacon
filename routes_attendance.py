"""
routes_attendance.py — Flask Blueprint: attendance_bp
Covers EduBeacon Attendance features (34-39).
"""
import csv, io
from datetime import date
from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, make_response, jsonify
)
from db import get_db_connection

attendance_bp = Blueprint("attendance_bp", __name__)


def _require_faculty():
    if session.get("role") != "faculty":
        return None
    return session.get("faculty_id"), session.get("department")


def _require_student():
    role = session.get("role")
    if role not in ("student", "cr"):
        return None
    uid = session.get("student_id") or session.get("cr_id")
    return uid, session.get("department"), session.get("semester")


# ── GET /faculty/attendance ──────────────────────────────────────────
@attendance_bp.route("/faculty/attendance", methods=["GET"])
def faculty_attendance():
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("faculty_login"))
    faculty_id, department = creds

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name, usn FROM students WHERE department=%s ORDER BY name",
            (department,)
        )
        students = cursor.fetchall()
        # Get distinct subjects from assignments for this dept
        cursor.execute(
            "SELECT DISTINCT subject FROM assignments WHERE department=%s ORDER BY subject",
            (department,)
        )
        subjects = [r["subject"] for r in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

    return render_template(
        "faculty_attendance.html",
        students=students,
        subjects=subjects,
        department=department,
        today=date.today().isoformat()
    )


# ── POST /faculty/attendance ─────────────────────────────────────────
@attendance_bp.route("/faculty/attendance", methods=["POST"])
def faculty_attendance_submit():
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("faculty_login"))
    faculty_id, department = creds

    subject = request.form.get("subject", "").strip()
    att_date = request.form.get("att_date", date.today().isoformat())
    semester = request.form.get("semester", "")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get all students in dept
        cursor.execute(
            "SELECT id FROM students WHERE department=%s", (department,)
        )
        student_rows = cursor.fetchall()

        for s in student_rows:
            sid = s["id"]
            status = request.form.get(f"status_{sid}", "absent")
            # Upsert attendance
            cursor.execute("""
                SELECT id FROM attendance
                WHERE student_id=%s AND subject=%s AND att_date=%s
            """, (sid, subject, att_date))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("""
                    UPDATE attendance SET status=%s, faculty_id=%s
                    WHERE student_id=%s AND subject=%s AND att_date=%s
                """, (status, faculty_id, sid, subject, att_date))
            else:
                cursor.execute("""
                    INSERT INTO attendance (student_id, subject, att_date, status, faculty_id, department, semester)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (sid, subject, att_date, status, faculty_id, department, semester))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return render_template("faculty_attendance.html",
                           message="Attendance saved successfully!",
                           students=[], subjects=[], department=department,
                           today=att_date)


# ── GET /faculty/attendance/report ──────────────────────────────────
@attendance_bp.route("/faculty/attendance/report", methods=["GET"])
def faculty_attendance_report():
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("faculty_login"))
    faculty_id, department = creds

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Per-student, per-subject: present/total/percentage
        cursor.execute("""
            SELECT s.name, s.usn, a.subject,
                   SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_count,
                   COUNT(*) AS total_count
            FROM attendance a
            JOIN students s ON s.id = a.student_id
            WHERE a.department = %s
            GROUP BY s.id, s.name, s.usn, a.subject
            ORDER BY s.name, a.subject
        """, (department,))
        rows = cursor.fetchall()
        for r in rows:
            r["percentage"] = round(r["present_count"] / r["total_count"] * 100, 1) if r["total_count"] else 0
            r["low"] = r["percentage"] < 75
    finally:
        cursor.close()
        conn.close()

    return render_template("attendance_report.html", rows=rows, department=department)


# ── GET /faculty/attendance/report/csv ──────────────────────────────
@attendance_bp.route("/faculty/attendance/report/csv", methods=["GET"])
def faculty_attendance_csv():
    creds = _require_faculty()
    if not creds:
        return redirect(url_for("faculty_login"))
    faculty_id, department = creds

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT s.name, s.usn, a.subject,
                   SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_count,
                   COUNT(*) AS total_count
            FROM attendance a
            JOIN students s ON s.id = a.student_id
            WHERE a.department = %s
            GROUP BY s.id, s.name, s.usn, a.subject
            ORDER BY s.name, a.subject
        """, (department,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "USN", "Subject", "Present", "Total", "Percentage"])
    for r in rows:
        pct = round(r["present_count"] / r["total_count"] * 100, 1) if r["total_count"] else 0
        writer.writerow([r["name"], r["usn"], r["subject"], r["present_count"], r["total_count"], f"{pct}%"])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=attendance_report.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


# ── GET /student/attendance ──────────────────────────────────────────
@attendance_bp.route("/student/attendance", methods=["GET"])
def student_attendance():
    creds = _require_student()
    if not creds:
        return redirect(url_for("student_login"))
    student_id, department, semester = creds

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT subject,
                   SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present_count,
                   COUNT(*) AS total_count
            FROM attendance
            WHERE student_id = %s
            GROUP BY subject
            ORDER BY subject
        """, (student_id,))
        rows = cursor.fetchall()
        for r in rows:
            r["percentage"] = round(r["present_count"] / r["total_count"] * 100, 1) if r["total_count"] else 0
            r["low"] = r["percentage"] < 75
    finally:
        cursor.close()
        conn.close()

    return render_template("student_attendance.html", subjects=rows)


# ── GET /student/attendance/download ────────────────────────────────
@attendance_bp.route("/student/attendance/download", methods=["GET"])
def student_attendance_download():
    creds = _require_student()
    if not creds:
        return redirect(url_for("student_login"))
    student_id, department, semester = creds

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT subject, att_date, status
            FROM attendance
            WHERE student_id=%s
            ORDER BY att_date DESC, subject
        """, (student_id,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Subject", "Date", "Status"])
    for r in rows:
        writer.writerow([r["subject"], str(r["att_date"]), r["status"]])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=my_attendance.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

