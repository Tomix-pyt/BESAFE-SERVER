from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from models.base import besafe_client

users_collection = besafe_client.get_collection('Users')

try:
    users_collection.create_index("phone", unique=True)
    users_collection.create_index([("email", ASCENDING)], unique=True, sparse=True)
except Exception as e:
    print(f"Index warning: {e}")


def save_user(phone):
    doc = {
        "phone": phone,
        "name": None,
        "email": None,
        "isEmailVerified": False,
        "profilePicture": None,
        "role": "user",
        "isOnboarded": False,
        "isActive": True,
        "emergencyContacts": [],
        "lastSeenAt": None,
        "pushTokens": [],
        "settings": {
            "autoCallEmergency": False,
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
    update_dict.setdefault("updatedAt", datetime.now())

    if "$set" in update_dict:
        update_dict["$set"]["updatedAt"] = datetime.now()
    elif "$unset" in update_dict:
        pass
    else:
        update_dict = {"$set": update_dict, "$set": {"updatedAt": datetime.now()}}

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
