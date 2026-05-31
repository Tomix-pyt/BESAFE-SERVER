from exceptions.app_exception import AppException
from exceptions.codes import INTERNAL_SERVER_ERROR


class InternalServerErrorException(AppException):
    def __init__(self, message="Internal server error"):
        super().__init__(message, code=INTERNAL_SERVER_ERROR, status_code=500)
