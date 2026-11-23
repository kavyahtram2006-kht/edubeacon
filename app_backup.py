from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    jsonify
)

from datetime import datetime, date
import mysql.connector
import os
from werkzeug.utils import secure_filename
import uuid


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = "edubeacon_secret_key"


# =========================================================
# MYSQL DATABASE CONNECTION
# =========================================================

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="kavya@123",
        database="edubeacon"
    )


# =========================================================
# NOTES UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "uploads",
    "notes"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png"
}


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================================================
# SMART PRIORITY SCORE ENGINE
# =========================================================

ANNOUNCEMENT_TYPE_SCORES = {
    "Exam":         40,
    "Assignment":   30,
    "Fee":          35,
    "Placement":    25,
    "Workshop":     15,
    "Event":        10,
    "Circular":     20,
    "General":       5,
}

PRIORITY_REASONS = {
    "Exam":       "Exam-related announcement",
    "Assignment": "Assignment deadline notice",
    "Fee":        "Fee-related notice",
    "Placement":  "Placement opportunity",
    "Workshop":   "Workshop / seminar notice",
    "Event":      "College event notice",
    "Circular":   "Official circular",
    "General":    "General information",
}


def calculate_smart_priority(ann_type, deadline_date=None):
    """
    Returns (priority_score, priority_label, priority_reason)
    Score 0-100. Breakdown:
      - Type base score (max 40)
      - Deadline urgency (max 50)
      - Remainder general weight (10)
    """
    type_score = ANNOUNCEMENT_TYPE_SCORES.get(ann_type, 5)
    deadline_score = 0
    deadline_reason = ""

    if deadline_date:
        if isinstance(deadline_date, str):
            try:
                deadline_date = datetime.strptime(deadline_date, "%Y-%m-%d").date()
            except Exception:
                deadline_date = None

    if deadline_date:
        days_left = (deadline_date - date.today()).days
        if days_left < 0:
            deadline_score = 0
            deadline_reason = "Deadline has passed"
        elif days_left == 0:
            deadline_score = 50
            deadline_reason = "Deadline is today"
        elif days_left == 1:
            deadline_score = 45
            deadline_reason = "Deadline is tomorrow"
        elif days_left <= 3:
            deadline_score = 35
            deadline_reason = f"Deadline in {days_left} days"
        elif days_left <= 7:
            deadline_score = 20
            deadline_reason = f"Deadline in {days_left} days"
        elif days_left <= 14:
            deadline_score = 10
            deadline_reason = f"Deadline in {days_left} days"
        else:
            deadline_score = 5
            deadline_reason = f"Deadline in {days_left} days"

    base_reason = PRIORITY_REASONS.get(ann_type, "General information")
    score = min(100, type_score + deadline_score + 10)

    reasons = [base_reason]
    if deadline_reason:
        reasons.append(deadline_reason)

    if score >= 80:
        label = "Critical"
    elif score >= 60:
        label = "High"
    elif score >= 40:
        label = "Medium"
    else:
        label = "Low"

    return score, label, ". ".join(reasons)


# =========================================================
# ASSIGNMENT PRIORITY (deadline-based)
# =========================================================

def calculate_priority(due_date):
    days_left = (due_date - date.today()).days

    if days_left <= 1:
        priority = "High"
    elif days_left <= 3:
        priority = "Medium"
    else:
        priority = "Low"

    return priority, days_left


# =========================================================
# UPDATE ALL ASSIGNMENT PRIORITIES
# =========================================================

def update_assignment_priorities():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, due_date FROM assignments")
        assignments = cursor.fetchall()

        for assignment in assignments:
            priority, days_left = calculate_priority(assignment["due_date"])
            cursor.execute("""
                UPDATE assignments
                SET priority = %s, days_left = %s
                WHERE id = %s
            """, (priority, days_left, assignment["id"]))

        conn.commit()

    except mysql.connector.Error as e:
        print("Priority update error:", e)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================================================
# TEST MYSQL CONNECTION
# =========================================================

try:
    conn = get_db_connection()
    print("MySQL connected successfully!")
    conn.close()
except Exception as e:
    print("Database connection error:", e)


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("home.html")


# =========================================================
# SET DEPARTMENT (from home page selector)
# =========================================================

@app.route("/set-department", methods=["POST"])
def set_department():
    dept = request.form.get("department", "").strip()
    if dept:
        session["selected_dept"] = dept
    return ("", 204)


# =========================================================
# STUDENT REGISTRATION
# =========================================================

@app.route("/student-register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        usn = request.form.get("usn")
        department = request.form.get("department")
        semester = request.form.get("semester")
        password = request.form.get("password")

        if not all([name, email, usn, department, semester, password]):
            return """
            <h2>Registration Failed</h2>
            <p>Please fill all fields.</p>
            <a href="/student-register">Go Back</a>
            """

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO students (name, email, usn, department, semester, password)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, usn, department, semester, password))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Student Registration Successful!</h2>
            <p>Your account has been created.</p>
            <a href="/student-login">Go to Student Login</a>
            """

        except mysql.connector.Error as e:
            return f"""
            <h2>Registration Error</h2>
            <p>{e}</p>
            <a href="/student-register">Go Back</a>
            """

    return render_template("student_register.html")


# =========================================================
# STUDENT LOGIN
# =========================================================

@app.route("/student-login", methods=["GET", "POST"])
def student_login():
    # Store dept from URL param if present (passed from home page)
    dept_param = request.args.get("dept", "").strip()
    if dept_param:
        session["selected_dept"] = dept_param

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM students
                WHERE name = %s AND password = %s
            """, (username, password))
            student = cursor.fetchone()
            cursor.close()
            conn.close()

            if student:
                session.clear()
                session["username"] = student["name"]
                session["student_id"] = student["id"]
                session["role"] = "student"
                session["department"] = student.get("department", "")
                session["semester"] = student.get("semester", "")
                return redirect(url_for("dashboard"))

            return """
            <h2>Login Failed</h2>
            <p>Invalid username or password.</p>
            <a href="/student-login">Try Again</a>
            """

        except mysql.connector.Error as e:
            return f"""
            <h2>Database Error</h2>
            <p>{e}</p>
            <a href="/student-login">Go Back</a>
            """

    return render_template("student_login.html")


# =========================================================
# FACULTY REGISTRATION
# =========================================================

@app.route("/faculty-register", methods=["GET", "POST"])
def faculty_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        department = request.form.get("department")
        password = request.form.get("password")

        if not all([name, email, department, password]):
            return """
            <h2>Registration Failed</h2>
            <p>Please fill all fields.</p>
            <a href="/faculty-register">Go Back</a>
            """

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO faculty (name, email, department, password)
                VALUES (%s, %s, %s, %s)
            """, (name, email, department, password))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Faculty Registration Successful!</h2>
            <p>Your account has been created.</p>
            <a href="/faculty-login">Go to Faculty Login</a>
            """

        except mysql.connector.Error as e:
            return f"""
            <h2>Faculty Registration Error</h2>
            <p>{e}</p>
            <a href="/faculty-register">Go Back</a>
            """

    return render_template("faculty_register.html")


# =========================================================
# FACULTY LOGIN
# =========================================================

@app.route("/faculty-login", methods=["GET", "POST"])
def faculty_login():
    dept_param = request.args.get("dept", "").strip()
    if dept_param:
        session["selected_dept"] = dept_param

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM faculty
                WHERE email = %s AND password = %s
            """, (email, password))
            faculty = cursor.fetchone()
            cursor.close()
            conn.close()

            if faculty:
                session.clear()
                session["username"] = faculty["name"]
                session["faculty_id"] = faculty["id"]
                session["role"] = "faculty"
                return redirect(url_for("faculty_dashboard"))

            return """
            <h2>Login Failed</h2>
            <p>Invalid email or password.</p>
            <a href="/faculty-login">Try Again</a>
            """

        except mysql.connector.Error as e:
            return f"""
            <h2>Database Error</h2>
            <p>{e}</p>
            <a href="/faculty-login">Go Back</a>
            """

    return render_template("faculty_login.html")


# =========================================================
# FACULTY DASHBOARD  (with analytics)
# =========================================================

@app.route("/faculty-dashboard")
def faculty_dashboard():
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Total students
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]

        # All announcements with acknowledgement counts
        cursor.execute("""
            SELECT a.*,
                   COUNT(DISTINCT ack.student_id) AS ack_count
            FROM announcements a
            LEFT JOIN acknowledgements ack ON ack.announcement_id = a.id
            GROUP BY a.id
            ORDER BY a.priority_score DESC, a.created_at DESC
        """)
        announcements = cursor.fetchall()

        # Assignment count
        cursor.execute("SELECT COUNT(*) AS total FROM assignments")
        assignment_count = cursor.fetchone()["total"]

        # Exam count
        cursor.execute("SELECT COUNT(*) AS total FROM examinations")
        exam_count = cursor.fetchone()["total"]

        cursor.close()
        conn.close()

        return render_template(
            "faculty_dashboard.html",
            username=session.get("username"),
            announcements=announcements,
            total_students=total_students,
            assignment_count=assignment_count,
            exam_count=exam_count
        )

    except mysql.connector.Error as e:
        return f"<h2>Database Error</h2><p>{e}</p>"


# =========================================================
# FACULTY - ADD ASSIGNMENT
# =========================================================

@app.route("/faculty/add-assignment", methods=["GET", "POST"])
def faculty_add_assignment():
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    if request.method == "POST":
        title = request.form.get("title")
        subject = request.form.get("subject")
        due_date = request.form.get("due_date")

        if not title or not subject or not due_date:
            return """
            <h2>Assignment Error</h2>
            <p>Please fill all required fields.</p>
            <a href="/faculty/add-assignment">Go Back</a>
            """

        try:
            deadline = datetime.strptime(due_date, "%Y-%m-%d").date()
            priority, days_left = calculate_priority(deadline)
            faculty_dept = session.get("department", "All")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO assignments (title, subject, due_date, priority, days_left, department)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title, subject, deadline, priority, days_left, faculty_dept))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Assignment Added Successfully!</h2>
            <p>Priority auto-calculated based on deadline.</p>
            <a href="/faculty-dashboard">Back to Faculty Dashboard</a>
            """

        except ValueError:
            return """
            <h2>Invalid Date</h2>
            <a href="/faculty/add-assignment">Go Back</a>
            """
        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("faculty_add_assignment.html")


# =========================================================
# FACULTY - ADD EXAMINATION
# =========================================================

@app.route("/faculty/add-examination", methods=["GET", "POST"])
def faculty_add_examination():
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    if request.method == "POST":
        subject = request.form.get("subject")
        exam_date = request.form.get("exam_date")
        exam_time = request.form.get("exam_time")
        description = request.form.get("description")

        if not subject or not exam_date:
            return """
            <h2>Examination Error</h2>
            <p>Subject and examination date are required.</p>
            <a href="/faculty/add-examination">Go Back</a>
            """

        try:
            faculty_dept = session.get("department", "All")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO examinations (subject, exam_date, exam_time, description, department)
                VALUES (%s, %s, %s, %s, %s)
            """, (subject, exam_date, exam_time, description, faculty_dept))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Examination Added Successfully!</h2>
            <a href="/faculty-dashboard">Back to Faculty Dashboard</a>
            """

        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("faculty_add_examination.html")


# =========================================================
# FACULTY - ADD ANNOUNCEMENT  (with smart priority)
# =========================================================

@app.route("/faculty/add-announcement", methods=["GET", "POST"])
def faculty_add_announcement():
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    if request.method == "POST":
        title = request.form.get("title")
        message = request.form.get("message")
        ann_type = request.form.get("type", "General")
        # Department field (renamed from target_department)
        faculty_dept = session.get("department", "All")
        target_dept = request.form.get("department", faculty_dept) or faculty_dept
        # Semester multi-select: join selected values with comma; default "All"
        selected_sems = request.form.getlist("semester")
        target_sem = ",".join(selected_sems) if selected_sems else "All"
        deadline_str = request.form.get("deadline", "").strip()

        if not title or not message:
            return """
            <h2>Announcement Error</h2>
            <p>Title and message are required.</p>
            <a href="/faculty/add-announcement">Go Back</a>
            """

        deadline_val = None
        if deadline_str:
            try:
                deadline_val = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        priority_score, priority_label, priority_reason = calculate_smart_priority(
            ann_type, deadline_val
        )

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO announcements
                (title, message, type, priority_score, priority_label,
                 priority_reason, target_department, target_semester, deadline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                title, message, ann_type, priority_score, priority_label,
                priority_reason, target_dept, target_sem,
                deadline_val
            ))
            conn.commit()
            cursor.close()
            conn.close()

            return f"""
            <h2>✅ Announcement Added!</h2>
            <p>Smart Priority Score: <strong>{priority_score}/100 — {priority_label}</strong></p>
            <p>Reason: {priority_reason}</p>
            <a href="/faculty-dashboard">Back to Faculty Dashboard</a>
            """

        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("faculty_add_announcement.html")


# =========================================================
# FACULTY - ADD NOTES
# =========================================================

@app.route("/faculty/add-note", methods=["GET", "POST"])
def faculty_add_note():
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    if request.method == "POST":
        subject = request.form.get("subject")
        title = request.form.get("title")
        content = request.form.get("content")
        uploaded_file = request.files.get("note_file")

        if not subject or not title:
            return """
            <h2>Notes Error</h2>
            <p>Subject and note title are required.</p>
            <a href="/faculty/add-note">Go Back</a>
            """

        if not uploaded_file or uploaded_file.filename == "":
            return """
            <h2>Notes Error</h2>
            <p>Please select a file.</p>
            <a href="/faculty/add-note">Go Back</a>
            """

        if not allowed_file(uploaded_file.filename):
            return """
            <h2>Invalid File</h2>
            <p>Only PDF, DOC, DOCX, JPG, JPEG and PNG files are allowed.</p>
            <a href="/faculty/add-note">Go Back</a>
            """

        try:
            original_filename = secure_filename(uploaded_file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_name = f"{timestamp}_{original_filename}"
            file_location = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            uploaded_file.save(file_location)

            faculty_dept = session.get("department", "All")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes (subject, title, content, file_path, department)
                VALUES (%s, %s, %s, %s, %s)
            """, (subject, title, content, unique_name, faculty_dept))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Notes Uploaded Successfully!</h2>
            <a href="/faculty-dashboard">Back to Faculty Dashboard</a>
            """

        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("faculty_add_note.html")


# =========================================================
# STUDENT DASHBOARD  (personalized, priority-driven)
# =========================================================

@app.route("/dashboard")
def dashboard():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    username = session.get("username")
    student_id = session.get("student_id")
    student_dept = session.get("department", "")
    student_sem = session.get("semester", "")

    try:
        update_assignment_priorities()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Assignments filtered by department
        cursor.execute("""
            SELECT * FROM assignments
            WHERE department = 'All' OR department = %s
            ORDER BY due_date ASC
        """, (student_dept,))
        assignments = cursor.fetchall()

        # Examinations filtered by department
        cursor.execute("""
            SELECT * FROM examinations
            WHERE department = 'All' OR department = %s
            ORDER BY exam_date ASC
        """, (student_dept,))
        examinations = cursor.fetchall()

        # Announcements — personalized: "All" dept/sem OR matching student's
        # target_semester may be comma-separated (e.g. "1,2,3"), so use FIND_IN_SET
        cursor.execute("""
            SELECT a.*,
                   CASE WHEN ack.student_id IS NOT NULL THEN 1 ELSE 0 END AS acknowledged
            FROM announcements a
            LEFT JOIN acknowledgements ack
                ON ack.announcement_id = a.id AND ack.student_id = %s
            WHERE (a.target_department = 'All' OR a.target_department = %s)
              AND (a.target_semester = 'All'
                   OR FIND_IN_SET(%s, a.target_semester) > 0)
            ORDER BY a.priority_score DESC, a.created_at DESC
        """, (student_id, student_dept, student_sem))
        announcements = cursor.fetchall()

        # Notes filtered by department
        cursor.execute("""
            SELECT * FROM notes
            WHERE department = 'All' OR department = %s
            ORDER BY id DESC
        """, (student_dept,))
        notes = cursor.fetchall()

        cursor.close()
        conn.close()

        # Priority breakdown for bell
        critical_count = sum(1 for a in announcements if a.get("priority_label") == "Critical")
        high_count = sum(1 for a in announcements if a.get("priority_label") == "High")
        medium_count = sum(1 for a in announcements if a.get("priority_label") == "Medium")
        low_count = sum(1 for a in announcements if a.get("priority_label") == "Low")

        # "Don't Miss" = Critical + High, unacknowledged
        dont_miss = [
            a for a in announcements
            if a.get("priority_label") in ("Critical", "High")
            and not a.get("acknowledged")
        ]

        # Upcoming timeline items (assignments + exams in next 30 days)
        today = date.today()
        timeline = []
        for asgn in assignments:
            due = asgn["due_date"]
            if isinstance(due, str):
                due = datetime.strptime(due, "%Y-%m-%d").date()
            days_left = (due - today).days
            if 0 <= days_left <= 30:
                timeline.append({
                    "date": due,
                    "label": asgn["title"],
                    "type": "assignment",
                    "days_left": days_left,
                    "priority": asgn.get("priority", "Low")
                })
        for exam in examinations:
            edate = exam["exam_date"]
            if isinstance(edate, str):
                edate = datetime.strptime(edate, "%Y-%m-%d").date()
            days_left = (edate - today).days
            if 0 <= days_left <= 30:
                timeline.append({
                    "date": edate,
                    "label": exam["subject"],
                    "type": "exam",
                    "days_left": days_left,
                    "priority": "High"
                })
        timeline.sort(key=lambda x: x["date"])

        # Total viewed (acknowledged)
        total_viewed = sum(1 for a in announcements if a.get("acknowledged"))

        return render_template(
            "dashboard.html",
            username=username,
            assignments=assignments,
            examinations=examinations,
            announcements=announcements,
            notes=notes,
            dont_miss=dont_miss,
            timeline=timeline,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            total_viewed=total_viewed,
            today=today
        )

    except mysql.connector.Error as e:
        return f"<h2>Database Error</h2><p>{e}</p><a href='/'>Go Home</a>"


# =========================================================
# ACKNOWLEDGE ANNOUNCEMENT (AJAX)
# =========================================================

@app.route("/acknowledge/<int:announcement_id>", methods=["POST"])
def acknowledge(announcement_id):
    if session.get("role") not in ("student", "cr"):
        return jsonify({"error": "Not authorized"}), 403

    student_id = session.get("student_id") or session.get("cr_id")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT IGNORE INTO acknowledgements (announcement_id, student_id)
            VALUES (%s, %s)
        """, (announcement_id, student_id))
        conn.commit()

        # Get updated count
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM acknowledgements
            WHERE announcement_id = %s
        """, (announcement_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        return jsonify({"success": True, "count": count})

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# FACULTY ANALYTICS - ANNOUNCEMENT DETAIL
# =========================================================

@app.route("/faculty/analytics/<int:announcement_id>")
def announcement_analytics(announcement_id):
    if session.get("role") != "faculty":
        return redirect(url_for("faculty_login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
        announcement = cursor.fetchone()

        if not announcement:
            return "<h2>Announcement not found</h2>"

        # Count targeted students
        dept = announcement.get("target_department", "All")
        sem = announcement.get("target_semester", "All")

        query = "SELECT COUNT(*) AS cnt FROM students WHERE 1=1"
        params = []
        if dept != "All":
            query += " AND department = %s"
            params.append(dept)
        if sem != "All":
            query += " AND semester = %s"
            params.append(sem)
        cursor.execute(query, params)
        targeted = cursor.fetchone()["cnt"]

        # Acknowledged count
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM acknowledgements
            WHERE announcement_id = %s
        """, (announcement_id,))
        ack_count = cursor.fetchone()["cnt"]

        # Who hasn't acknowledged (if targeted)
        if dept != "All" or sem != "All":
            q2 = """
                SELECT s.name, s.usn FROM students s
                WHERE s.id NOT IN (
                    SELECT student_id FROM acknowledgements WHERE announcement_id = %s
                )
            """
            q2_params = [announcement_id]
            if dept != "All":
                q2 += " AND s.department = %s"
                q2_params.append(dept)
            if sem != "All":
                q2 += " AND s.semester = %s"
                q2_params.append(sem)
            cursor.execute(q2, q2_params)
            not_seen = cursor.fetchall()
        else:
            not_seen = []

        cursor.close()
        conn.close()

        return render_template(
            "faculty_analytics.html",
            announcement=announcement,
            targeted=targeted,
            ack_count=ack_count,
            not_seen=not_seen
        )

    except mysql.connector.Error as e:
        return f"<h2>Database Error</h2><p>{e}</p>"


# =========================================================
# STUDENT ASSIGNMENT PAGE
# =========================================================

@app.route("/assignments")
def student_assignments_disabled():
    if session.get("role") == "student":
        return redirect(url_for("dashboard"))
    return redirect(url_for("student_login"))


# =========================================================
# DOWNLOAD NOTES
# =========================================================

@app.route("/notes/<path:filename>")
def download_note(filename):
    if session.get("role") not in ["student", "faculty", "cr"]:
        return redirect(url_for("home"))

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        os.path.basename(filename),
        as_attachment=True
    )


# =========================================================
# CR REGISTRATION
# =========================================================

@app.route("/cr-register", methods=["GET", "POST"])
def cr_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        usn = request.form.get("usn")
        department = request.form.get("department")
        semester = request.form.get("semester")
        password = request.form.get("password")

        if not all([name, email, usn, department, semester, password]):
            return """
            <h2>Registration Failed</h2>
            <p>Please fill all fields.</p>
            <a href="/cr-register">Go Back</a>
            """

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cr (name, email, usn, department, semester, password)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, usn, department, semester, password))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>CR Registration Successful!</h2>
            <p>Your CR account has been created.</p>
            <a href="/cr-login">Go to CR Login</a>
            """

        except mysql.connector.Error as e:
            return f"""
            <h2>CR Registration Error</h2>
            <p>{e}</p>
            <a href="/cr-register">Go Back</a>
            """

    return render_template("cr_register.html")


# =========================================================
# CR LOGIN
# =========================================================

@app.route("/cr-login", methods=["GET", "POST"])
def cr_login():
    dept_param = request.args.get("dept", "").strip()
    if dept_param:
        session["selected_dept"] = dept_param

    error = None

    if request.method == "POST":
        usn = request.form.get("usn", "").strip()
        password = request.form.get("password", "")

        if not usn or not password:
            error = "Please enter your USN and password."
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                # First check if the USN exists
                cursor.execute("SELECT * FROM cr WHERE usn = %s", (usn,))
                cr_user = cursor.fetchone()
                cursor.close()
                conn.close()

                if cr_user is None:
                    error = "No account found with this USN."
                elif cr_user["password"] != password:
                    error = "Wrong password. Please try again."
                else:
                    session.clear()
                    session["username"] = cr_user["name"]
                    session["cr_id"] = cr_user["id"]
                    session["role"] = "cr"
                    session["department"] = cr_user.get("department", "")
                    session["semester"] = cr_user.get("semester", "")
                    return redirect(url_for("cr_dashboard"))

            except mysql.connector.Error as e:
                error = f"Database error: {e}"

    return render_template("cr_login.html", error=error)


# =========================================================
# CR DASHBOARD
# =========================================================

@app.route("/cr-dashboard")
def cr_dashboard():
    if session.get("role") != "cr":
        return redirect(url_for("cr_login"))

    cr_dept = session.get("department", "")
    cr_sem = session.get("semester", "")
    cr_id = session.get("cr_id")

    try:
        update_assignment_priorities()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM assignments
            WHERE department = 'All' OR department = %s
            ORDER BY due_date ASC
        """, (cr_dept,))
        assignments = cursor.fetchall()

        cursor.execute("""
            SELECT * FROM examinations
            WHERE department = 'All' OR department = %s
            ORDER BY exam_date ASC
        """, (cr_dept,))
        examinations = cursor.fetchall()

        cursor.execute("""
            SELECT a.*,
                   CASE WHEN ack.student_id IS NOT NULL THEN 1 ELSE 0 END AS acknowledged,
                   COUNT(DISTINCT ack2.student_id) AS ack_count
            FROM announcements a
            LEFT JOIN acknowledgements ack
                ON ack.announcement_id = a.id AND ack.student_id = %s
            LEFT JOIN acknowledgements ack2
                ON ack2.announcement_id = a.id
            WHERE (a.target_department = 'All' OR a.target_department = %s)
              AND (a.target_semester = 'All'
                   OR FIND_IN_SET(%s, a.target_semester) > 0)
            GROUP BY a.id, ack.student_id
            ORDER BY a.priority_score DESC, a.created_at DESC
        """, (cr_id, cr_dept, cr_sem))
        announcements = cursor.fetchall()

        cursor.execute("""
            SELECT * FROM notes
            WHERE department = 'All' OR department = %s
            ORDER BY id DESC
        """, (cr_dept,))
        notes = cursor.fetchall()

        cursor.close()
        conn.close()

        critical_count = sum(1 for a in announcements if a.get("priority_label") == "Critical")
        high_count = sum(1 for a in announcements if a.get("priority_label") == "High")
        medium_count = sum(1 for a in announcements if a.get("priority_label") == "Medium")
        low_count = sum(1 for a in announcements if a.get("priority_label") == "Low")

        dont_miss = [
            a for a in announcements
            if a.get("priority_label") in ("Critical", "High")
            and not a.get("acknowledged")
        ]

        today = date.today()
        timeline = []
        for asgn in assignments:
            due = asgn["due_date"]
            if isinstance(due, str):
                due = datetime.strptime(due, "%Y-%m-%d").date()
            days_left = (due - today).days
            if 0 <= days_left <= 30:
                timeline.append({
                    "date": due,
                    "label": asgn["title"],
                    "type": "assignment",
                    "days_left": days_left,
                    "priority": asgn.get("priority", "Low")
                })
        for exam in examinations:
            edate = exam["exam_date"]
            if isinstance(edate, str):
                edate = datetime.strptime(edate, "%Y-%m-%d").date()
            days_left = (edate - today).days
            if 0 <= days_left <= 30:
                timeline.append({
                    "date": edate,
                    "label": exam["subject"],
                    "type": "exam",
                    "days_left": days_left,
                    "priority": "High"
                })
        timeline.sort(key=lambda x: x["date"])

        return render_template(
            "cr_dashboard.html",
            username=session.get("username"),
            assignments=assignments,
            examinations=examinations,
            announcements=announcements,
            notes=notes,
            dont_miss=dont_miss,
            timeline=timeline,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            today=today
        )

    except mysql.connector.Error as e:
        return f"<h2>Database Error</h2><p>{e}</p>"


# =========================================================
# CR ACADEMIC ALERTS
# =========================================================

@app.route("/cr/academic-alerts")
def cr_academic_alerts():
    if session.get("role") != "cr":
        return redirect(url_for("cr_login"))
    return redirect(url_for("cr_dashboard"))


# =========================================================
# CR - ADD ASSIGNMENT
# =========================================================

@app.route("/cr/add-assignment", methods=["GET", "POST"])
def cr_add_assignment():
    if session.get("role") != "cr":
        return redirect(url_for("cr_login"))

    if request.method == "POST":
        title = request.form.get("title")
        subject = request.form.get("subject")
        due_date = request.form.get("due_date")

        if not title or not subject or not due_date:
            return """
            <h2>Assignment Error</h2>
            <p>Please fill all required fields.</p>
            <a href="/cr/add-assignment">Go Back</a>
            """

        try:
            deadline = datetime.strptime(due_date, "%Y-%m-%d").date()
            priority, days_left = calculate_priority(deadline)
            cr_dept = session.get("department", "All")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO assignments (title, subject, due_date, priority, days_left, department)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title, subject, deadline, priority, days_left, cr_dept))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Assignment Added Successfully!</h2>
            <p>Priority auto-calculated based on deadline.</p>
            <a href="/cr-dashboard">Back to CR Dashboard</a>
            """

        except ValueError:
            return """
            <h2>Invalid Date</h2>
            <a href="/cr/add-assignment">Go Back</a>
            """
        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("cr_add_assignment.html")


# =========================================================
# CR - ADD NOTE
# =========================================================

@app.route("/cr/add-note", methods=["GET", "POST"])
def cr_add_note():
    if session.get("role") != "cr":
        return redirect(url_for("cr_login"))

    if request.method == "POST":
        subject = request.form.get("subject")
        title = request.form.get("title")
        content = request.form.get("content")
        uploaded_file = request.files.get("note_file")

        if not subject or not title:
            return """
            <h2>Notes Error</h2>
            <p>Subject and note title are required.</p>
            <a href="/cr/add-note">Go Back</a>
            """

        if not uploaded_file or uploaded_file.filename == "":
            return """
            <h2>Notes Error</h2>
            <p>Please select a file.</p>
            <a href="/cr/add-note">Go Back</a>
            """

        if not allowed_file(uploaded_file.filename):
            return """
            <h2>Invalid File</h2>
            <p>Only PDF, DOC, DOCX, JPG, JPEG and PNG files are allowed.</p>
            <a href="/cr/add-note">Go Back</a>
            """

        try:
            original_filename = secure_filename(uploaded_file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_name = f"{timestamp}_{original_filename}"
            file_location = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            uploaded_file.save(file_location)

            cr_dept = session.get("department", "All")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes (subject, title, content, file_path, department)
                VALUES (%s, %s, %s, %s, %s)
            """, (subject, title, content, unique_name, cr_dept))
            conn.commit()
            cursor.close()
            conn.close()

            return """
            <h2>Notes Uploaded Successfully!</h2>
            <a href="/cr-dashboard">Back to CR Dashboard</a>
            """

        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("cr_add_note.html")


# =========================================================
# CR - ADD ANNOUNCEMENT
# =========================================================

@app.route("/cr/add-announcement", methods=["GET", "POST"])
def cr_add_announcement():
    if session.get("role") != "cr":
        return redirect(url_for("cr_login"))

    if request.method == "POST":
        title = request.form.get("title")
        message = request.form.get("message")
        ann_type = request.form.get("type", "General")
        cr_dept = session.get("department", "All")
        target_dept = request.form.get("department", cr_dept) or cr_dept
        selected_sems = request.form.getlist("semester")
        target_sem = ",".join(selected_sems) if selected_sems else "All"
        deadline_str = request.form.get("deadline", "").strip()

        if not title or not message:
            return """
            <h2>Announcement Error</h2>
            <p>Title and message are required.</p>
            <a href="/cr/add-announcement">Go Back</a>
            """

        deadline_val = None
        if deadline_str:
            try:
                deadline_val = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        priority_score, priority_label, priority_reason = calculate_smart_priority(
            ann_type, deadline_val
        )

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO announcements
                (title, message, type, priority_score, priority_label,
                 priority_reason, target_department, target_semester, deadline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                title, message, ann_type, priority_score, priority_label,
                priority_reason, target_dept, target_sem,
                deadline_val
            ))
            conn.commit()
            cursor.close()
            conn.close()

            return f"""
            <h2>✅ Announcement Added!</h2>
            <p>Smart Priority Score: <strong>{priority_score}/100 — {priority_label}</strong></p>
            <p>Reason: {priority_reason}</p>
            <a href="/cr-dashboard">Back to CR Dashboard</a>
            """

        except mysql.connector.Error as e:
            return f"<h2>Database Error</h2><p>{e}</p>"

    return render_template("cr_add_announcement.html")


# =========================================================
# OLD ROUTES
# =========================================================

@app.route("/login", methods=["POST"])
def login():
    return redirect(url_for("student_login"))


@app.route("/staff-login")
def staff_login():
    return redirect(url_for("faculty_login"))


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# =========================================================
# FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def file_too_large(error):
    return """
    <h2>File Too Large</h2>
    <p>Please upload a file smaller than 10 MB.</p>
    <a href="/faculty/add-note">Go Back</a>
    """, 413


# =========================================================
# RUN FLASK
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)