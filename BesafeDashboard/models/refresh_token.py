from datetime import datetime
from bson import ObjectId
from models.base import besafe_client
from config import Config

refresh_tokens_collection = besafe_client.get_collection('RefreshTokens')

ttl_seconds = Config.JWT_REFRESH_TOKEN_EXPIRATION_DB

try:
    refresh_tokens_collection.create_index("refresh_token", unique=True)
    refresh_tokens_collection.create_index("user_id")
    refresh_tokens_collection.create_index(
        "createdAt", expireAfterSeconds=ttl_seconds
    )
except Exception as e:
    print(f"Index warning: {e}")


def save_refresh_token(user_id, refresh_token):
    refresh_tokens_collection.update_one(
        {"user_id": str(user_id)},
        {"$set": {
            "refresh_token": refresh_token,
            "createdAt": datetime.now(),
        }},
        upsert=True
    )


def find_refresh_token(token):
    return refresh_tokens_collection.find_one({"refresh_token": token})


def delete_refresh_token(token):
    refresh_tokens_collection.delete_one({"refresh_token": token})


def delete_user_refresh_tokens(user_id):
    refresh_tokens_collection.delete_many({"user_id": str(user_id)})
