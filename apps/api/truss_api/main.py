from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from truss_api.core.storage import ensure_storage_layout
from truss_api.db.schema import initialize_database
from truss_api.health.routes import router as health_router
from truss_api.projects.routes import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_layout()
    initialize_database()
    yield


app = FastAPI(
    title="Truss Agent API",
    version="0.0.0",
    description="Backend local para revisao grafica de projetos estruturais em PDF.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
