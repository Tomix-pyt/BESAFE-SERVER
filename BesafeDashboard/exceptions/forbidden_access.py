from exceptions.app_exception import AppException
from exceptions.codes import FORBIDDEN_ACCESS


class ForbiddenAccessException(AppException):
    def __init__(self, message="Forbidden"):
        super().__init__(message, code=FORBIDDEN_ACCESS, status_code=403)
