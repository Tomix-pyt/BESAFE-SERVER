from flask_socketio import join_room
from auth.helpers import verify_jwt
from db import get_user_by_id
from socket_instance import socketio

def register_socket_events(sio=socketio):
    @sio.on("connect")
    def on_connect():
        print("[WS] Client connected")

    @sio.on("disconnect")
    def on_disconnect():
        print("[WS] Client disconnected")

    @sio.on("join")
    def on_join(data):
        agency_id = (data or {}).get("agency_id")
        if agency_id:
            join_room(f"agency_{agency_id}")
            print(f"[WS] Agency {agency_id} joined room")

    @sio.on("safety:auth")
    def on_safety_auth(data):
        token = (data or {}).get("token", "").strip()
        if not token:
            return

        payload = verify_jwt(token, "access")
        if not payload:
            return

        user_id = payload.get("id")
        if not user_id:
            return

        user = get_user_by_id(user_id)
        if not user:
            return

        join_room(f"user_{user_id}")
        print(f"[WS] User {user_id} authenticated and joined room")

    @sio.on("safety:location")
    def on_safety_location(data):
        data = data or {}
        token = data.get("token", "").strip()
        if not token:
            return

        payload = verify_jwt(token, "access")
        if not payload:
            return

        user_id = payload.get("id")
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if latitude is None or longitude is None:
            return

        user = get_user_by_id(user_id)
        if not user:
            return

        try:
            from services.safety_check_service import update_location
            loc = {"latitude": latitude, "longitude": longitude}
            update_location(user_id, loc)
        except Exception as e:
            print(f"[WS Location Error]: {e}")
