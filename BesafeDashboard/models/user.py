from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from models.base import besafe_client

users_collection = besafe_client.get_collection('Users')

try:
    users_collection.create_index("phone", unique=True)
    users_collection.create_index([("email", ASCENDING)], unique=True, sparse=True)
    users_collection.create_index([("emergencyContacts.phone", ASCENDING)])
except Exception as e:
    print(f"Index warning: {e}")


def save_user(phone):
    doc = {
        "phone": phone,
        "name": None,
        "isEmailVerified": False,
        "profilePicture": None,
        "role": "user",
        "isOnboarded": False,
        "isActive": True,
        "emergencyContacts": [],
        "lastSeenAt": None,
        "lastLocation": None,
        "pushTokens": [],
        "settings": {
            "liveLocationSharing": True,
        },
        "createdAt": datetime.now(),
        "updatedAt": datetime.now(),
    }
    try:
        result = users_collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
    except DuplicateKeyError:
        return None


def serialize_user(user):
    """Convert MongoDB user doc to JSON-safe dict with string _id."""
    if not user:
        return None
    return {
        **user,
        "_id": str(user["_id"]),
    }


def get_user_by_id(user_id):
    try:
        return users_collection.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def get_user_by_phone(phone):
    return users_collection.find_one({"phone": phone})


def get_user_by_email(email):
    if not email:
        return None
    return users_collection.find_one({"email": email.lower().strip()})


def get_user_by_phone_batch(phones):
    return list(users_collection.find({"phone": {"$in": phones}}))


def update_user_by_id(user_id, update_dict):
    if "$set" in update_dict:
        update_dict["$set"]["updatedAt"] = datetime.now()
    elif "$unset" in update_dict:
        pass
    else:
        update_dict = {"$set": {**update_dict, "updatedAt": datetime.now()}}

    result = users_collection.find_one_and_update(
        {"_id": ObjectId(user_id)},
        update_dict,
        return_document=True,
    )
    return result


def add_push_token(user_id, token):
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"pushTokens": token}}
    )


def remove_push_token(user_id, token):
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"pushTokens": token}}
    )


def update_user_last_seen(user_id):
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"lastSeenAt": datetime.now()}}
    )


def get_watchers(phone):
    """Return users who have this phone in their emergency contacts
       AND have liveLocationSharing enabled, along with their lastLocation."""
    return list(users_collection.find(
        {
            "emergencyContacts.phone": phone,
            "settings.liveLocationSharing": True,
        },
        {
            "_id": 1,
            "name": 1,
            "phone": 1,
            "lastLocation": 1,
        }
    ))
