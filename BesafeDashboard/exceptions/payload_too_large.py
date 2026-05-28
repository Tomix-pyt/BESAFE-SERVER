from exceptions.app_exception import AppException
from exceptions.codes import PAYLOAD_TOO_LARGE


class PayloadTooLargeException(AppException):
    def __init__(self, message="Payload too large"):
        super().__init__(message, code=PAYLOAD_TOO_LARGE, status_code=413)
