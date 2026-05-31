from exceptions.codes import APP_EXCEPTION


class AppException(Exception):
    def __init__(self, message="An error occurred", code=APP_EXCEPTION, status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
