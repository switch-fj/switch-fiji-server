from fastapi import APIRouter, status

from app.services.misc import MiscService
from app.shared.schema import (
    ServerRespModel,
)

misc_router = APIRouter(prefix="/misc", tags=["misc"])


@misc_router.get(
    "/tz",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[dict[str, list[str]]],
)
async def get_available_timezones():
    tz = await MiscService.get_cities_by_regions()
    return ServerRespModel[dict[str, list[str]]](data=tz, message="regions retrieved")
