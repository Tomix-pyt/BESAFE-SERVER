from exceptions.app_exception import AppException
from exceptions.codes import INVALID_ACCESS_CREDENTIALS


class InvalidAccessCredentialsException(AppException):
    def __init__(self, message="Invalid access credentials"):
        super().__init__(message, code=INVALID_ACCESS_CREDENTIALS, status_code=401)
