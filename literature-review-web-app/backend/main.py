from __future__ import annotations
import asyncio
import concurrent.futures
import logging
from fastapi import FastAPI
from api.middleware import setup_middleware
from api.routes.literature_review import router as literature_review_router
from api.routes.health import router as health_router
from config.settings import get_settings
from config.logging_config import setup_logging

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(
        title="Mukti Scholar Agent",
        description="Autonomous Literature Review & Research Multi-Agent System",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    setup_middleware(app)

    app.include_router(literature_review_router, prefix="/api", tags=["Literature Review"])
    app.include_router(health_router, prefix="/api", tags=["Health"])

    @app.on_event("startup")
    async def startup_event():
        settings = get_settings()
        setup_logging(settings.LOG_LEVEL)
        # Cap the default thread pool so blocking executor tasks can never
        # starve the event loop of threads it needs to respond to HTTP requests.
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="blocking-io"
        )
        loop.set_default_executor(executor)
        logger.info("Mukti Scholar API starting. version=%s env=%s",
            settings.APP_VERSION, settings.ENVIRONMENT)

    return app

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
