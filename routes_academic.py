"""
routes_academic.py
==================
Flask Blueprint for EduBeacon Smart Academic Management features (Features 5–7).

Exports:
  - academic_bp : Blueprint (no URL prefix)

Routes:
  GET /daily-schedule   → daily_schedule.html with today's + next-7-day items
  GET /weekly-summary   → weekly_summary.html with this week's summary
  GET /api/countdown    → JSON countdown list for all upcoming deadlines
"""

from flask import Blueprint, jsonify, render_template, session, redirect, url_for
import mysql.connector
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
academic_bp = Blueprint("academic_bp", __name__)


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------
def _get_db():
    """Return a fresh MySQL connection for the edubeacon database."""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="kavya@123",
        database="edubeacon"
    )


# ---------------------------------------------------------------------------
# Auth guard helper
# ---------------------------------------------------------------------------
def _current_user():
    """
    Return (user_id, role, department, semester) from session.
    Returns (None, None, None, None) if no user is logged in.
    Supports 'student' and 'cr' roles.
    """
    role = session.get("role")
    if role == "student":
        uid = session.get("student_id")
        dept = session.get("department", "")
        sem  = session.get("semester", "")
        if uid:
            return int(uid), role, dept, sem
    elif role == "cr":
        uid = session.get("cr_id")
        dept = session.get("department", "")
        sem  = session.get("semester", "")
        if uid:
            return int(uid), role, dept, sem
    return None, None, None, None


# ---------------------------------------------------------------------------
# Deadline label helper
# ---------------------------------------------------------------------------
def _label_days(days_left: int) -> str:
    """
    Return a human-readable urgency label.

    Parameters
    ----------
    days_left : int – signed integer (negative = overdue)

    Returns
    -------
    str – 'overdue', 'today', 'tomorrow', or 'in X days'
    """
    if days_left < 0:
        return "overdue"
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    return f"in {days_left} days"


# ---------------------------------------------------------------------------
# Shared query helpers
# ---------------------------------------------------------------------------
def _fetch_assignments(cur, department, semester, from_date: date, to_date: date):
    """
    Fetch assignments for a department+semester in [from_date, to_date].

    Returns a list of dicts with keys:
        id, title, subject, due_date (date obj), days_left, label, priority
    """
    cur.execute(
        """
        SELECT id, title, subject, due_date, priority
        FROM assignments
        WHERE department = %s
          AND due_date BETWEEN %s AND %s
        ORDER BY due_date ASC
        """,
        (department, from_date.isoformat(), to_date.isoformat()),
    )
    rows = cur.fetchall()
    today = date.today()
    result = []
    for r in rows:
        due = r["due_date"] if isinstance(r["due_date"], date) else r["due_date"]
        days_left = (due - today).days
        result.append({
            "id": r["id"],
            "title": r["title"],
            "subject": r["subject"],
            "due_date": due.isoformat(),
            "days_left": days_left,
            "label": _label_days(days_left),
            "priority": r.get("priority", ""),
        })
    return result


def _fetch_exams(cur, department, from_date: date, to_date: date):
    """
    Fetch examinations for a department in [from_date, to_date].

    Returns a list of dicts with keys:
        id, subject, exam_date (str), exam_time, description, days_left, label
    """
    cur.execute(
        """
        SELECT id, subject, exam_date, exam_time, description
        FROM examinations
        WHERE department = %s
          AND exam_date BETWEEN %s AND %s
        ORDER BY exam_date ASC
        """,
        (department, from_date.isoformat(), to_date.isoformat()),
    )
    rows = cur.fetchall()
    today = date.today()
    result = []
    for r in rows:
        exam_d = r["exam_date"] if isinstance(r["exam_date"], date) else r["exam_date"]
        days_left = (exam_d - today).days
        result.append({
            "id": r["id"],
            "subject": r["subject"],
            "exam_date": exam_d.isoformat(),
            "exam_time": str(r.get("exam_time", "")),
            "description": r.get("description", ""),
            "days_left": days_left,
            "label": _label_days(days_left),
        })
    return result


def _fetch_notes_this_week(cur, department, week_start: date, week_end: date):
    """
    Fetch notes added in the current week for a department.

    Returns list of dicts with keys: id, subject, title, file_path
    """
    cur.execute(
        """
        SELECT id, subject, title, file_path
        FROM notes
        WHERE department = %s
        ORDER BY id DESC
        """,
        (department,),
    )
    # Notes table has no created_at; return all for the department this week
    # (adjust if created_at column is added later)
    rows = cur.fetchall()
    return [
        {"id": r["id"], "subject": r["subject"], "title": r["title"], "file_path": r.get("file_path", "")}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Route 5 – GET /daily-schedule
# ---------------------------------------------------------------------------
@academic_bp.route("/daily-schedule", methods=["GET"])
def daily_schedule():
    """
    Render the daily schedule page (daily_schedule.html).

    Context passed to template:
        today_assignments : list – assignments due today
        today_exams       : list – exams scheduled today
        upcoming_assignments : list – assignments due in next 7 days (excl. today)
        upcoming_exams    : list – exams in next 7 days (excl. today)
        today_str         : str  – formatted today's date
        role              : str  – 'student' or 'cr'

    Redirects to login if not authenticated.
    """
    user_id, role, department, semester = _current_user()
    if user_id is None:
        return redirect(url_for("login"))

    today = date.today()
    week_end = today + timedelta(days=7)

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor(dictionary=True)

        # Today's items
        today_assignments = _fetch_assignments(cur, department, semester, today, today)
        today_exams = _fetch_exams(cur, department, today, today)

        # Upcoming 7-day items (exclude today)
        tomorrow = today + timedelta(days=1)
        upcoming_assignments = _fetch_assignments(cur, department, semester, tomorrow, week_end)
        upcoming_exams = _fetch_exams(cur, department, tomorrow, week_end)

        return render_template(
            "daily_schedule.html",
            today_assignments=today_assignments,
            today_exams=today_exams,
            upcoming_assignments=upcoming_assignments,
            upcoming_exams=upcoming_exams,
            today_str=today.strftime("%A, %d %B %Y"),
            role=role,
            department=department,
            semester=semester,
        )
    except Exception as exc:
        print(f"[daily_schedule] ERROR: {exc}")
        return "An error occurred loading your daily schedule.", 500
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Route 6 – GET /weekly-summary
# ---------------------------------------------------------------------------
@academic_bp.route("/weekly-summary", methods=["GET"])
def weekly_summary():
    """
    Render the weekly summary page (weekly_summary.html).

    'This week' spans from the most recent Monday through Sunday.

    Context passed to template:
        week_assignments : list – assignments due this week
        week_exams       : list – exams this week
        week_notes       : list – notes available for the department
        week_start_str   : str  – e.g. "11 Nov 2026"
        week_end_str     : str  – e.g. "17 Nov 2026"
        role             : str

    Redirects to login if not authenticated.
    """
    user_id, role, department, semester = _current_user()
    if user_id is None:
        return redirect(url_for("login"))

    today = date.today()
    # ISO weekday: Monday=1, Sunday=7
    week_start = today - timedelta(days=today.weekday())          # this Monday
    week_end = week_start + timedelta(days=6)                     # this Sunday

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor(dictionary=True)

        week_assignments = _fetch_assignments(cur, department, semester, week_start, week_end)
        week_exams = _fetch_exams(cur, department, week_start, week_end)
        week_notes = _fetch_notes_this_week(cur, department, week_start, week_end)

        return render_template(
            "weekly_summary.html",
            week_assignments=week_assignments,
            week_exams=week_exams,
            week_notes=week_notes,
            week_start_str=week_start.strftime("%d %b %Y"),
            week_end_str=week_end.strftime("%d %b %Y"),
            role=role,
            department=department,
            semester=semester,
            today_str=today.strftime("%A, %d %B %Y"),
        )
    except Exception as exc:
        print(f"[weekly_summary] ERROR: {exc}")
        return "An error occurred loading your weekly summary.", 500
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Route 7 – GET /api/countdown
# ---------------------------------------------------------------------------
@academic_bp.route("/api/countdown", methods=["GET"])
def api_countdown():
    """
    Return a JSON array of live countdown entries for the current user's
    upcoming (and overdue) assignments and exams.

    Each entry shape:
        {
            "title"     : str,
            "type"      : "assignment" | "exam",
            "due_date"  : "YYYY-MM-DD",
            "days_left" : int,          # negative if overdue
            "hours_left": int,          # hours component (0-23) for today items
            "label"     : str           # 'overdue' | 'today' | 'tomorrow' | 'in X days'
        }

    Items are sorted by due_date ascending.
    Returns 401 if user is not in session.
    """
    user_id, role, department, semester = _current_user()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    today = date.today()
    now = datetime.now()
    # Look back 30 days (overdue) and forward 60 days
    from_date = today - timedelta(days=30)
    to_date = today + timedelta(days=60)

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor(dictionary=True)

        # Assignments
        cur.execute(
            """
            SELECT title, due_date
            FROM assignments
            WHERE department = %s
              AND due_date BETWEEN %s AND %s
            ORDER BY due_date ASC
            """,
            (department, from_date.isoformat(), to_date.isoformat()),
        )
        assignment_rows = cur.fetchall()

        # Exams
        cur.execute(
            """
            SELECT subject AS title, exam_date AS due_date, exam_time
            FROM examinations
            WHERE department = %s
              AND exam_date BETWEEN %s AND %s
            ORDER BY exam_date ASC
            """,
            (department, from_date.isoformat(), to_date.isoformat()),
        )
        exam_rows = cur.fetchall()

        countdown = []

        for row in assignment_rows:
            due = row["due_date"] if isinstance(row["due_date"], date) else row["due_date"]
            days_left = (due - today).days
            # For today, calculate remaining hours
            hours_left = 0
            if days_left == 0:
                end_of_day = datetime.combine(today, datetime.max.time())
                hours_left = max(0, int((end_of_day - now).seconds // 3600))
            countdown.append({
                "title": row["title"],
                "type": "assignment",
                "due_date": due.isoformat(),
                "days_left": days_left,
                "hours_left": hours_left,
                "label": _label_days(days_left),
            })

        for row in exam_rows:
            due = row["due_date"] if isinstance(row["due_date"], date) else row["due_date"]
            days_left = (due - today).days
            hours_left = 0
            if days_left == 0:
                # Use exam_time if available for more precise hours
                exam_time = row.get("exam_time")
                if exam_time:
                    # exam_time is a timedelta from MySQL TIME column
                    total_seconds = int(exam_time.total_seconds()) if hasattr(exam_time, "total_seconds") else 0
                    exam_dt = datetime.combine(today, datetime.min.time()) + timedelta(seconds=total_seconds)
                    hours_left = max(0, int((exam_dt - now).total_seconds() // 3600))
                else:
                    end_of_day = datetime.combine(today, datetime.max.time())
                    hours_left = max(0, int((end_of_day - now).seconds // 3600))
            countdown.append({
                "title": row["title"],
                "type": "exam",
                "due_date": due.isoformat(),
                "days_left": days_left,
                "hours_left": hours_left,
                "label": _label_days(days_left),
            })

        # Sort by due_date, then overdue items first within same date
        countdown.sort(key=lambda x: x["due_date"])

        return jsonify(countdown), 200

    except Exception as exc:
        print(f"[api_countdown] ERROR: {exc}")
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()
