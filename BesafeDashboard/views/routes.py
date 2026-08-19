import os
from flask import Blueprint, render_template, send_from_directory, current_app

views_bp = Blueprint("views", __name__)

@views_bp.route("/")
def home():
    return render_template("home.html")

@views_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", mapbox_token=current_app.config.get("MAPBOX_TOKEN", ""))

@views_bp.route("/login")
def login_page():
    return render_template("login.html", mapbox_token=current_app.config.get("MAPBOX_TOKEN", ""))

@views_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    upload_folder = current_app.config.get("UPLOAD_FOLDER") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    return send_from_directory(upload_folder, filename)
