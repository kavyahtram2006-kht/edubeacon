"""
routes_account.py — Flask Blueprint: account_bp
Covers: change password, forgot password, reset password, profile, photo upload.
"""
import os, random, string
from datetime import datetime
from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, jsonify, flash
)
from werkzeug.utils import secure_filename
from db import get_db_connection

account_bp = Blueprint("account_bp", __name__)

PROFILE_UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uploads", "profiles"
)
os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)
ALLOWED_PHOTO = {"jpg", "jpeg", "png", "gif", "webp"}


def _get_role():
    return session.get("role")

def _get_uid():
    role = _get_role()
    if role == "student": return session.get("student_id")
    if role == "faculty": return session.get("faculty_id")
    if role == "cr":      return session.get("cr_id")
    return None

def _table_for_role(role):
    return {"student": "students", "faculty": "faculty", "cr": "cr"}.get(role)


# ── GET /profile ─────────────────────────────────────────────────────
@account_bp.route("/profile", methods=["GET"])
def profile():
    role = _get_role()
    uid  = _get_uid()
    if not uid:
        return redirect(url_for("home"))

    table = _table_for_role(role)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT * FROM {table} WHERE id=%s", (uid,))
        user = cursor.fetchone()
    finally:
        cursor.close(); conn.close()

    return render_template("profile.html", user=user, role=role)


# ── POST /profile/upload-photo ───────────────────────────────────────
@account_bp.route("/profile/upload-photo", methods=["POST"])
def upload_photo():
    role = _get_role()
    uid  = _get_uid()
    if not uid:
        return jsonify(success=False, error="Not logged in"), 401

    f = request.files.get("photo")
    if not f or f.filename == "":
        return jsonify(success=False, error="No file selected"), 400

    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_PHOTO:
        return jsonify(success=False, error="Invalid file type"), 400

    if request.content_length and request.content_length > 2 * 1024 * 1024:
        return jsonify(success=False, error="File too large (max 2MB)"), 400

    fname = f"{role}_{uid}_{secure_filename(f.filename)}"
    f.save(os.path.join(PROFILE_UPLOAD_FOLDER, fname))

    table = _table_for_role(role)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"UPDATE {table} SET profile_photo=%s WHERE id=%s", (fname, uid))
        conn.commit()
    finally:
        cursor.close(); conn.close()

    return jsonify(success=True, filename=fname)


# ── GET /profile/photo/<filename> ───────────────────────────────────
@account_bp.route("/profile/photo/<path:filename>")
def serve_profile_photo(filename):
    from flask import send_from_directory
    return send_from_directory(PROFILE_UPLOAD_FOLDER, os.path.basename(filename))


# ── GET+POST /change-password ────────────────────────────────────────
@account_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    role = _get_role()
    uid  = _get_uid()
    if not uid:
        return redirect(url_for("home"))

    error = None
    success = None

    if request.method == "POST":
        current  = request.form.get("current_password", "")
        new_pass = request.form.get("new_password", "")
        confirm  = request.form.get("confirm_password", "")

        table = _table_for_role(role)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(f"SELECT password FROM {table} WHERE id=%s", (uid,))
            row = cursor.fetchone()
            if not row or row["password"] != current:
                error = "Current password is incorrect."
            elif len(new_pass) < 6:
                error = "New password must be at least 6 characters."
            elif new_pass != confirm:
                error = "Passwords do not match."
            else:
                cursor.execute(f"UPDATE {table} SET password=%s WHERE id=%s", (new_pass, uid))
                conn.commit()
                success = "Password changed successfully!"
        finally:
            cursor.close(); conn.close()

    return render_template("change_password.html", error=error, success=success, role=role)


# ── GET+POST /forgot-password ────────────────────────────────────────
@account_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    token_shown = None
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        usn   = request.form.get("usn", "").strip()

        # Search students then cr
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        found_table = None
        found_id = None
        try:
            for table in ("students", "cr"):
                cursor.execute(
                    f"SELECT id FROM {table} WHERE email=%s AND usn=%s",
                    (email, usn)
                )
                row = cursor.fetchone()
                if row:
                    found_table = table
                    found_id = row["id"]
                    break

            if not found_id:
                # Try faculty by email only
                cursor.execute("SELECT id FROM faculty WHERE email=%s", (email,))
                row = cursor.fetchone()
                if row:
                    found_table = "faculty"
                    found_id = row["id"]

            if found_id:
                token = "".join(random.choices(string.digits, k=6))
                cursor.execute(
                    f"UPDATE {found_table} SET reset_token=%s WHERE id=%s",
                    (token, found_id)
                )
                conn.commit()
                token_shown = token
            else:
                error = "No account found with those details."
        finally:
            cursor.close(); conn.close()

    return render_template("forgot_password.html", token_shown=token_shown, error=error)


# ── GET+POST /reset-password ─────────────────────────────────────────
@account_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    error = None
    success = None
    token = request.args.get("token", "")

    if request.method == "POST":
        token     = request.form.get("token", "").strip()
        new_pass  = request.form.get("new_password", "")
        confirm   = request.form.get("confirm_password", "")

        if new_pass != confirm:
            error = "Passwords do not match."
        elif len(new_pass) < 6:
            error = "Password must be at least 6 characters."
        else:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            found = False
            try:
                for table in ("students", "cr", "faculty"):
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE reset_token=%s",
                        (token,)
                    )
                    row = cursor.fetchone()
                    if row:
                        cursor.execute(
                            f"UPDATE {table} SET password=%s, reset_token=NULL WHERE id=%s",
                            (new_pass, row["id"])
                        )
                        conn.commit()
                        found = True
                        success = "Password reset successfully! You can now log in."
                        break
                if not found:
                    error = "Invalid or expired token."
            finally:
                cursor.close(); conn.close()

    return render_template("reset_password.html", error=error, success=success, token=token)

