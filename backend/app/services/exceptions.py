"""Domain errors raised by services and mapped to HTTP responses in app.main."""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class BusinessRuleError(ServiceError):
    """Request is well-formed but violates a business rule."""

    status_code = 422


class ForbiddenError(ServiceError):
    """The caller is not allowed to perform this action (e.g. not an authorized approver)."""

    status_code = 403
