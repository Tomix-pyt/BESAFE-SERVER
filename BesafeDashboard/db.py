from datetime import datetime
import certifi
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash,check_password_hash
from config import Config
from pymongo.errors import DuplicateKeyError

client = MongoClient(Config.MONGO_URI,tlsCAFile=certifi.where())
besafe_client = client.get_database('BesafeDB')


# ── Collections
agencies_collection  = besafe_client.get_collection('Agencies')
alerts_collection    = besafe_client.get_collection('Alerts')
locations_collection = besafe_client.get_collection('Locations')

#── Indexes on startup
try:
    agencies_collection.create_index("phone_number", unique=True)
    agencies_collection.create_index("email",        unique=True)
    alerts_collection.create_index([("agency_id",  ASCENDING)])
    alerts_collection.create_index([("status",     ASCENDING)])
    alerts_collection.create_index([("created_at", DESCENDING)])
    locations_collection.create_index([("alert_id",    ASCENDING)])
    locations_collection.create_index([("recorded_at", DESCENDING)])
except Exception as e:
    print(f" there is an Index warning: {e}")


# ── Fuctions/Logic

def save_agency(name,phone_number,email,password,region):
    hashed_password = generate_password_hash(password=password)
    email = email.strip().lower()
    phone_number = phone_number.strip()
    doc = {
        "name":          name,
        "phone_number":  phone_number,
        "email":         email.lower(),
        "password_hash": hashed_password,
        "region":        region,
        "created_at":    datetime.now(),
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
        return {
            "success": False,
            "message": message
        }
def get_agency(agency_id):
   """Fetch a single agency by its ObjectId string.
    Returns the document dict or None.
    """
   try:
       return agencies_collection.find_one({'_id': ObjectId(agency_id)})
   except Exception as e:
       print(e)

def get_agency_by_phone(phone_number):
    """
    Fetch an agency by its registered phone number.
    """
    try:
        return agencies_collection.find_one({"phone_number": phone_number})
    except Exception as e:
        print(e)
def get_agency_by_id(agency_id):
    """
    Fetch an agency by its unique ID (the _id string from JWT).
    """
    try:
        return agencies_collection.find_one({"_id": ObjectId(agency_id)})
    except Exception as e:
        print(e)
        return None
def verify_agency_password(agency, password):
    """
    Check a plaintext password against the stored hash.
    """
    if not agency or not agency.get("password_hash"):
        return False
    return check_password_hash(agency["password_hash"], password)

def  update_agency(agency_id,new_details):
    result = agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {
        "name":         new_details["name"],
        "region":       new_details["region"],
        "phone_number": new_details["phone_number"],
        "email":        new_details["email"].lower()}
    })
    return result

def  update_agency_password(agency_id,new_password):
    result = agencies_collection.update_one(
        {"_id": ObjectId(agency_id)},
        {"$set": {
        "password_hash": generate_password_hash(new_password)}
    })

def delete_agency(agency_id):
    """
    Remove an agency account.
    Returns True if deleted.
    """
    result = agencies_collection.delete_one({"_id": ObjectId(agency_id)})
    return result.deleted_count > 0

def save_alert(user_id, user_name, user_phone, user_photo, transcribed_text,confidence,gps_lat, gps_lng,agency_id=None,sos_contacts=[]):
    """
    Save a new threat alert to the database.

    Called by Flask after the NLP model confirms a threat.
    agency_id is the string _id of the matched agency (or None if no
    agency was found in the SOS contacts list).

    Returns the new alert's ObjectId string.
    """
    result = alerts_collection.insert_one({
        "user_id":          user_id,
        "user_name":        user_name,
        "user_phone":       user_phone,
        "user_photo":       user_photo or "",
        "transcribed_text": transcribed_text,
        "label":            "",
        "confidence":       float(confidence),
        "gps_lat":          gps_lat,
        "gps_lng":          gps_lng,
        "status":           "active",    
        "agency_id":        agency_id,
        "created_at":       datetime.now(),
        "sos_contacts":  sos_contacts,
        "updated_at":       None
    })
    return str(result.inserted_id)

def get_alerts_for_agency(agency_id, status=None, limit=100):
    """
    Fetch all alerts that belong to a specific agency.

    status can be:
        "active"       — only unacknowledged threats
        "acknowledged" — seen by police, not yet resolved
        "resolved"     — closed
        None / "all"   — return everything

    Results are sorted newest-first. The caller (app.py) then re-sorts
    by priority score after fetching.
    """
    query = {"agency_id": agency_id}
    if status and status != "all":
        query["status"] = status

    return list(
        alerts_collection.find(query)
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    
def get_alert_by_id(alert_id):
    """
    Fetch a single alert by its ObjectId string.
    Returns the document dict or None.
    """
    try:
        return alerts_collection.find_one({"_id": ObjectId(alert_id)})
    except Exception:
        return None

def get_agency_by_email(email):
    """
    Fetch a single agency by email. Used for login.
    Returns the document dict or None.
    """
    try:
        return agencies_collection.find_one({"email": email.lower()})
    except Exception:
        return None

def get_alerts_for_agency(agency_id, status=None, limit=100):
    """
    Fetch all alerts that belong to a specific agency.

    status can be:
        "active"       — only unacknowledged threats
        "acknowledged" — seen by police, not yet resolved
        "resolved"     — closed
        None / "all"   — return everything

    Results are sorted newest-first. The caller (app.py) then re-sorts
    by priority score after fetching.
    """
    query = {"agency_id": agency_id}
    if status and status != "all":
        query["status"] = status

    return list(
        alerts_collection.find(query)
        .sort("created_at", DESCENDING)
        .limit(limit)
    )


def get_active_alerts_for_agency(agency_id):
    """
    Shorthand for fetching only active (unacknowledged) alerts.
    Used by the dashboard on first load.
    """
    return get_alerts_for_agency(agency_id, status="active")


def update_alert_status(alert_id, new_status):
    """
    Change an alert's status.
    new_status must be one of: "acknowledged", "resolved"

    Returns True if a document was modified.
    """
    valid = {"acknowledged", "resolved"}
    if new_status not in valid:
        raise ValueError(f"status must be one of {valid}")

    result = alerts_collection.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "status":     new_status,
            "updated_at": datetime.now()
        }}
    )
    return result.modified_count > 0


def get_alert_counts_for_agency(agency_id):
    """
    Return a summary count dict for the navbar stats pills.
    {
        "active": int,
        "acknowledged": int,
        "resolved": int,
        "total": int
    }
    """
    return {
        "active":       alerts_collection.count_documents({"agency_id": agency_id, "status": "active"}),
        "acknowledged": alerts_collection.count_documents({"agency_id": agency_id, "status": "acknowledged"}),
        "resolved":     alerts_collection.count_documents({"agency_id": agency_id, "status": "resolved"}),
        "total":        alerts_collection.count_documents({"agency_id": agency_id}),
    }


def get_recent_alerts(limit=50):
    """
    Return the most recent alerts across ALL agencies.
    For admin/oversight use.
    """
    return list(
        alerts_collection.find()
        .sort("created_at", DESCENDING)
        .limit(limit)
    )



# ═══════════════════════════════════════════════════════════════
#  LIVE LOCATION FUNCTIONS - These are to be implemented later i made them to save me time in future
# ═══════════════════════════════════════════════════════════════

def save_location_ping(alert_id, lat, lng):
    """
    Save a single GPS ping from the mobile app.

    The app calls POST /location/update every 5–10 seconds while
    a threat is active. Each call lands here as a new document.

    Returns the inserted ObjectId string.
    """
    result = locations_collection.insert_one({
        "alert_id":    alert_id,
        "lat":         float(lat),
        "lng":         float(lng),
        "recorded_at": datetime.now()
    })
    return str(result.inserted_id)


def get_latest_location(alert_id):
    """
    Fetch the single most recent GPS ping for an alert.
    Used to place the marker on the map when first loading an alert.
    Returns a dict with lat/lng or None.
    """
    doc = locations_collection.find_one(
        {"alert_id": alert_id},
        sort=[("recorded_at", DESCENDING)]
    )
    if doc:
        return {"lat": doc["lat"], "lng": doc["lng"], "recorded_at": doc["recorded_at"]}
    return None


def get_location_track(alert_id, limit=500):
    """
    Fetch the full ordered GPS trail for an alert.
    Used to draw the polyline (movement path) on the map when
    an officer clicks "Track Live Location".

    Returns a list of dicts: [{"lat": ..., "lng": ...}, ...]
    Ordered oldest → newest so the line draws correctly.
    """
    pings = list(
        locations_collection.find({"alert_id": alert_id})
        .sort("recorded_at", ASCENDING)
        .limit(limit)
    )
    return [{"lat": p["lat"], "lng": p["lng"]} for p in pings]


def get_location_ping_count(alert_id):
    """
    How many GPS pings have been received for this alert.
    Useful for knowing if tracking has started.
    """
    return locations_collection.count_documents({"alert_id": alert_id})


def delete_location_track(alert_id):
    """
    Delete all GPS pings for a specific alert.
    Called internally by delete_alert(), or use directly to clear a track.
    Returns the number of documents deleted.
    """
    result = locations_collection.delete_many({"alert_id": alert_id})
    return result.deleted_count

