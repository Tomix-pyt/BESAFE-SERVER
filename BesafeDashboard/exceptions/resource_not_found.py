from exceptions.app_exception import AppException
from exceptions.codes import RESOURCE_NOT_FOUND


class ResourceNotFoundException(AppException):
    def __init__(self, message="Resource not found"):
        super().__init__(message, code=RESOURCE_NOT_FOUND, status_code=404)
