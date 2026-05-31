from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from db import get_due_checks, get_overdue_checks, get_active_checks_not_due, get_user_by_id, update_many_safety_checks
from services.notification_service import send_to_emergency_contacts, send_to_user
from services.safety_check_service import format_contact_summary
from services.sos_service import send_sos

GRACE_PERIOD_MINUTES = 2
GRACE_PERIOD_SECONDS = GRACE_PERIOD_MINUTES * 60

scheduler = BackgroundScheduler()


def _seconds_until(dt, now):
    return max(0, int((dt - now).total_seconds()))


def _seconds_since(dt, now):
    return max(0, int((now - dt).total_seconds()))


def _tick_minute():
    now = datetime.now()

    # State 1: active checks not yet due — send tick notification
    for check in get_active_checks_not_due(now):
        seconds_left = _seconds_until(check["nextCheckAt"], now)
        minutes_left = max(0, -(-seconds_left // 60))

        send_to_user(str(check["userId"]), "SAFETY_CHECK_TICK", {
            "minutesLeft": minutes_left,
            "secondsLeft": seconds_left,
            "activity": check.get("activity", ""),
            "checkId": str(check["_id"]),
        })

    # State 3: overdue past grace period — trigger SOS
    cutoff = now - timedelta(minutes=GRACE_PERIOD_MINUTES)
    for check in get_overdue_checks(cutoff):
        user_id = str(check["userId"])
        print(f"[SafetyCheck Job] OVERDUE — triggering SOS for user: {user_id}")

        update_many_safety_checks(
            {"_id": check["_id"], "status": "active"},
            {"status": "triggered"},
        )

        contacts_summary = format_contact_summary(user_id, check.get("contactIds", []))

        send_to_user(user_id, "SAFETY_CHECK_OVERDUE", {
            "contactsSummary": contacts_summary,
            "contactCount": len(check.get("contactIds", [])),
            "checkId": str(check["_id"]),
        })

        send_to_emergency_contacts(user_id, "SOS_ALERT", {}, check.get("contactIds", []))

        payload = {}
        last_location = check.get("lastLocation")
        if last_location:
            payload["location"] = last_location

        user = get_user_by_id(user_id)
        if user:
            try:
                send_sos(user, payload)
            except Exception as e:
                print(f"[SafetyCheck Job] send_sos failed for {user_id}: {e}")


def _tick_30_seconds():
    now = datetime.now()
    grace_start = now - timedelta(minutes=GRACE_PERIOD_MINUTES)

    for check in get_due_checks(now, grace_start):
        user_id = str(check["userId"])
        elapsed = _seconds_since(check["nextCheckAt"], now)
        seconds_left = max(0, GRACE_PERIOD_SECONDS - elapsed)
        minutes_left = max(0, -(-seconds_left // 60))
        notif_type = "SAFETY_CHECK_DUE" if elapsed < 30 else "SAFETY_CHECK_DUE_TICK"

        print(f"[SafetyCheck Job] Check due for user: {user_id}, secondsLeft={seconds_left}")
        send_to_user(user_id, notif_type, {
            "minutesLeft": minutes_left,
            "secondsLeft": seconds_left,
            "checkId": str(check["_id"]),
        })


def start_safety_check_job():
    scheduler.add_job(_tick_minute, "interval", minutes=1, id="safety_check_60s")
    scheduler.add_job(_tick_30_seconds, "interval", seconds=30, id="safety_check_30s")
    scheduler.start()
    print("[SafetyCheck Job] Scheduler started — running every minute and every 30 seconds")
