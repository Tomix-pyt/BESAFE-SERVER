from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from models.base import besafe_client

staff_collection = besafe_client.get_collection('AgencyStaff')

try:
    staff_collection.create_index("email", unique=True)
    staff_collection.create_index([("agency_id", ASCENDING)])
    staff_collection.create_index([("role", ASCENDING)])
    staff_collection.create_index([("is_active", ASCENDING)])
except Exception as e:
    print(f"Staff index warning: {e}")


def save_staff(agency_id, name, email, phone, password, role="DISPATCHER", created_by=None):
    """
    Creates a new staff/operator account for an agency with mandatory first-time password change.
    """
    now = datetime.now()
    doc = {
        "agency_id": agency_id,
        "name": name.strip(),
        "email": email.strip().lower(),
        "phone_number": (phone or "").strip(),
        "password_hash": generate_password_hash(password),
        "role": "DISPATCHER",
        "is_active": True,
        "must_change_password": True,
        "created_by": created_by or agency_id,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = staff_collection.insert_one(doc)
        return {"success": True, "staff_id": str(result.inserted_id)}
    except DuplicateKeyError:
        return {"success": False, "message": "A staff member with this email already exists"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_staff_by_id(staff_id):
    try:
        return staff_collection.find_one({"_id": ObjectId(staff_id)})
    except Exception:
        return None


def get_staff_by_email(email):
    if not email:
        return None
    return staff_collection.find_one({"email": email.strip().lower()})


def get_staff_for_agency(agency_id):
    """
    Returns all staff/operators assigned to a specific agency.
    """
    try:
        return list(
            staff_collection.find({"agency_id": agency_id})
            .sort("created_at", ASCENDING)
        )
    except Exception:
        return []


def update_staff_role(staff_id, new_role):
    """
    Promote or demote a staff member (DISPATCHER <-> AGENCY_ADMIN).
    """
    if new_role not in ["DISPATCHER", "AGENCY_ADMIN"]:
        return False
    try:
        result = staff_collection.update_one(
            {"_id": ObjectId(staff_id)},
            {"$set": {"role": new_role, "updated_at": datetime.now()}}
        )
        return result.modified_count > 0
    except Exception:
        return False


def update_staff_status(staff_id, is_active):
    """
    Activate or suspend/revoke a staff member's access.
    """
    try:
        result = staff_collection.update_one(
            {"_id": ObjectId(staff_id)},
            {"$set": {"is_active": bool(is_active), "updated_at": datetime.now()}}
        )
        return result.modified_count > 0
    except Exception:
        return False


def change_staff_password(staff_id, new_password):
    """
    Updates the staff member's password and clears the must_change_password flag.
    """
    try:
        result = staff_collection.update_one(
            {"_id": ObjectId(staff_id)},
            {"$set": {
                "password_hash": generate_password_hash(new_password),
                "must_change_password": False,
                "updated_at": datetime.now()
            }}
        )
        return result.modified_count > 0
    except Exception:
        return False


def verify_staff_password(staff, password):
    if not staff or not staff.get("password_hash"):
        return False
    return check_password_hash(staff["password_hash"], password)


def delete_staff(staff_id):
    try:
        result = staff_collection.delete_one({"_id": ObjectId(staff_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def serialize_staff(doc):
    if not doc:
        return None
    created = doc.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    updated = doc.get("updated_at")
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    return {
        "id": str(doc["_id"]),
        "agency_id": str(doc.get("agency_id", "")),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "phone_number": doc.get("phone_number", ""),
        "role": doc.get("role", "DISPATCHER"),
        "is_active": doc.get("is_active", True),
        "must_change_password": doc.get("must_change_password", False),
        "created_at": created,
        "updated_at": updated,
    }
