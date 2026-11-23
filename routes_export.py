"""
routes_export.py — Flask Blueprint: export_bp
Covers: CSV export (assignments, attendance), PDF/text report.
"""
import csv, io, os
from datetime import date
from flask import (
    Blueprint, session, redirect, url_for,
    make_response, render_template
)
from db import get_db_connection

export_bp = Blueprint("export_bp", __name__)


def _get_role(): return session.get("role")
def _get_uid():
    r = _get_role()
    if r == "student": return session.get("student_id")
    if r == "faculty": return session.get("faculty_id")
    if r == "cr":      return session.get("cr_id")
    return None


# ── GET /export/assignments/csv ──────────────────────────────────────
@export_bp.route("/export/assignments/csv")
def export_assignments_csv():
    uid = _get_uid()
    if not uid:
        return redirect(url_for("home"))

    dept = session.get("department", "")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT title, subject, due_date, priority, days_left
            FROM assignments
            WHERE department='All' OR department=%s
            ORDER BY due_date ASC
        """, (dept,))
        rows = cursor.fetchall()
    finally:
        cursor.close(); conn.close()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Title", "Subject", "Due Date", "Priority", "Days Left"])
    for r in rows:
        w.writerow([r["title"], r["subject"], str(r["due_date"]), r["priority"], r["days_left"]])

    resp = make_response(out.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=assignments.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


# ── GET /export/attendance/csv ───────────────────────────────────────
@export_bp.route("/export/attendance/csv")
def export_attendance_csv():
    role = _get_role()
    uid  = _get_uid()
    if not uid or role not in ("student", "cr"):
        return redirect(url_for("home"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT subject, att_date, status
            FROM attendance WHERE student_id=%s
            ORDER BY att_date DESC
        """, (uid,))
        rows = cursor.fetchall()
    finally:
        cursor.close(); conn.close()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Subject", "Date", "Status"])
    for r in rows:
        w.writerow([r["subject"], str(r["att_date"]), r["status"]])

    resp = make_response(out.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=attendance.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


# ── GET /export/report/pdf ───────────────────────────────────────────
@export_bp.route("/export/report/pdf")
def export_report_pdf():
    role = _get_role()
    uid  = _get_uid()
    if not uid:
        return redirect(url_for("home"))

    dept = session.get("department", "")
    sem  = session.get("semester", "")
    name = session.get("username", "")
    today = date.today()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT title, subject, due_date, priority FROM assignments
            WHERE department='All' OR department=%s ORDER BY due_date
        """, (dept,))
        assignments = cursor.fetchall()

        cursor.execute("""
            SELECT subject, exam_date, exam_time FROM examinations
            WHERE department='All' OR department=%s ORDER BY exam_date
        """, (dept,))
        exams = cursor.fetchall()

        att_summary = []
        if role in ("student", "cr"):
            cursor.execute("""
                SELECT subject,
                       SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present_count,
                       COUNT(*) AS total_count
                FROM attendance WHERE student_id=%s GROUP BY subject
            """, (uid,))
            for r in cursor.fetchall():
                pct = round(r["present_count"]/r["total_count"]*100,1) if r["total_count"] else 0
                att_summary.append(f"{r['subject']}: {r['present_count']}/{r['total_count']} ({pct}%)")
    finally:
        cursor.close(); conn.close()

    # Try reportlab first, fall back to plain text
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"EduBeacon Academic Report", styles["Title"]))
        story.append(Paragraph(f"Student: {name} | Dept: {dept} | Sem: {sem} | Date: {today}", styles["Normal"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Assignments", styles["Heading2"]))
        tdata = [["Title", "Subject", "Due Date", "Priority"]]
        for a in assignments:
            tdata.append([a["title"], a["subject"], str(a["due_date"]), a["priority"]])
        t = Table(tdata, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#5b35d5")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        story.append(Paragraph("Examinations", styles["Heading2"]))
        edata = [["Subject", "Exam Date", "Time"]]
        for e in exams:
            edata.append([e["subject"], str(e["exam_date"]), str(e.get("exam_time",""))])
        et = Table(edata, hAlign="LEFT")
        et.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8a69e8")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(et)

        if att_summary:
            story.append(Spacer(1, 12))
            story.append(Paragraph("Attendance Summary", styles["Heading2"]))
            for line in att_summary:
                story.append(Paragraph(line, styles["Normal"]))

        doc.build(story)
        pdf_data = buf.getvalue()
        resp = make_response(pdf_data)
        resp.headers["Content-Disposition"] = "attachment; filename=edubeacon_report.pdf"
        resp.headers["Content-Type"] = "application/pdf"
        return resp

    except ImportError:
        # Fallback: plain text
        lines = [
            "EDUBEACON ACADEMIC REPORT",
            f"Student: {name} | Dept: {dept} | Sem: {sem} | Date: {today}",
            "=" * 60,
            "",
            "ASSIGNMENTS",
            "-" * 40,
        ]
        for a in assignments:
            lines.append(f"  {a['title']} ({a['subject']}) — Due: {a['due_date']} [{a['priority']}]")
        lines += ["", "EXAMINATIONS", "-" * 40]
        for e in exams:
            lines.append(f"  {e['subject']} — {e['exam_date']} {e.get('exam_time','')}")
        if att_summary:
            lines += ["", "ATTENDANCE SUMMARY", "-" * 40]
            lines += [f"  {l}" for l in att_summary]

        content = "\n".join(lines)
        resp = make_response(content)
        resp.headers["Content-Disposition"] = "attachment; filename=edubeacon_report.txt"
        resp.headers["Content-Type"] = "text/plain"
        return resp

