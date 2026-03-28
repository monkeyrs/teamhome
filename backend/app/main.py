from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    security_issues = settings.validate_runtime_security()
    if security_issues:
        joined = " ".join(security_issues)
        raise RuntimeError(f"Unsafe runtime configuration: {joined}")

    app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _enforce_json_utf8(request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.lower().startswith("application/json") and "charset=" not in content_type.lower():
            response.headers["content-type"] = "application/json; charset=UTF-8"
        return response

    app.include_router(api_router)

    return app


app = create_app()
