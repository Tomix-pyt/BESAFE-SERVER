from exceptions.app_exception import AppException
from exceptions.codes import UNAUTHORIZED_ACCESS


class UnauthorizedAccessException(AppException):
    def __init__(self, message="Unauthorized"):
        super().__init__(message, code=UNAUTHORIZED_ACCESS, status_code=401)
