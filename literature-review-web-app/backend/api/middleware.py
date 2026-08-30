from __future__ import annotations
import logging, time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config.settings import get_settings
from utils.correlation import CorrelationIdMiddleware, get_correlation_id
from models.api import ErrorResponse

logger = logging.getLogger(__name__)

def setup_middleware(app: FastAPI) -> None:
    settings = get_settings()

    # CORS — allow all origins in development, restrict in production
    cors_origins = settings.CORS_ORIGINS
    if settings.ENVIRONMENT == "development":
        cors_origins = ["*"]

    app.add_middleware(CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"])

    # Correlation ID
    app.add_middleware(CorrelationIdMiddleware)

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        logger.info("request method=%s path=%s status=%d duration_ms=%.1f",
            request.method, request.url.path, response.status_code, duration * 1000)
        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        cid = get_correlation_id()
        logger.error("Unhandled exception correlation_id=%s: %s", cid, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=str(exc), correlation_id=cid, status_code=500).model_dump()
        )
