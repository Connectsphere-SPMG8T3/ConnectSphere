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


class SupabasePasswordRejectedError(HTTPException):
    """Supabase's own password policy refused a password our rule accepted.

    Shaped like a validation error on `password`, so the SPA shows GoTrue's
    reason under the field as it does for the API's own checks (SCRUM-80).
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", "password"], "msg": message, "type": "weak_password"}],
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


class BookingConflictError(HTTPException):
    """409 for a booking request refused by what is already at the venue
    (SCRUM-21 AC2). `conflict` names it and is sent beside `detail`; see the
    handler in `app.main`."""

    def __init__(self, detail: str, conflict: dict | None) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
        self.conflict = conflict


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
            detail=f"Cannot {action.replace('_', ' ')} an event that is {current_status.replace('_', ' ')}",
        )


class VenueConflictError(HTTPException):
    """Lost an optimistic-concurrency race on a venue edit (DB-5, SCRUM-63)."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This venue was updated by someone else. Reload.",
        )


class BookingNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")


class BookingDecisionConflictError(HTTPException):
    """The booking is no longer a live hold, so it can't be decided (SCRUM-38 AC9, AC10)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class BookingDecisionTextError(HTTPException):
    """The database refused the decision's text, which the API had already
    validated, so this is a backstop (SCRUM-38 AC2, AC3)."""

    def __init__(self, field: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", field], "msg": "Must be 1 to 1000 characters.", "type": "value_error"}],
        )


class VenueAlreadyInactiveError(HTTPException):
    """SCRUM-64: deactivating a venue that is already inactive."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="This venue is already inactive.")


class VenueBlockInvalidError(HTTPException):
    """SCRUM-51 AC1: a block period the database refused under its lock, such
    as an end that passed between the request's validation and the save."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class VenueAlreadyActiveError(HTTPException):
    """SCRUM-64: reactivating a venue that is already active."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="This venue is already active.")


class NotAssignedCoordinatorError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the event's assigned coordinator can do this.",
        )


class EventNotInLeadScopeError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This event is managed by another Event Coordinator Lead.",
        )


class CoordinatorNotEligibleError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That person is not an Event Coordinator.",
        )


class EquipmentRequestNotAllowedError(HTTPException):
    """The event's status doesn't accept equipment requests (SCRUM-45, QA-22)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class EquipmentNotInCatalogueError(HTTPException):
    """A requested item is missing from the catalogue or retired (SCRUM-45)."""

    def __init__(self, indexes: list[int] | None = None) -> None:
        # No indexes when the database refused the batch: it doesn't say which item.
        locs = [["body", "items", index, "equipment_id"] for index in indexes] if indexes else [["body", "items"]]
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {"loc": loc, "msg": "This item is not in the equipment catalogue.", "type": "not_in_catalogue"}
                for loc in locs
            ],
        )


class UnknownEventArrangementError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                         detail="Unknown booking or equipment line for this event")


class EventServiceUnavailableError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                         detail="The event service is temporarily unavailable. Please try again.")
