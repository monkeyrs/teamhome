from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import engine


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    if settings.DB_AUTO_CREATE:
        from app.core.database import Base
        from app import models  # noqa: F401

        @app.on_event("startup")
        def _create_tables() -> None:
            Base.metadata.create_all(bind=engine)

    return app


app = create_app()
