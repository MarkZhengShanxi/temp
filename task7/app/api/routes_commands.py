from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.schemas import CommandRequest, CommandResponse
from app.services.command_service import CommandService

router = APIRouter(prefix="/api", tags=["commands"])


def get_command_service() -> CommandService:
    return CommandService()


@router.post("/commands", response_model=CommandResponse)
def handle_command(
    request: CommandRequest,
    session: Session = Depends(get_session),
    service: CommandService = Depends(get_command_service),
) -> CommandResponse:
    parsed, result = service.handle(session, request)
    return CommandResponse(parsed=parsed, result=result)
