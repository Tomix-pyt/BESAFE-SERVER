import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── MongoDB
    MONGO_URI = os.getenv("MONGO_URI")

    # ── Flask / Server
    PORT = os.getenv("PORT", "5000")
    DEBUG = os.getenv("DEBUG", "True") == "True"
    SECRET_KEY = os.getenv("SECRET_KEY")

    # ── NLP / AI model
    NLP_API_URL = os.getenv("NLP_API_URL", "https://besafev1.onrender.com/predict")

    # ── JWT (agency dashboard — Flask-JWT-Extended)
    JWT_SECRET = os.getenv("JWT_SECRET")

    # ── JWT (mobile app access & refresh tokens)
    JWT_ACCESS_SECRET = os.getenv("JWT_ACCESS_SECRET", os.getenv("JWT_SECRET"))
    JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", os.getenv("JWT_SECRET"))
    JWT_ACCESS_TOKEN_EXPIRATION = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRATION", "1800"))  # 30 min
    JWT_REFRESH_TOKEN_EXPIRATION = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRATION", "604800"))  # 7 days
    JWT_REFRESH_TOKEN_EXPIRATION_DB = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRATION_DB", "2592000"))  # 30 days

    # ── Cloudinary (profile picture uploads)
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    # ── Mailjet (email)
    MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
    MAILJET_API_SECRET = os.getenv("MAILJET_API_SECRET")
    EMAIL_FROM = os.getenv("EMAIL_FROM")

    # ── Twilio (SMS)
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

    # ── Africa's Talking SMS (fallback / family alerts)
    SMS_USERNAME = os.getenv("SMS_USERNAME")
    SMS_API_KEY = os.getenv("SMS_API_KEY")
