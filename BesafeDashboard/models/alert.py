from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from models.base import besafe_client

alerts_collection = besafe_client.get_collection('Alerts')
locations_collection = besafe_client.get_collection('Locations')

try:
    alerts_collection.create_index([("agency_id", ASCENDING)])
    alerts_collection.create_index([("status", ASCENDING)])
    alerts_collection.create_index([("created_at", DESCENDING)])
    locations_collection.create_index([("alert_id", ASCENDING)])
    locations_collection.create_index([("recorded_at", DESCENDING)])
except Exception as e:
    print(f"Index warning: {e}")


def save_alert(user_id, user_name, label, user_phone, user_photo, transcribed_text,
               confidence, gps_lat, gps_lng, sos_contacts=None, agency_id=None):
    result = alerts_collection.insert_one({
        "user_id": user_id,
        "user_name": user_name,
        "user_phone": user_phone,
        "user_photo": user_photo or "",
        "transcribed_text": transcribed_text,
        "label": label,
        "confidence": float(confidence),
        "gps_lat": gps_lat,
        "gps_lng": gps_lng,
        "status": "active",
        "analysis_status": "pending",
        "ai_analysis": None,
        "sos_contacts": sos_contacts or [],
        "agency_id": agency_id,
        "created_at": datetime.now(),
        "updated_at": None
    })
    return str(result.inserted_id)


def get_alerts_for_agency(agency_id, status=None, limit=500):
    query = {"agency_id": agency_id}
    if status and status != "all":
        query["status"] = status
    return list(
        alerts_collection.find(query)
        .sort("created_at", DESCENDING)
        .limit(limit)
    )


def get_alert_by_id(alert_id):
    try:
        return alerts_collection.find_one({"_id": ObjectId(alert_id)})
    except Exception:
        return None


def get_active_alerts_for_agency(agency_id):
    return get_alerts_for_agency(agency_id, status="active")


def update_alert_status(alert_id, new_status):
    valid = {"acknowledged", "resolved"}
    if new_status not in valid:
        raise ValueError(f"status must be one of {valid}")
    result = alerts_collection.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"status": new_status, "updated_at": datetime.now()}}
    )
    return result.modified_count > 0


def assign_alert_staff(alert_id, staff_id, staff_name):
    """
    Assigns a station dispatcher to handle this emergency alert.
    """
    now = datetime.now()
    result = alerts_collection.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "assigned_staff_id": str(staff_id) if staff_id else None,
            "assigned_staff_name": staff_name if staff_id else None,
            "assigned_at": now if staff_id else None,
            "updated_at": now
        }}
    )
    return result.modified_count > 0



def update_alert_analysis(alert_id, analysis_result):
    result = alerts_collection.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "ai_analysis": analysis_result,
            "analysis_status": "completed",
            "updated_at": datetime.now()
        }}
    )
    return result.modified_count > 0


def get_active_alerts_for_user(user_id):
    return list(alerts_collection.find({"user_id": user_id, "status": "active"}))


def get_alert_counts_for_agency(agency_id):
    return {
        "active": alerts_collection.count_documents(
            {"agency_id": agency_id, "status": "active"}),
        "acknowledged": alerts_collection.count_documents(
            {"agency_id": agency_id, "status": "acknowledged"}),
        "resolved": alerts_collection.count_documents(
            {"agency_id": agency_id, "status": "resolved"}),
        "total": alerts_collection.count_documents({"agency_id": agency_id}),
    }


def get_dashboard_overview_stats(agency_id):
    from datetime import datetime, timedelta
    from models.safe_chat_report import reports_collection

    now = datetime.now()
    one_day_ago = now - timedelta(days=1)

    active_alerts = alerts_collection.count_documents(
        {"agency_id": agency_id, "status": "active"}
    )
    pending_reports = reports_collection.count_documents(
        {
            "submittedToAgency": True,
            "assignedAgencyId": agency_id,
            "status": {"$in": ["pending", "pending_analysis"]},
        }
    )
    resolved_today = alerts_collection.count_documents(
        {
            "agency_id": agency_id,
            "status": "resolved",
            "created_at": {"$gte": one_day_ago},
        }
    )
    total_alerts = alerts_collection.count_documents({"agency_id": agency_id})
    total_reports = reports_collection.count_documents(
        {
            "submittedToAgency": True,
            "assignedAgencyId": agency_id,
        }
    )
    total_all_time = total_alerts + total_reports

    # 1. Real 7-Day Rolling Volume Trend
    weekly_volume = []
    days_map = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for i in range(6, -1, -1):
        day_date = now - timedelta(days=i)
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        day_alerts = alerts_collection.count_documents({
            "agency_id": agency_id,
            "created_at": {"$gte": day_start, "$lt": day_end}
        })
        day_reports = reports_collection.count_documents({
            "submittedToAgency": True,
            "assignedAgencyId": agency_id,
            "$or": [
                {"createdAt": {"$gte": day_start, "$lt": day_end}},
                {"created_at": {"$gte": day_start, "$lt": day_end}},
            ]
        })
        total_day = day_alerts + day_reports
        day_name = days_map[day_start.weekday()]
        weekly_volume.append({
            "day": day_name,
            "date": day_start.strftime("%b %d"),
            "count": total_day,
            "alerts": day_alerts,
            "reports": day_reports,
        })

    # 2. Real Threat Category Distribution
    voice_threat_count = total_alerts
    report_categories = [
        {"key": "harassment", "label": "Harassment Reports", "color": "bg-primary"},
        {"key": "domestic_violence", "aliases": ["domestic_violence", "abuse", "abuse-home"], "label": "Domestic Disturbance", "color": "bg-amber-500"},
        {"key": "assault", "label": "Assault & Physical Hazard", "color": "bg-red-500"},
        {"key": "transport", "label": "Unsafe Ride / Transit", "color": "bg-indigo-400"},
        {"key": "community", "label": "Community Concern", "color": "bg-blue-400"},
    ]

    distribution = []
    if total_all_time > 0:
        pct = round((voice_threat_count / total_all_time) * 100)
        distribution.append({
            "label": "Voice Threat SOS",
            "count": voice_threat_count,
            "percentage": f"{pct}%",
            "color": "bg-destructive",
        })

        for cat in report_categories:
            match_filter = {"submittedToAgency": True, "assignedAgencyId": agency_id}
            if "aliases" in cat:
                match_filter["category"] = {"$in": cat["aliases"]}
            else:
                match_filter["category"] = cat["key"]

            c_count = reports_collection.count_documents(match_filter)
            c_pct = round((c_count / total_all_time) * 100)
            distribution.append({
                "label": cat["label"],
                "count": c_count,
                "percentage": f"{c_pct}%",
                "color": cat["color"],
            })
    else:
        distribution = [
            {"label": "Voice Threat SOS", "count": 0, "percentage": "0%", "color": "bg-destructive"},
            {"label": "Harassment Reports", "count": 0, "percentage": "0%", "color": "bg-primary"},
            {"label": "Domestic Disturbance", "count": 0, "percentage": "0%", "color": "bg-amber-500"},
            {"label": "Unsafe Ride Distress", "count": 0, "percentage": "0%", "color": "bg-indigo-400"},
        ]

    return {
        "active_alerts": active_alerts,
        "pending_reports": pending_reports,
        "resolved_today": resolved_today,
        "total_all_time": total_all_time,
        "weekly_volume": weekly_volume,
        "category_distribution": distribution,
        "active": active_alerts,
        "pending": pending_reports,
        "resolved": resolved_today,
        "total": total_all_time,
    }



def get_recent_alerts(limit=50):
    return list(
        alerts_collection.find()
        .sort("created_at", DESCENDING)
        .limit(limit)
    )


def save_location_ping(alert_id, lat, lng):
    result = locations_collection.insert_one({
        "alert_id": alert_id,
        "lat": float(lat),
        "lng": float(lng),
        "recorded_at": datetime.now()
    })
    return str(result.inserted_id)


def get_latest_location(alert_id):
    doc = locations_collection.find_one(
        {"alert_id": alert_id},
        sort=[("recorded_at", DESCENDING)]
    )
    if doc:
        return {"lat": doc["lat"], "lng": doc["lng"],
                "recorded_at": doc["recorded_at"]}
    return None


def get_location_track(alert_id, limit=200):
    pings = list(
        locations_collection.find({"alert_id": alert_id})
        .sort("recorded_at", ASCENDING)
        .limit(limit)
    )
    return [{"lat": p["lat"], "lng": p["lng"]} for p in pings]


def get_location_ping_count(alert_id):
    return locations_collection.count_documents({"alert_id": alert_id})


def delete_location_track(alert_id):
    result = locations_collection.delete_many({"alert_id": alert_id})
    return result.deleted_count
