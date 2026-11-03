import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.event_bus import reminder_event_bus

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/reminders")
async def reminder_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        async for event in reminder_event_bus.subscribe():
            if await request.is_disconnected():
                break
            yield f"event: {event.get('type', 'message')}\n"
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
