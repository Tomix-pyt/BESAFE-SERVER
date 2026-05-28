import io
import json

import cloudinary
import cloudinary.uploader
from flask import Blueprint, g, request

from auth.middleware import require_auth, require_onboarded
from config import Config
from db import (
    get_user_by_email,
    get_user_by_id,
    update_user_by_id,
)
from exceptions import (
    BadRequestException,
    NotFoundException,
    ConflictException,
    InternalServerErrorException,
)
from helpers.response import ok_response

user_bp = Blueprint("user", __name__)

cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
)


def _upload_to_cloudinary(file_storage):
    result = cloudinary.uploader.upload(
        file_storage,
        folder="besafe/profile_pictures",
        format="jpg",
        public_id=f"profile_{__import__('time').time_ns()}",
        resource_type="image",
    )
    return result.get("secure_url", "")


def _parse_emergency_contacts(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _validate_contacts(contacts):
    for contact in contacts:
        if not isinstance(contact, dict):
            return False, "Each contact must be an object"
        if not contact.get("name", "").strip():
            return False, "Each contact must have a name"
        if not contact.get("relationship", "").strip():
            return False, "Each contact must have a relationship"
        if not contact.get("phone", "").strip() and not contact.get("email", "").strip():
            return False, f'Contact "{contact.get("name")}" must have a phone number or email'
    return True, None


# ── POST /me/onboard
@user_bp.route("/me/onboard", methods=["POST"])
@require_auth
def onboard():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        raise BadRequestException("Name is required")

    email = (data.get("email") or "").strip() or None
    emergency_contacts = data.get("emergencyContacts", [])

    valid, err = _validate_contacts(emergency_contacts)
    if not valid:
        raise BadRequestException(err)

    user_id = str(g.current_user["_id"])
    user = update_user_by_id(user_id, {
        "name": name,
        "email": email,
        "emergencyContacts": emergency_contacts,
        "isOnboarded": True,
    })

    if not user:
        raise NotFoundException("User not found")

    return ok_response("Onboarding complete", {"user": user})


# ── GET /me
@user_bp.route("/me", methods=["GET"])
@require_auth
@require_onboarded
def get_me():
    user_id = str(g.current_user["_id"])
    user = get_user_by_id(user_id)
    if not user:
        raise NotFoundException("User not found")
    return ok_response(data={"user": user})


# ── PATCH /me
@user_bp.route("/me", methods=["PATCH"])
@require_auth
@require_onboarded
def update_me():
    user_id = str(g.current_user["_id"])

    content_type = request.content_type or ""
    is_multipart = "multipart/form-data" in content_type

    if is_multipart:
        form = request.form
        file = request.files.get("profilePicture")
    else:
        form = request.get_json(silent=True) or {}
        file = None

    updates = {}

    name = form.get("name")
    if name is not None:
        updates["name"] = name.strip()

    email = form.get("email")
    if email is not None:
        email_clean = email.strip().lower() if email.strip() else None
        if email_clean:
            existing = get_user_by_email(email_clean)
            if existing and str(existing["_id"]) != user_id:
                raise ConflictException("Email is already in use")
            updates["email"] = email_clean
        else:
            updates["email"] = None
            updates["isEmailVerified"] = False

    if file and file.filename:
        try:
            url = _upload_to_cloudinary(file)
            updates["profilePicture"] = url
        except Exception as e:
            raise InternalServerErrorException(f"Failed to upload image: {str(e)}")
    elif "profilePicture" in form and form.get("profilePicture") == "":
        updates["profilePicture"] = None

    raw_contacts = form.get("emergencyContacts")
    if raw_contacts is not None:
        contacts = _parse_emergency_contacts(raw_contacts)
        if contacts is None:
            raise BadRequestException("Invalid emergencyContacts payload")
        valid, err = _validate_contacts(contacts)
        if not valid:
            raise BadRequestException(err)
        updates["emergencyContacts"] = contacts

    if not updates:
        raise BadRequestException("No fields provided to update")

    user = update_user_by_id(user_id, updates)
    if not user:
        raise NotFoundException("User not found")

    return ok_response("Profile updated", {"user": user})


# ── PATCH /me/settings
@user_bp.route("/me/settings", methods=["PATCH"])
@require_auth
@require_onboarded
def update_settings():
    user_id = str(g.current_user["_id"])
    data = request.get_json(silent=True) or {}

    settings_update = {}
    if "autoCallEmergency" in data:
        settings_update["settings.autoCallEmergency"] = bool(data["autoCallEmergency"])
    if "liveLocationSharing" in data:
        settings_update["settings.liveLocationSharing"] = bool(data["liveLocationSharing"])

    if not settings_update:
        raise BadRequestException("No settings provided to update")

    user = update_user_by_id(user_id, settings_update)
    if not user:
        raise NotFoundException("User not found")

    return ok_response("Settings updated", {"user": user})
