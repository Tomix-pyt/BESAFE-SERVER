from exceptions.app_exception import AppException
from exceptions.codes import TOO_MANY_ATTEMPTS


class TooManyAttemptsException(AppException):
    def __init__(self, message="Too many attempts. Try again later."):
        super().__init__(message, code=TOO_MANY_ATTEMPTS, status_code=429)
