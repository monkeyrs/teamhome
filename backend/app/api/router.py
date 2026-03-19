from fastapi import APIRouter

from app.api import assistant, auth, changes, finance, schedules, teams
from app.api import places

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])
api_router.include_router(places.router, prefix="/places", tags=["places"])
api_router.include_router(changes.router, prefix="/changes", tags=["changes"])
