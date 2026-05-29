from datetime import datetime
from bson import ObjectId
from math import radians, sin, cos, sqrt, asin
from pymongo import ASCENDING
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from models.base import besafe_client

agencies_collection = besafe_client.get_collection('Agencies')

try:
    agencies_collection.create_index("phone_number", unique=True)
    agencies_collection.create_index("email", unique=True)
except Exception as e:
    print(f"Index warning: {e}")


def save_agency(name, phone_number, email, password, region, location=None):
    hashed_password = generate_password_hash(password=password)
    email = email.strip().lower()
    phone_number = phone_number.strip()
    doc = {
        "name": name,
        "phone_number": phone_number,
        "email": email.lower(),
        "password_hash": hashed_password,
        "region": region,
        "location": location if location and "lat" in location and "lng" in location else None,
        "created_at": datetime.now(),
    }
    try:
        result = agencies_collection.insert_one(doc)
        return {
            "success": True,
            "agency_id": str(result.inserted_id),
            "message": "Agency created successfully"
        }
    except DuplicateKeyError as e:
        error_message = str(e)
        if "email" in error_message:
            message = "Email already exists"
        elif "phone_number" in error_message:
            message = "Phone number already exists"
        else:
            message = "Duplicate data exists"
        return {"success": False, "message": message}


def get_agency(agency_id):
    try:
        return agencies_collection.find_one({'_id': ObjectId(agency_id)})
    except Exception as e:
        print(e)


def get_agency_by_phone(phone_number):
    try:
        return agencies_collection.find_one({"phone_number": phone_number})
    except Exception as e:
        print(e)


def get_agency_by_id(agency_id):
    try:
        return agencies_collection.find_one({"_id": ObjectId(agency_id)})
    except Exception as e:
        print(e)
        return None


def get_agency_by_email(email):
    try:
        return agencies_collection.find_one({"email": email.lower()})
    except Exception:
        return None


def verify_agency_password(agency, password):
    if not agency or not agency.get("password_hash"):
        return False
    return check_password_hash(agency["password_hash"], password)


def update_agency(agency_id, new_details):
    update = {
        "name": new_details["name"],
        "region": new_details["region"],
        "phone_number": new_details["phone_number"],
        "email": new_details["email"].lower(),
    }
    loc = new_details.get("location")
    if loc and "lat" in loc and "lng" in loc:
        update["location"] = loc
    result = agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": update}
    )
    return result


def update_agency_password(agency_id, new_password):
    agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {"password_hash": generate_password_hash(new_password)}}
    )


def delete_agency(agency_id):
    result = agencies_collection.delete_one({"_id": ObjectId(agency_id)})
    return result.deleted_count > 0


# ─────────────────────────────────────────────────────────────
#  LOCATION-BASED ROUTING
# ─────────────────────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2):
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def get_nearest_agencies(lat, lng, limit=3):
    """Return the closest `limit` agencies that have a location set, sorted by distance."""
    all_with_loc = list(agencies_collection.find(
        {"location": {"$exists": True, "$ne": None}}
    ))
    if not all_with_loc:
        return []
    all_with_loc.sort(key=lambda a: _haversine_km(
        lat, lng, a["location"]["lat"], a["location"]["lng"]
    ))
    return all_with_loc[:limit]


def get_all_agencies():
    """Return every agency in the database (fallback when no pins are set)."""
    return list(agencies_collection.find({}))


def update_agency_location(agency_id, lat, lng):
    agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {"location": {"lat": lat, "lng": lng}}}
    )


def agencies_have_location():
    """Return True if at least one agency has a location pin set."""
    return agencies_collection.count_documents(
        {"location": {"$exists": True, "$ne": None}}
    ) > 0
