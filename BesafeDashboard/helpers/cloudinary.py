import cloudinary
import cloudinary.uploader
from config import Config

cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
)

EVIDENCE_FOLDER = "besafe/evidence"
PROFILE_FOLDER = "besafe/profile_pictures"

RESOURCE_TYPE_MAP = {
    "photo": "image",
    "audio": "video",
    "video": "video",
    "document": "raw",
}


def upload_file(file_storage, folder, public_id=None, resource_type="image"):
    kwargs = {
        "folder": folder,
        "resource_type": resource_type,
        "public_id": public_id or f"file_{__import__('time').time_ns()}",
    }
    if resource_type == "image":
        kwargs["format"] = "jpg"
    result = cloudinary.uploader.upload(file_storage, **kwargs)
    return result.get("secure_url", "")


def upload_evidence(file_storage, file_type):
    resource_type = RESOURCE_TYPE_MAP.get(file_type, "raw")
    return upload_file(
        file_storage,
        folder=EVIDENCE_FOLDER,
        resource_type=resource_type,
    )


def upload_profile_picture(file_storage):
    return upload_file(
        file_storage,
        folder=PROFILE_FOLDER,
        resource_type="image",
    )
