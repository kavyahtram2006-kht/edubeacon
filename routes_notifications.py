"""
routes_notifications.py
=======================
Flask Blueprint for EduBeacon Notification features (Features 1–4).

Exports:
  - notifications_bp  : Blueprint with prefix '/api'
  - create_notification : helper importable by other route modules

Routes:
  GET  /api/notifications             → JSON list of notifications for session user
  POST /api/notifications/mark-all-read → mark all notifications as read
  POST /api/notifications/<nid>/read  → mark a single notification as read
  GET  /notifications                 → paginated notification history page (20/page)
"""

from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for
import mysql.connector
from datetime import datetime

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
notifications_bp = Blueprint("notifications_bp", __name__)


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
# Public helper – importable by other route modules
# ---------------------------------------------------------------------------
def create_notification(user_id, user_type, notif_type, title, message, link=""):
    """
    Insert a notification row into the `notifications` table.

    Parameters
    ----------
    user_id   : int   – recipient's primary-key id
    user_type : str   – 'student', 'faculty', or 'cr'
    notif_type: str   – short category tag, e.g. 'assignment', 'exam', 'general'
    title     : str   – short headline shown in the bell dropdown
    message   : str   – full notification body
    link      : str   – optional URL the notification should link to

    Returns
    -------
    int – last-insert-id of the new notification row, or None on error
    """
    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notifications
                (user_id, user_type, notif_type, title, message, link, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
            """,
            (user_id, user_type, notif_type, title, message, link),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        print(f"[create_notification] ERROR: {exc}")
        return None
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Auth guard helper
# ---------------------------------------------------------------------------
def _current_user():
    """
    Return (user_id, role) from session, or (None, None) if not logged in.
    Supports student, cr, and faculty session keys.
    """
    for role in ("student", "cr", "faculty"):
        uid = session.get(f"{role}_id")
        if uid:
            return int(uid), role
    return None, None


# ---------------------------------------------------------------------------
# Route 1 – GET /api/notifications
# ---------------------------------------------------------------------------
@notifications_bp.route("/api/notifications", methods=["GET"])
def api_get_notifications():
    """
    Return a JSON array of the current user's notifications, newest first.

    Response shape (each item):
        {
            "id"        : int,
            "title"     : str,
            "message"   : str,
            "notif_type": str,
            "is_read"   : 0 | 1,
            "link"      : str,
            "created_at": "YYYY-MM-DD HH:MM:SS"
        }

    Returns 401 if no user is in session.
    """
    user_id, role = _current_user()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, title, message, notif_type, is_read, link,
                   DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_at
            FROM notifications
            WHERE user_id = %s AND user_type = %s
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (user_id, role),
        )
        rows = cur.fetchall()
        # Coerce is_read to plain int for JSON serialisation
        for row in rows:
            row["is_read"] = int(row["is_read"])
        return jsonify(rows), 200
    except Exception as exc:
        print(f"[api_get_notifications] ERROR: {exc}")
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Route 2 – POST /api/notifications/mark-all-read
# ---------------------------------------------------------------------------
@notifications_bp.route("/api/notifications/mark-all-read", methods=["POST"])
def api_mark_all_read():
    """
    Set is_read = 1 for every unread notification belonging to the session user.

    Returns JSON {"updated": <row-count>} or 401 if not authenticated.
    """
    user_id, role = _current_user()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = %s AND user_type = %s AND is_read = 0
            """,
            (user_id, role),
        )
        conn.commit()
        return jsonify({"updated": cur.rowcount}), 200
    except Exception as exc:
        print(f"[api_mark_all_read] ERROR: {exc}")
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Route 3 – POST /api/notifications/<nid>/read
# ---------------------------------------------------------------------------
@notifications_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
def api_mark_one_read(nid):
    """
    Mark a single notification (by id) as read.

    Only marks the notification if it belongs to the session user so users
    cannot mark each other's notifications.

    Returns JSON {"ok": true} on success, 401/404 otherwise.
    """
    user_id, role = _current_user()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s AND user_id = %s AND user_type = %s
            """,
            (nid, user_id, role),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Notification not found"}), 404
        return jsonify({"ok": True}), 200
    except Exception as exc:
        print(f"[api_mark_one_read] ERROR: {exc}")
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Route 4 – GET /notifications  (HTML page)
# ---------------------------------------------------------------------------
@notifications_bp.route("/notifications", methods=["GET"])
def notifications_page():
    """
    Render the notification history page (notifications.html).

    Paginates at 20 notifications per page; passes `page`, `notifications`,
    `total_pages`, and `unread_count` to the template.

    Redirects to /login if the user is not authenticated.
    """
    user_id, role = _current_user()
    if user_id is None:
        return redirect(url_for("login"))  # adjust endpoint name if needed

    PAGE_SIZE = 20
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PAGE_SIZE

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor(dictionary=True)

        # Total count for pagination
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND user_type=%s",
            (user_id, role),
        )
        total = cur.fetchone()["cnt"]
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        # Page of notifications
        cur.execute(
            """
            SELECT id, title, message, notif_type, is_read, link,
                   DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_at
            FROM notifications
            WHERE user_id = %s AND user_type = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, role, PAGE_SIZE, offset),
        )
        notifs = cur.fetchall()
        for n in notifs:
            n["is_read"] = int(n["is_read"])

        # Unread count for badge
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND user_type=%s AND is_read=0",
            (user_id, role),
        )
        unread_count = cur.fetchone()["cnt"]

        return render_template(
            "notifications.html",
            notifications=notifs,
            page=page,
            total_pages=total_pages,
            unread_count=unread_count,
            role=role,
        )
    except Exception as exc:
        print(f"[notifications_page] ERROR: {exc}")
        return "An error occurred loading notifications.", 500
    finally:
        if conn:
            conn.close()
