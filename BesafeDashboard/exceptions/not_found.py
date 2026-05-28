from exceptions.app_exception import AppException
from exceptions.codes import NOT_FOUND


class NotFoundException(AppException):
    def __init__(self, message="Resource not found"):
        super().__init__(message, code=NOT_FOUND, status_code=404)
