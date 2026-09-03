from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from truss_api.audit.routes import router as audit_router
from truss_api.calibration.routes import router as calibration_router
from truss_api.comparisons.routes import router as comparisons_router
from truss_api.assistant.routes import router as assistant_router
from truss_api.batch.routes import router as batch_router
from truss_api.core.storage import ensure_storage_layout
from truss_api.core.settings import get_settings
from truss_api.db.schema import initialize_database
from truss_api.documents.routes import router as documents_router
from truss_api.health.routes import router as health_router
from truss_api.learning.routes import router as learning_router
from truss_api.projects.routes import router as projects_router
from truss_api.preferences.routes import router as preferences_router
from truss_api.recovery.errors import TrussError
from truss_api.recovery.routes import router as recovery_router
from truss_api.recovery.repository import mark_running_as_interrupted
from truss_api.sheetmap.routes import router as sheetmap_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings_provider = app.dependency_overrides.get(get_settings, get_settings)
    settings = settings_provider()
    ensure_storage_layout(settings)
    initialize_database(settings)
    mark_running_as_interrupted(settings)
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
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TrussError)
async def truss_error_handler(_request: Request, error: TrussError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.public.as_detail()},
    )

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(sheetmap_router)
app.include_router(audit_router)
app.include_router(assistant_router)
app.include_router(batch_router)
app.include_router(preferences_router)
app.include_router(learning_router)
app.include_router(calibration_router)
app.include_router(comparisons_router)
app.include_router(recovery_router)
