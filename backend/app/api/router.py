from fastapi import APIRouter

from app.api import auth, finance, schedules, teams

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])
