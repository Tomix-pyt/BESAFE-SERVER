from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from models.base import besafe_client

reports_collection = besafe_client.get_collection('SafeChatReports')

try:
    reports_collection.create_index([("userId", ASCENDING)])
    reports_collection.create_index([("assignedAgencyId", ASCENDING)])
    reports_collection.create_index([("status", ASCENDING)])
    reports_collection.create_index([("createdAt", DESCENDING)])
except Exception as e:
    print(f"Index warning: {e}")


def save_report(user_id, category, description, timing, frequency,
                location=None, submit_for_help=False, agency_id=None):
    now = datetime.now()
    doc = {
        "userId": user_id,
        "category": category,
        "description": description,
        "timing": timing,
        "frequency": frequency,
        "location": location if location and "lat" in location and "lng" in location else None,
        "status": "new" if submit_for_help else "private",
        "priority": _calculate_priority(category, frequency),
        "submittedToAgency": submit_for_help,
        "assignedAgencyId": agency_id,
        "createdAt": now,
        "updatedAt": now,
    }
    result = reports_collection.insert_one(doc)
    return str(result.inserted_id)


def get_reports_for_user(user_id):
    return list(
        reports_collection.find({"userId": user_id})
        .sort("createdAt", DESCENDING)
    )


def get_report_by_id(report_id):
    try:
        return reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
        return None


def get_reports_for_agency(agency_id, status=None):
    query = {
        "submittedToAgency": True,
        "assignedAgencyId": agency_id,
    }
    if status and status != "all":
        query["status"] = status
    return list(
        reports_collection.find(query)
        .sort("createdAt", DESCENDING)
    )


def get_report_counts_for_agency(agency_id):
    base = {"submittedToAgency": True, "assignedAgencyId": agency_id}
    return {
        "new": reports_collection.count_documents({**base, "status": "new"}),
        "reviewing": reports_collection.count_documents({**base, "status": "reviewing"}),
        "resolved": reports_collection.count_documents({**base, "status": "resolved"}),
        "closed": reports_collection.count_documents({**base, "status": "closed"}),
        "total": reports_collection.count_documents(base),
    }


def update_report_status(report_id, new_status):
    valid = {"reviewing", "resolved", "closed"}
    if new_status not in valid:
        raise ValueError(f"status must be one of {valid}")
    result = reports_collection.update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {"status": new_status, "updatedAt": datetime.now()}}
    )
    return result.modified_count > 0


def _calculate_priority(category, frequency):
    urgent_categories = {"threats", "abuse-home"}
    high_categories = {"harassment", "unsafe-ride"}
    freq_map = {"first": 1, "few": 2, "many": 3}
    score = freq_map.get(frequency, 1)
    if category in urgent_categories:
        score += 2
    elif category in high_categories:
        score += 1
    if score >= 4:
        return "urgent"
    if score >= 2:
        return "medium"
    return "low"
