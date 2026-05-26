import hashlib
import random
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from config import Config
from db import save_refresh_token


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_numeric_otp() -> str:
    return f"{random.randint(1000, 9999)}"


def sign_jwt(payload: dict, token_type: str) -> str:
    secret = (
        Config.JWT_ACCESS_SECRET if token_type == "access"
        else Config.JWT_REFRESH_SECRET
    )
    expiry = (
        Config.JWT_ACCESS_TOKEN_EXPIRATION if token_type == "access"
        else Config.JWT_REFRESH_TOKEN_EXPIRATION
    )
    now = datetime.now(timezone.utc)
    to_sign = {
        **payload,
        "iat": now,
        "exp": now + timedelta(seconds=expiry),
        "type": token_type,
    }
    return pyjwt.encode(to_sign, secret, algorithm="HS256")


def verify_jwt(token: str, token_type: str):
    secret = (
        Config.JWT_ACCESS_SECRET if token_type == "access"
        else Config.JWT_REFRESH_SECRET
    )
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        if payload.get("type") != token_type:
            return None
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def generate_token_pair(user_dict: dict) -> dict:
    payload = {
        "id": str(user_dict["_id"]),
        "phone": user_dict.get("phone", ""),
        "name": user_dict.get("name"),
        "role": user_dict.get("role", "user"),
    }
    access_token = sign_jwt(payload, "access")
    refresh_token = sign_jwt(payload, "refresh")
    save_refresh_token(payload["id"], refresh_token)
    return {"access_token": access_token, "refresh_token": refresh_token}
