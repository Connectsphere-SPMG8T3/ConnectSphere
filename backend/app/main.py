from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import BookingConflictError, EquipmentInsufficientError
from app.modules.auth.router import router as auth_router
from app.modules.equipment.router import router as equipment_router
from app.modules.events.router import router as events_router
from app.modules.notifications.router import router as notifications_router
from app.modules.registrations.router import attendee_router as attendee_registrations_router
from app.modules.registrations.router import router as registrations_router
from app.modules.venues.router import bookings_router as venue_bookings_router
from app.modules.venues.router import router as venues_router

settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    description="ConnectSphere API — event planning and venue booking platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*settings.backend_cors_origins, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(equipment_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(notifications_router, prefix=settings.api_v1_prefix)
app.include_router(registrations_router, prefix=settings.api_v1_prefix)
app.include_router(attendee_registrations_router, prefix=settings.api_v1_prefix)
app.include_router(venues_router, prefix=settings.api_v1_prefix)
app.include_router(venue_bookings_router, prefix=settings.api_v1_prefix)


@app.exception_handler(BookingConflictError)
def booking_conflict_handler(request: Request, exc: BookingConflictError) -> JSONResponse:
    """A refused booking request keeps `detail` and adds `conflict` when the
    database named what is in the way (SCRUM-21 AC2)."""
    body = {"detail": exc.detail}
    if exc.conflict is not None:
        body["conflict"] = exc.conflict
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(EquipmentInsufficientError)
def equipment_insufficient_handler(request: Request, exc: EquipmentInsufficientError) -> JSONResponse:
    """A refused reservation says how many are free (SCRUM-24 AC3)."""
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "free_quantity": exc.free_quantity})


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
