from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import amendments, atlas, chat, constitution, models, self_improvement

settings = get_settings()

app = FastAPI(title="God Tear AI Brain — Echo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(chat.router)
app.include_router(atlas.router)
app.include_router(constitution.router)
app.include_router(amendments.router)
app.include_router(models.router)
app.include_router(self_improvement.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "codename": "Seed", "version": "1.0"}
