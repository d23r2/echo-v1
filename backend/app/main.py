from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
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
    human_persona,
    knowledge,
    library,
    local_intelligence,
    memory_candidates,
    mission_control,
    models,
    permissions,
    projects,
    releases,
    schedule,
    self_improvement,
    tasks,
    tools,
    usage,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ECHO — Adaptive Personal AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(atlas.router)
app.include_router(constitution.router)
app.include_router(amendments.router)
app.include_router(models.router)
app.include_router(self_improvement.router)
app.include_router(usage.router)
app.include_router(memory_candidates.router)
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


@app.get("/api/health")
def health():
    return {"status": "ok", "codename": "Seed", "version": "1.0"}
