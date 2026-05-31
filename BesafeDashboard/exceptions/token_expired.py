from exceptions.app_exception import AppException
from exceptions.codes import TOKEN_EXPIRED


class TokenExpiredException(AppException):
    def __init__(self, message="Token has expired"):
        super().__init__(message, code=TOKEN_EXPIRED, status_code=401)
