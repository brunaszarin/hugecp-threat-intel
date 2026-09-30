from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, origins, overview
from app.core.config import settings
from app.db.pool import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = create_pool()
    pool.open()
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(overview.router, prefix="/api")
    app.include_router(origins.router, prefix="/api")
    return app


app = create_app()
