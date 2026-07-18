import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import RequestIDMiddleware, register_exception_handlers
from app.core.logging import configure_logging
from app.db import SessionLocal, init_db
from app.routers import (
    actions,
    amendments,
    atlas,
    chat,
    cognitive,
    constitution,
    conversation_summary,
    evaluations,
    features,
    goals,
    human_persona,
    intelligence,
    knowledge,
    library,
    local_intelligence,
    memory,
    memory_candidates,
    mission_control,
    models,
    operational_self_model,
    permissions,
    projects,
    releases,
    schedule,
    self_improvement,
    self_modification,
    system,
    tasks,
    tools,
    usage,
)
from app.services import identity_runtime

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level, structured=settings.app_env == "production")
    problems = settings.validate_startup()
    for problem in problems:
        logger.warning("startup config problem: %s", problem)
    init_db()
    # Part 2B: preload a validated, immutable identity snapshot after schema
    # creation/bootstrap. No network calls occur. A missing/corrupt database
    # identity activates the deterministic local fallback and startup
    # continues in an observable degraded state.
    try:
        with SessionLocal() as db:
            identity_runtime.refresh_active_identity(db, reason="startup")
    except Exception as exc:
        logger.warning("identity runtime preload failed safely: %s", type(exc).__name__)
    logger.info(
        "ECHO backend started — app_env=%s version=%s ollama_enabled=%s",
        settings.app_env,
        settings.app_version,
        settings.ollama_enabled,
    )
    yield
    logger.info("ECHO backend shutting down")


app = FastAPI(title="ECHO — Adaptive Personal AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
register_exception_handlers(app)

app.include_router(chat.router)
app.include_router(atlas.router)
app.include_router(constitution.router)
app.include_router(amendments.router)
app.include_router(models.router)
app.include_router(self_improvement.router)
app.include_router(self_modification.router)
app.include_router(usage.router)
app.include_router(memory_candidates.router)
app.include_router(memory.router)
app.include_router(features.router)
app.include_router(library.router)
app.include_router(schedule.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(mission_control.router)
app.include_router(human_persona.router)
app.include_router(local_intelligence.router)
app.include_router(actions.router)
app.include_router(permissions.router)
app.include_router(evaluations.router)
app.include_router(knowledge.router)
app.include_router(conversation_summary.router)
app.include_router(releases.router)
app.include_router(tools.router)
app.include_router(cognitive.router)
app.include_router(intelligence.router)
app.include_router(operational_self_model.router)
app.include_router(system.router)
app.include_router(goals.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "codename": "Seed", "version": "1.0"}
