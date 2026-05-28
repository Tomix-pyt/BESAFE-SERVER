from exceptions.app_exception import AppException
from exceptions.codes import BAD_REQUEST


class BadRequestException(AppException):
    def __init__(self, message="Bad request"):
        super().__init__(message, code=BAD_REQUEST, status_code=400)
