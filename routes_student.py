"""
routes_student.py — Flask Blueprint: student_bp
Covers EduBeacon features 15–20:
  - Student progress chart data
  - Student activity log (view + write)
  - Study suggestions
  - Feedback form
"""
from datetime import date, datetime
from flask import (
    Blueprint, jsonify, render_template, request,
    session, redirect, url_for, flash
)
from db import get_db_connection

student_bp = Blueprint("student_bp", __name__)


# ─────────────────────────── helpers ──────────────────────────────

def _require_student():
    """Return (student_id, department, semester) or None if not authorised."""
    role = session.get("role")
    if role == "student":
        uid = session.get("student_id")
    elif role == "cr":
        uid = session.get("cr_id")
    else:
        return None
    return (
        uid,
        session.get("department"),
        session.get("semester"),
    )


# ─────────────── 1. GET /student/progress ─────────────────────────

@student_bp.route("/student/progress", methods=["GET"])
def student_progress():
    """
    Return JSON {completed, pending, overdue} for the logged-in student.

    completed = acknowledged assignments (via acknowledgements table)
    pending   = not acknowledged, due_date >= today
    overdue   = not acknowledged, due_date < today
    Filtered by student's department.
    """
    creds = _require_student()
    if not creds:
        return jsonify(error="Unauthorised"), 403

    student_id, department, _ = creds
    today = date.today()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Acknowledged assignments for this student
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM assignments a
            JOIN acknowledgements ack ON ack.announcement_id = a.id
            WHERE ack.student_id = %s AND a.department = %s
            """,
            (student_id, department),
        )
        completed = cursor.fetchone()["cnt"]

        # Pending (not acked, due today or later)
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM assignments a
            WHERE a.department = %s
              AND a.due_date >= %s
              AND a.id NOT IN (
                  SELECT announcement_id FROM acknowledgements WHERE student_id = %s
              )
            """,
            (department, today, student_id),
        )
        pending = cursor.fetchone()["cnt"]

        # Overdue (not acked, due before today)
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM assignments a
            WHERE a.department = %s
              AND a.due_date < %s
              AND a.id NOT IN (
                  SELECT announcement_id FROM acknowledgements WHERE student_id = %s
              )
            """,
            (department, today, student_id),
        )
        overdue = cursor.fetchone()["cnt"]

    finally:
        cursor.close()
        conn.close()

    return jsonify(completed=completed, pending=pending, overdue=overdue)


# ─────────────── 2. GET /student/activity ─────────────────────────

@student_bp.route("/student/activity", methods=["GET"])
def student_activity():
    """Render activity feed for the logged-in student (latest 50 rows)."""
    creds = _require_student()
    if not creds:
        return redirect(url_for("login"))

    student_id, _, _ = creds
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT action, detail, created_at
            FROM student_activity
            WHERE student_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (student_id,),
        )
        activities = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template("student_activity.html", activities=activities)


# ─────────────── 3. POST /student/log-activity ────────────────────

@student_bp.route("/student/log-activity", methods=["POST"])
def log_student_activity():
    """
    Insert a row into student_activity.
    Expects JSON body: {action: str, detail: str}
    Returns 201 on success.
    """
    creds = _require_student()
    if not creds:
        return jsonify(error="Unauthorised"), 403

    student_id, _, _ = creds
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    detail = data.get("detail", "")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO student_activity (student_id, action, detail) VALUES (%s, %s, %s)",
            (student_id, action, detail),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return jsonify(status="ok"), 201


# ─────────────── 4. GET /student/study-suggestions ───────────────

@student_bp.route("/student/study-suggestions", methods=["GET"])
def study_suggestions():
    """
    Return a JSON list of personalised study suggestions:
    - Assignments due in <= 7 days  → "Study <subject> — due in X days"
    - Exams in <= 14 days           → "Revise for <subject> exam — X days left"
    Filtered by student's dept and semester.
    """
    creds = _require_student()
    if not creds:
        return jsonify(error="Unauthorised"), 403

    _, department, semester = creds
    today = date.today()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    suggestions = []

    try:
        # Assignments due within 7 days
        cursor.execute(
            """
            SELECT subject, due_date,
                   DATEDIFF(due_date, %s) AS days_left
            FROM assignments
            WHERE department = %s
              AND due_date BETWEEN %s AND DATE_ADD(%s, INTERVAL 7 DAY)
            ORDER BY due_date
            """,
            (today, department, today, today),
        )
        for row in cursor.fetchall():
            days = int(row["days_left"])
            label = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            suggestions.append(
                {
                    "type": "assignment",
                    "text": f"Study {row['subject']} — due {label}",
                    "days_left": days,
                }
            )

        # Exams within 14 days
        cursor.execute(
            """
            SELECT subject, exam_date,
                   DATEDIFF(exam_date, %s) AS days_left
            FROM examinations
            WHERE department = %s
              AND exam_date BETWEEN %s AND DATE_ADD(%s, INTERVAL 14 DAY)
            ORDER BY exam_date
            """,
            (today, department, today, today),
        )
        for row in cursor.fetchall():
            days = int(row["days_left"])
            label = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} left"
            suggestions.append(
                {
                    "type": "exam",
                    "text": f"Revise for {row['subject']} exam — {label}",
                    "days_left": days,
                }
            )

    finally:
        cursor.close()
        conn.close()

    # Sort by urgency
    suggestions.sort(key=lambda s: s["days_left"])
    return jsonify(suggestions=suggestions)


# ─────────────── 5 & 6. GET/POST /feedback ────────────────────────

@student_bp.route("/feedback", methods=["GET"])
def feedback_form():
    """Render the feedback submission form."""
    if not session.get("student_id") and not session.get("cr_id"):
        return redirect(url_for("home"))
    return render_template("feedback.html")


@student_bp.route("/feedback", methods=["POST"])
def feedback_submit():
    """
    Insert feedback into the feedback table.
    Form fields: subject, message
    """
    role = session.get("role")
    if role == "student":
        user_id = session.get("student_id")
    elif role == "cr":
        user_id = session.get("cr_id")
    elif role == "faculty":
        user_id = session.get("faculty_id")
    else:
        return redirect(url_for("home"))
    user_type = session.get("role", "student")
    subject   = request.form.get("subject", "").strip()
    message   = request.form.get("message", "").strip()

    if not message:
        flash("Feedback message cannot be empty.", "danger")
        return redirect(url_for("student_bp.feedback_form"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO feedback (user_id, user_type, subject, message)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, user_type, subject, message),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    flash("Thank you! Your feedback has been submitted successfully.", "success")
    return redirect(url_for("student_bp.feedback_form"))
