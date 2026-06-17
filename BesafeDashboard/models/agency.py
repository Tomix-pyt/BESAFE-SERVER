from datetime import datetime
from bson import ObjectId
from math import radians, sin, cos, sqrt, asin
from flask import jsonify
from pymongo import ASCENDING
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from models.base import besafe_client

agencies_collection = besafe_client.get_collection('Agencies')

try:
    agencies_collection.create_index("phone_number", unique=True)
    agencies_collection.create_index("email",        unique=True)
    agencies_collection.create_index([("location", "2dsphere")])
except Exception as e:
    print(f"Index warning: {e}")


def save_agency(name, phone_number, email, password, region, lat, lng):
    doc = {
        "name":          name,
        "phone_number":  phone_number,
        "email":         email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "region":        region,
        "location": {
            "type":        "Point",
            "coordinates": [float(lat), float(lng)]  
        },
        "created_at": datetime.now(),
    }
    try:
        result = agencies_collection.insert_one(doc)
        return {"success": True, "agency_id": str(result.inserted_id)}
    except DuplicateKeyError as e:
        error_message = str(e)
        if "email" in error_message:
            message = "Email already exists"
        elif "phone_number" in error_message:
            message = "Phone number already exists"
        else:
            message = "Duplicate data exists"
        return {"success": False, "message": message}

def get_agency_by_phone(phone_number):
    try:
        return agencies_collection.find_one({"phone_number": phone_number})
    except Exception as e:
         return jsonify({"error": e})


def get_agency_by_id(agency_id):
    try:
        return agencies_collection.find_one({"_id": ObjectId(agency_id)})
    except Exception as e:
         return jsonify({"error": e})


def get_agency_by_email(email):
    try:
        return agencies_collection.find_one({"email": email.lower()})
    except Exception as e:
        return jsonify({"error": e})

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

    result = agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": update}
    )
    return result

def update_agency_location(agency_id, lat, lng):
    
    agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {"location": {
            "type":        "Point",
            "coordinates": [float(lat), float(lng)]}}}
    )


def update_agency_password(agency_id, new_password):
    agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {"password_hash": generate_password_hash(new_password)}}
    )

# for future use for now
def delete_agency(agency_id):
    result = agencies_collection.delete_one({"_id": ObjectId(agency_id)})
    return result.deleted_count > 0


# ─────────────────────────────────────────────────────────────
#  LOCATION-BASED ROUTING
# ─────────────────────────────────────────────────────────────
def get_nearest_agencies(lat, lng, max_distance_km=100000000, limit=1):
    """
    Return the closest agencies within max_distance_km using
    MongoDB's $near geospatial query — sorted by distance automatically.

    GeoJSON uses [longitude, latitude] order.
    max_distance is in metres so multiply km by 1000.
    """
    try:
        results = list(agencies_collection.find(
            {
                "location": {
                    "$near": {
                        "$geometry": {
                            "type":        "Point",
                            "coordinates": [float(lat), float(lng)]
                        },
                        "$maxDistance": max_distance_km * 1000
                    }
                }
            }
        ).limit(limit))
        return results
    except Exception as e:
        print(f"[GEO QUERY ERROR] {e}")
        return []
# for future use for now
def get_all_agencies():
    """Return every agency in the database (fallback when no pins are set)."""
    return list(agencies_collection.find({}))


def agencies_have_location():
    """Return True if at least one agency has a location pin set."""
    return agencies_collection.count_documents(
        {"location": {"$exists": True, "$ne": None}}
    ) > 0
