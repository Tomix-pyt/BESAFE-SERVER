from exceptions.app_exception import AppException
from exceptions.codes import UNPROCESSABLE_ENTITY


class UnprocessableEntityException(AppException):
    def __init__(self, message="Unprocessable entity"):
        super().__init__(message, code=UNPROCESSABLE_ENTITY, status_code=422)
