import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.core.security import AdminAccessBearer
from app.database.redis import async_redis_client
from app.modules.sites.schema import (
    CreateSiteModel,
    SiteDailyStatsRespModel,
    SiteRespModel,
)
from app.services.sites import SiteService, get_site_service
from app.shared.schema import (
    ServerRespModel,
)

site_router = APIRouter(prefix="/sites", tags=["site"])


@site_router.post(
    "/site/add",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def add_site(
    data: CreateSiteModel,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(AdminAccessBearer()),
):
    site = await site_service.create_site(data=data)

    return ServerRespModel[str](data=str(site.uid), message="Site added to client successfully")


@site_router.get(
    "/sites/{client_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[list[SiteRespModel]],
)
async def get_client_sites_by_uid(
    client_uid: UUID,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(AdminAccessBearer()),
):
    sites = await site_service.get_sites_by_client_uid(client_uid=client_uid)

    return ServerRespModel[list[SiteRespModel]](data=sites, message="client's sites retrieved")


@site_router.get(
    "/sites/{site_uid}/stats/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream live stats for a single site via SSE",
)
async def stream_site_stats(
    site_uid: UUID,
):
    async def event_generator():
        while True:
            try:
                stats = await async_redis_client.get_site_stats_stream(site_uid=str(site_uid))

                if stats:
                    yield f"data: {stats}\n\n".encode("utf-8")
                else:
                    yield f"data: {json.dumps({'status': 'computing', 'site_uid': str(site_uid)})}\n\n".encode("utf-8")

            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'detail': str(e)})}\n\n".encode("utf-8")

            await asyncio.sleep(30)

    return StreamingResponse(
        content=event_generator(),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@site_router.get(
    "/sites/{site_uid}/stats",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[SiteDailyStatsRespModel],
)
async def site_stats(
    site_uid: UUID,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(AdminAccessBearer()),
):
    stats = await async_redis_client.get_site_stats(site_uid=str(site_uid))
    if stats:
        return ServerRespModel[SiteDailyStatsRespModel](
            data=SiteDailyStatsRespModel.model_validate(json.loads(stats)),
            message="Site stat retrieved",
        )
    site_stats = await site_service.compute_site_stats(site_uid=site_uid)
    await async_redis_client.set_site_stats(data=site_stats.model_dump_json(), site_uid=str(site_uid))
    return ServerRespModel[SiteDailyStatsRespModel](data=site_stats, message="Site stat retrieved")
