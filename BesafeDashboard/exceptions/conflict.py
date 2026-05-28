from exceptions.app_exception import AppException
from exceptions.codes import CONFLICT


class ConflictException(AppException):
    def __init__(self, message="Resource already exists"):
        super().__init__(message, code=CONFLICT, status_code=409)
