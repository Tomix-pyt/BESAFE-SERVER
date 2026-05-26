from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING
from models.base import besafe_client

safety_checks_collection = besafe_client.get_collection('SafetyChecks')

try:
    safety_checks_collection.create_index([("userId", ASCENDING)])
    safety_checks_collection.create_index([("status", ASCENDING)])
    safety_checks_collection.create_index([("nextCheckAt", ASCENDING)])
except Exception as e:
    print(f"Index warning: {e}")


def create_safety_check(data):
    doc = {
        "userId": data["userId"],
        "activity": data["activity"],
        "intervalMinutes": data["intervalMinutes"],
        "contactIds": data.get("contactIds", []),
        "status": "active",
        "nextCheckAt": data["nextCheckAt"],
        "expiresAt": data["expiresAt"],
        "startLocation": data.get("startLocation"),
        "lastLocation": data.get("startLocation"),
        "createdAt": datetime.now(),
        "updatedAt": datetime.now(),
    }
    result = safety_checks_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def get_active_check(user_id):
    return safety_checks_collection.find_one({
        "userId": user_id,
        "status": {"$in": ["active", "triggered"]},
    })


def get_active_checks_not_due(now):
    return list(safety_checks_collection.find({
        "status": "active",
        "nextCheckAt": {"$gt": now},
    }))


def get_overdue_checks(cutoff):
    return list(safety_checks_collection.find({
        "status": "active",
        "nextCheckAt": {"$lt": cutoff},
    }))


def get_due_checks(start, end):
    return list(safety_checks_collection.find({
        "status": "active",
        "nextCheckAt": {"$lte": start, "$gte": end},
    }))


def update_safety_check(check_id, updates):
    updates["updatedAt"] = datetime.now()
    return safety_checks_collection.find_one_and_update(
        {"_id": ObjectId(check_id)},
        {"$set": updates},
        return_document=True,
    )


def cancel_user_checks(user_id):
    safety_checks_collection.update_many(
        {"userId": user_id, "status": "active"},
        {"$set": {"status": "cancelled", "updatedAt": datetime.now()}}
    )


def update_many_safety_checks(query, updates):
    updates["updatedAt"] = datetime.now()
    safety_checks_collection.update_many(query, {"$set": updates})
