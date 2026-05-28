from exceptions.app_exception import AppException
from exceptions.codes import AUTHENTICATION_TOKEN


class AuthenticationTokenException(AppException):
    def __init__(self, message="Invalid or expired authentication token"):
        super().__init__(message, code=AUTHENTICATION_TOKEN, status_code=401)
