from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_commands import router as commands_router
from app.api.routes_events import router as events_router
from app.api.routes_items import router as items_router
from app.config import get_settings
from app.database import init_db
from app.services.scheduler import ReminderScheduler

settings = get_settings()
reminder_scheduler = ReminderScheduler(settings.reminder_poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    reminder_scheduler.start()
    try:
        yield
    finally:
        reminder_scheduler.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(commands_router)
app.include_router(items_router)
app.include_router(events_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
