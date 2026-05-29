from models.base import client, besafe_client

from models.agency import (
    save_agency,
    get_agency,
    get_agency_by_phone,
    get_agency_by_id,
    get_agency_by_email,
    verify_agency_password,
    update_agency,
    update_agency_password,
    delete_agency,
)

from models.alert import (
    save_alert,
    get_alerts_for_agency,
    get_alert_by_id,
    get_active_alerts_for_agency,
    update_alert_status,
    get_alert_counts_for_agency,
    get_recent_alerts,
    save_location_ping,
    get_latest_location,
    get_location_track,
    get_location_ping_count,
    delete_location_track,
)

from models.user import (
    save_user,
    serialize_user,
    get_user_by_id,
    get_user_by_phone,
    get_user_by_email,
    get_user_by_phone_batch,
    update_user_by_id,
    add_push_token,
    remove_push_token,
    update_user_last_seen,
    get_watchers,
)

from models.otp import (
    save_otp_session,
    find_otp_session,
    update_otp_session,
    delete_otp_session,
    upsert_otp_session,
)

from models.refresh_token import (
    save_refresh_token,
    find_refresh_token,
    delete_refresh_token,
    delete_user_refresh_tokens,
)

from models.safety_check import (
    create_safety_check,
    get_active_check,
    get_active_checks_not_due,
    get_overdue_checks,
    get_due_checks,
    update_safety_check,
    cancel_user_checks,
    update_many_safety_checks,
)
