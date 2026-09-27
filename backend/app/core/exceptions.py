from fastapi import HTTPException, status


class InvalidCredentialsError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidOrExpiredTokenError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthServiceUnavailableError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication service is temporarily unavailable. Please try again.",
        )


class EmailAlreadyRegisteredError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )


class ProfileNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found.",
        )


class VenueNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found.",
        )


class InsufficientRoleError(HTTPException):
    def __init__(self, allowed_roles: list[str]) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires one of the following roles: {', '.join(allowed_roles)}.",
        )


class RoleNotAssignedError(HTTPException):
    def __init__(self, role: str) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not hold the '{role}' role.",
        )


class EventTransitionError(HTTPException):
    """A lifecycle action the event's current status does not allow (LC-R1)."""

    def __init__(self, action: str, current_status: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} an event that is {current_status.replace('_', ' ')}",
        )


class NotAssignedCoordinatorError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the event's assigned coordinator can do this.",
        )
