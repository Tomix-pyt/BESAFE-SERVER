from datetime import datetime
from bson import ObjectId
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


def save_agency(name, phone_number, email, password, region):
    hashed_password = generate_password_hash(password=password)
    email = email.strip().lower()
    phone_number = phone_number.strip()
    doc = {
        "name": name,
        "phone_number": phone_number,
        "email": email.lower(),
        "password_hash": hashed_password,
        "region": region,
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
    result = agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {
            "name": new_details["name"],
            "region": new_details["region"],
            "phone_number": new_details["phone_number"],
            "email": new_details["email"].lower()}
        })
    return result


def update_agency_password(agency_id, new_password):
    agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {"password_hash": generate_password_hash(new_password)}}
    )


def delete_agency(agency_id):
    result = agencies_collection.delete_one({"_id": ObjectId(agency_id)})
    return result.deleted_count > 0
