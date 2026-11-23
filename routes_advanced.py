"""
routes_advanced.py — Flask Blueprint: advanced_bp
Covers: Chatbot, NL search, Announcement summariser, Study planner.
"""
import re
from datetime import date, timedelta
from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, jsonify
)
from db import get_db_connection

advanced_bp = Blueprint("advanced_bp", __name__)


def _get_dept():
    return session.get("department", "")

def _logged_in():
    return session.get("role") is not None


# ── Chatbot keyword engine ────────────────────────────────────────────
CHATBOT_RESPONSES = {
    "assignment": "📚 Check your Assignments section on the dashboard for all upcoming deadlines and priorities.",
    "exam": "📝 Your upcoming examinations are listed in the Examinations section with dates and times.",
    "note": "📖 Notes uploaded by faculty are in the Study Notes section. You can download them directly.",
    "attendance": "📊 Check your attendance at /student/attendance. A warning appears if you're below 75%.",
    "announcement": "📢 Announcements are sorted by priority score. Critical ones appear at the top.",
    "deadline": "⏰ Check the Timeline section on your dashboard for all upcoming deadlines in the next 30 days.",
    "schedule": "📅 Visit /daily-schedule to see today's assignments and exams, and upcoming events.",
    "summary": "📋 Visit /weekly-summary for a full summary of this week's academic items.",
    "notification": "🔔 Click the bell icon to see your notifications. Visit /notifications for the full history.",
    "password": "🔑 You can change your password at /change-password.",
    "help": "🤖 I can help with: assignments, exams, notes, attendance, announcements, deadlines, schedule, notifications, and password. Just ask!",
    "planner": "📅 Visit /study-planner for a smart study plan based on your upcoming deadlines.",
    "feedback": "💬 You can submit feedback or complaints at /feedback.",
    "chatbot": "👋 I'm EduBeacon's AI assistant! Ask me about assignments, exams, notes, or anything academic.",
    "hi": "👋 Hello! I'm your EduBeacon assistant. How can I help you today?",
    "hello": "👋 Hi there! Ask me anything about your academics.",
    "thanks": "😊 You're welcome! Is there anything else I can help you with?",
}

def _get_chatbot_reply(message: str) -> str:
    msg_lower = message.lower()
    for keyword, reply in CHATBOT_RESPONSES.items():
        if keyword in msg_lower:
            return reply
    # Contextual fallbacks
    if any(w in msg_lower for w in ["due", "submit", "submit"]):
        return "📅 Check your assignments section for all due dates and submission deadlines."
    if any(w in msg_lower for w in ["mark", "grade", "score"]):
        return "📊 EduBeacon tracks assignment priorities and acknowledgements. Grade management is handled by faculty."
    if any(w in msg_lower for w in ["faculty", "teacher", "professor"]):
        return "👩‍🏫 Faculty post assignments, exams, announcements and study notes on this platform."
    return "🤖 I can help with assignments, exams, notes, attendance, announcements, deadlines, and schedule. What would you like to know?"


# ── GET /chatbot ──────────────────────────────────────────────────────
@advanced_bp.route("/chatbot", methods=["GET"])
def chatbot():
    if not _logged_in():
        return redirect(url_for("home"))
    return render_template("chatbot.html")


# ── POST /api/chat ────────────────────────────────────────────────────
@advanced_bp.route("/api/chat", methods=["POST"])
def api_chat():
    if not _logged_in():
        return jsonify(error="Unauthorized"), 401
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify(reply="Please type a message."), 200
    reply = _get_chatbot_reply(message)
    return jsonify(reply=reply)


# ── GET /api/search?q=... ─────────────────────────────────────────────
@advanced_bp.route("/api/search", methods=["GET"])
def api_search():
    if not _logged_in():
        return jsonify(error="Unauthorized"), 401

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(results=[])

    dept = _get_dept()
    words = [w for w in re.split(r"\s+", q.lower()) if len(w) > 1]
    if not words:
        return jsonify(results=[])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    results = []

    try:
        # Search announcements
        like_clauses = " OR ".join(["(LOWER(title) LIKE %s OR LOWER(message) LIKE %s)"] * len(words))
        params = []
        for w in words:
            params += [f"%{w}%", f"%{w}%"]
        cursor.execute(f"""
            SELECT id, title, message, type, priority_label
            FROM announcements
            WHERE {like_clauses}
            ORDER BY priority_score DESC LIMIT 10
        """, params)
        for r in cursor.fetchall():
            results.append({
                "type": "announcement",
                "title": r["title"],
                "detail": (r["message"] or "")[:100] + "...",
                "url": "/dashboard#announcements",
                "badge": r["priority_label"] or ""
            })

        # Search assignments
        a_clauses = " OR ".join(["(LOWER(title) LIKE %s OR LOWER(subject) LIKE %s)"] * len(words))
        a_params = []
        for w in words:
            a_params += [f"%{w}%", f"%{w}%"]
        cursor.execute(f"""
            SELECT id, title, subject, due_date, priority
            FROM assignments
            WHERE (department='All' OR department=%s) AND ({a_clauses})
            LIMIT 5
        """, [dept] + a_params)
        for r in cursor.fetchall():
            results.append({
                "type": "assignment",
                "title": r["title"],
                "detail": f"Subject: {r['subject']} | Due: {r['due_date']}",
                "url": "/dashboard#assignments",
                "badge": r["priority"] or ""
            })

        # Search notes
        n_clauses = " OR ".join(["(LOWER(title) LIKE %s OR LOWER(subject) LIKE %s)"] * len(words))
        n_params = []
        for w in words:
            n_params += [f"%{w}%", f"%{w}%"]
        cursor.execute(f"""
            SELECT id, title, subject, file_path
            FROM notes
            WHERE (department='All' OR department=%s) AND ({n_clauses})
            LIMIT 5
        """, [dept] + n_params)
        for r in cursor.fetchall():
            results.append({
                "type": "note",
                "title": r["title"],
                "detail": f"Subject: {r['subject']}",
                "url": f"/notes/{r['file_path']}" if r.get("file_path") else "#",
                "badge": "Note"
            })

    finally:
        cursor.close(); conn.close()

    return jsonify(results=results[:20])


# ── GET /api/summarize/<ann_id> ───────────────────────────────────────
@advanced_bp.route("/api/summarize/<int:ann_id>", methods=["GET"])
def api_summarize(ann_id):
    if not _logged_in():
        return jsonify(error="Unauthorized"), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM announcements WHERE id=%s", (ann_id,))
        ann = cursor.fetchone()
    finally:
        cursor.close(); conn.close()

    if not ann:
        return jsonify(error="Announcement not found"), 404

    # Keyword-based summarisation
    message = ann.get("message", "")
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", message) if s.strip()]
    top_sentences = sentences[:3]

    summary_parts = [
        f"Type: {ann.get('type', 'General')}",
        f"Priority: {ann.get('priority_label', 'Low')} (Score: {ann.get('priority_score', 0)}/100)",
        f"Department: {ann.get('target_department', 'All')} | Semester: {ann.get('target_semester', 'All')}",
    ]
    if ann.get("deadline"):
        summary_parts.append(f"Deadline: {ann['deadline']}")
    summary_parts.append("Key points: " + " | ".join(top_sentences) if top_sentences else "")

    return jsonify(summary="\n".join(summary_parts))


# ── GET /study-planner ────────────────────────────────────────────────
@advanced_bp.route("/study-planner", methods=["GET"])
def study_planner():
    if not _logged_in():
        return redirect(url_for("home"))

    dept = _get_dept()
    today = date.today()
    end   = today + timedelta(days=30)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT title, subject, due_date, priority,
                   DATEDIFF(due_date, %s) AS days_left
            FROM assignments
            WHERE (department='All' OR department=%s)
              AND due_date BETWEEN %s AND %s
            ORDER BY due_date ASC
        """, (today, dept, today, end))
        assignments = cursor.fetchall()

        cursor.execute("""
            SELECT subject, exam_date,
                   DATEDIFF(exam_date, %s) AS days_left
            FROM examinations
            WHERE (department='All' OR department=%s)
              AND exam_date BETWEEN %s AND %s
            ORDER BY exam_date ASC
        """, (today, dept, today, end))
        exams = cursor.fetchall()
    finally:
        cursor.close(); conn.close()

    # Build subject plan: suggested study hours
    plans = {}
    for a in assignments:
        subj = a["subject"]
        days = int(a["days_left"]) if a["days_left"] is not None else 30
        hours = max(1, min(4, 10 - days)) if days <= 7 else 1
        if subj not in plans:
            plans[subj] = {"assignments": [], "exams": [], "suggested_hours": 0}
        plans[subj]["assignments"].append(a)
        plans[subj]["suggested_hours"] = max(plans[subj]["suggested_hours"], hours)

    for e in exams:
        subj = e["subject"]
        days = int(e["days_left"]) if e["days_left"] is not None else 30
        hours = max(2, min(6, 15 - days)) if days <= 14 else 2
        if subj not in plans:
            plans[subj] = {"assignments": [], "exams": [], "suggested_hours": 0}
        plans[subj]["exams"].append(e)
        plans[subj]["suggested_hours"] = max(plans[subj]["suggested_hours"], hours)

    return render_template(
        "study_planner.html",
        plans=plans,
        today_str=today.strftime("%A, %d %B %Y")
    )
