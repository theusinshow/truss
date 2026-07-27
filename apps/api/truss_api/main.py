from contextlib import asynccontextmanager

from fastapi import FastAPI

from truss_api.core.storage import ensure_storage_layout
from truss_api.health.routes import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_layout()
    yield


app = FastAPI(
    title="Truss Agent API",
    version="0.0.0",
    description="Backend local para revisao grafica de projetos estruturais em PDF.",
    lifespan=lifespan,
)

app.include_router(health_router)
