from exceptions.app_exception import AppException
from exceptions.codes import MISSING_PARAMETER


class MissingParameterException(AppException):
    def __init__(self, message="Missing required parameter"):
        super().__init__(message, code=MISSING_PARAMETER, status_code=400)
