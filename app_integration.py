"""
app_integration.py — Register all new blueprints into the Flask app.
"""

def register_all_blueprints(app):
    from routes_notifications import notifications_bp
    from routes_academic import academic_bp
    from routes_student import student_bp
    from routes_faculty_extra import faculty_extra_bp
    from routes_attendance import attendance_bp
    from routes_advanced import advanced_bp
    from routes_account import account_bp
    from routes_export import export_bp

    app.register_blueprint(notifications_bp)
    app.register_blueprint(academic_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(faculty_extra_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(advanced_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(export_bp)

