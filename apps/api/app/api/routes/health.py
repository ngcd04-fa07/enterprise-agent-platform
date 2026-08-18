from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.session import ping_database

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    environment: str
    database: Literal["ok", "unreachable"]


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    database_reachable: Annotated[bool, Depends(ping_database)],
) -> HealthResponse:
    return HealthResponse(
        status="ok" if database_reachable else "degraded",
        environment=settings.environment,
        database="ok" if database_reachable else "unreachable",
    )
