import os
import sys
from datetime import timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config
from socket_instance import socketio
from socket_events import register_socket_events

# ── Mobile App Blueprints (Preserved)
from auth.routes import auth_bp
from user.routes import user_bp
from safety.routes import safety_bp
from notifications.routes import notifications_bp
from safechat.routes import safechat_bp

# ── Agency & Dashboard Blueprints (Modularized)
from agency.routes import agency_bp
from alerts.routes import alerts_bp
from views.routes import views_bp

# ── Background Jobs
from jobs.safety_check_job import start_safety_check_job

# ── Global Exceptions
from exceptions import (
    AppException, BadRequestException, NotFoundException,
    UnauthorizedAccessException, ForbiddenAccessException,
    TooManyAttemptsException, ConflictException,
    UnprocessableEntityException, PayloadTooLargeException,
    InternalServerErrorException,
)

sys.dont_write_bytecode = True

# ── App Factory & Setup
app = Flask(__name__)
app.config["SECRET_KEY"]               = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"]           = Config.JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["UPLOAD_FOLDER"]            = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAPBOX_TOKEN"]            = Config.MAPBOX_TOKEN

# ── Extensions
CORS(app, origins="*")
socketio.init_app(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
jwt = JWTManager(app)

# ── Global Error Handlers
@app.errorhandler(AppException)
def handle_app_exception(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), error.status_code

@app.errorhandler(BadRequestException)
def handle_bad_request(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 400

@app.errorhandler(NotFoundException)
def handle_not_found(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 404

@app.errorhandler(UnauthorizedAccessException)
def handle_unauthorized(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 401

@app.errorhandler(ForbiddenAccessException)
def handle_forbidden(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 403

@app.errorhandler(TooManyAttemptsException)
def handle_too_many_attempts(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 429

@app.errorhandler(ConflictException)
def handle_conflict(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 409

@app.errorhandler(UnprocessableEntityException)
def handle_unprocessable_entity(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 422

@app.errorhandler(PayloadTooLargeException)
def handle_payload_too_large(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 413

@app.errorhandler(InternalServerErrorException)
def handle_internal_server_error(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 500

# ── Register Citizen Mobile App Blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(user_bp, url_prefix="/user")
app.register_blueprint(safety_bp, url_prefix="/safety")
app.register_blueprint(notifications_bp, url_prefix="/notifications")
app.register_blueprint(safechat_bp, url_prefix="/safechat")

# ── Register Agency & Dashboard Blueprints
app.register_blueprint(agency_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(views_bp)

# ── Register Socket.IO Events & Background Jobs
register_socket_events(socketio)
start_safety_check_job()

if __name__ == "__main__":
    socketio.run(
        app,
        debug=Config.DEBUG,
    )
