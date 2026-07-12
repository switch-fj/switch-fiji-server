import asyncio
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.core.security import AdminAccessBearer, EngineerAccessBearer
from app.database.redis import async_redis_client
from app.modules.panel_references.schema import (
    CreatePanelRefModel,
    PanelRefsModel,
    UpdatePanelRefModel,
)
from app.modules.pv_degradation.schema import (
    PVDegradationModel,
    Year1DegradationInputModel,
)
from app.modules.pv_summary.schema import PVSModel, SitePVSItemModel, UpdatePVSItemModel
from app.modules.sites.schema import (
    CreateSiteModel,
    SiteDailyStatsRespModel,
    SiteRespModel,
)
from app.modules.string_wiring.schema import (
    StringsWiringInputModel,
    StringWiringRespModel,
)
from app.services.site_configs import SiteConfigService, get_site_configs_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import (
    ServerRespModel,
)

site_router = APIRouter(prefix="", tags=["site"])


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


@site_router.get(
    "/sites/{site_uid}/panels",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[list[PanelRefsModel]],
)
async def get_site_panels(
    site_uid: UUID,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
):
    site_panels = await site_config_service.get_site_panels(site_uid=site_uid)

    return ServerRespModel[list[PanelRefsModel]](data=site_panels, message="Site panels retrieved")


@site_router.post(
    "/sites/{site_uid}/panels",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def create_site_panels(
    site_uid: UUID,
    payload: CreatePanelRefModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    await site_config_service.add_panel_refs(site_uid=site_uid, user_uid=token_user_uid, payload=payload)

    return ServerRespModel[bool](data=True, message="Site panel types created")


@site_router.put(
    "/sites/{site_uid}/panels",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def edit_site_panels(
    site_uid: UUID,
    payload: UpdatePanelRefModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    await site_config_service.edit_panel_ref(site_uid=site_uid, user_uid=token_user_uid, payload=payload)

    return ServerRespModel[bool](data=True, message="Site panel types updated")


@site_router.get(
    "/sites/{site_uid}/pvs",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVSModel]],
)
async def get_site_pvs(
    site_uid: UUID,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
):
    site_pvs = await site_config_service.get_site_pvs(site_uid=site_uid)

    return ServerRespModel[Optional[PVSModel]](
        data=PVSModel.model_validate(site_pvs) if site_pvs else None,
        message="Site photovoltaic summary retrieved",
    )


@site_router.post(
    "/sites/{site_uid}/pvs",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def create_site_pvs(
    site_uid: UUID,
    payload: SitePVSItemModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    await site_config_service.create_pvs(site_uid=site_uid, user_uid=token_user_uid, payload=payload)

    return ServerRespModel[bool](data=True, message="Site photovoltaic summary created")


@site_router.put(
    "/sites/{site_uid}/pvs",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def edit_site_pvs(
    site_uid: UUID,
    payload: UpdatePVSItemModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    await site_config_service.edit_pvs(site_uid=site_uid, user_uid=token_user_uid, payload=payload)

    return ServerRespModel[bool](data=True, message="Site photovoltaic summary updated")


@site_router.post(
    "/sites/{site_uid}/degradation",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVDegradationModel]],
)
async def create_year_one_degradation(
    site_uid: UUID,
    payload: Year1DegradationInputModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    result = await site_config_service.create_or_update_year_one_degradation(
        site_uid=site_uid, user_uid=token_user_uid, payload=payload
    )

    return ServerRespModel[Optional[PVDegradationModel]](
        data=PVDegradationModel.model_validate(result) if result else None,
        message=("Site degradation created!" if result else "Site PV Summary needs to be created first!"),
    )


@site_router.put(
    "/sites/{site_uid}/degradation",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVDegradationModel]],
)
async def update_year_one_degradation(
    site_uid: UUID,
    payload: Year1DegradationInputModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    result = await site_config_service.create_or_update_year_one_degradation(
        site_uid=site_uid, user_uid=token_user_uid, payload=payload
    )

    return ServerRespModel[Optional[PVDegradationModel]](
        data=PVDegradationModel.model_validate(result) if result else None,
        message="Site degradation updated!",
    )


@site_router.get(
    "/sites/{site_uid}/degradation",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVDegradationModel]],
)
async def get_site_degradation(
    site_uid: UUID,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    result = await site_config_service.get_degradation_by_site(site_uid=site_uid)

    return ServerRespModel[Optional[PVDegradationModel]](
        data=PVDegradationModel.model_validate(result) if result else None,
        message="Site degradation retrieved!",
    )


@site_router.post(
    "/sites/{site_uid}/string-wiring",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[StringWiringRespModel],
)
async def configure_string_wiring(
    site_uid: UUID,
    payload: StringsWiringInputModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")
    result = await site_config_service.create_string_wiring(site_uid=site_uid, user_uid=token_user_uid, payload=payload)

    return ServerRespModel[StringWiringRespModel](
        data=StringWiringRespModel.model_validate(result.model_dump()),
        message="Site string summary configured!",
    )


@site_router.put(
    "/sites/{site_uid}/string-wiring/{str_wiring_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVDegradationModel]],
)
async def update_string_writing(
    site_uid: UUID,
    str_wiring_uid: UUID,
    payload: StringsWiringInputModel,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    token_payload: dict = Depends(EngineerAccessBearer()),
):
    token_user = token_payload.get("user")
    token_user_uid = token_user.get("uid")

    result = await site_config_service.update_string_wiring(
        site_uid=site_uid,
        user_uid=token_user_uid,
        str_wiring_uid=str_wiring_uid,
        payload=payload,
    )

    return ServerRespModel[StringWiringRespModel](
        data=StringWiringRespModel.model_validate(result.model_dump()),
        message="Site string summary configured!",
    )


@site_router.get(
    "/sites/{site_uid}/string-wiring",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[Optional[PVDegradationModel]],
)
async def get_site_wiring(
    site_uid: UUID,
    site_config_service: SiteConfigService = Depends(get_site_configs_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    result = await site_config_service.get_str_wiring(site_uid=site_uid)

    return ServerRespModel[Optional[PVDegradationModel]](
        data=PVDegradationModel.model_validate(result) if result else None,
        message="Site string wiring retrieved!",
    )
