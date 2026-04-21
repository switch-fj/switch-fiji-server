import asyncio
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import Config
from app.core.security import AdminAccessBearer
from app.database.redis import async_redis_client
from app.modules.clients.schema import ClientRespModel, CreateClientModel
from app.modules.settings.schema import (
    ContractSettingsModel,
    UpdateContractSettingsModel,
)
from app.modules.sites.schema import CreateSiteModel, SiteRespModel
from app.services.client import ClientService, get_client_service
from app.services.settings import SettingsService, get_settings_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import (
    CursorPaginationModel,
    PaginatedRespModel,
    ServerRespModel,
)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post(
    "/client/add",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def add_client(
    data: CreateClientModel,
    client_service: ClientService = Depends(get_client_service),
    token_payload: dict = Depends(AdminAccessBearer()),
):
    client = await client_service.register_client(data=data, token_payload=token_payload)

    return JSONResponse(
        content=ServerRespModel[str](data=str(client.uid), message="client added successfully").model_dump()
    )


@admin_router.post(
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

    return JSONResponse(
        content=ServerRespModel[str](data=str(site.uid), message="Site added to client successfully").model_dump()
    )


@admin_router.get(
    "/clients",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[ClientRespModel, CursorPaginationModel]],
)
async def get_clients(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=Config.DEFAULT_PAGE_LIMIT),
    next_cursor: Optional[str] = Query(default=None),
    prev_cursor: Optional[str] = Query(default=None),
    client_service: ClientService = Depends(get_client_service),
    _: dict = Depends(AdminAccessBearer()),
):
    result = await client_service.get_clients(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

    return JSONResponse(
        content=ServerRespModel[PaginatedRespModel[ClientRespModel, CursorPaginationModel]](
            data=result, message="clients retrieved"
        ).model_dump()
    )


@admin_router.get(
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

    return JSONResponse(
        content=ServerRespModel[list[SiteRespModel]](data=sites, message="client's sites retrieved").model_dump()
    )


@admin_router.get(
    "/sites/{site_uid}/stats/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream live stats for a single site via SSE",
)
async def stream_site_stats(
    site_uid: UUID,
    _: dict = Depends(AdminAccessBearer()),
):
    async def event_generator():
        while True:
            try:
                stats = await async_redis_client.get_site_stats(site_uid=str(site_uid))

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
            "Connection": "keep-alive",
        },
    )


@admin_router.get(
    "/contracts-settings",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[ContractSettingsModel],
)
async def get_contracts_general_settings(
    contract_settings_service: SettingsService = Depends(get_settings_service),
    _: dict = Depends(AdminAccessBearer()),
):
    contract_settings = await contract_settings_service.get_contract_general_settings()

    return JSONResponse(
        content=ServerRespModel[list[ContractSettingsModel]](
            data=contract_settings, message="contract general settings retrieved"
        ).model_dump()
    )


@admin_router.patch(
    "/contracts-settings",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ServerRespModel[bool],
)
async def update_contracts_generat_settings(
    data: UpdateContractSettingsModel,
    contract_settings_service: SettingsService = Depends(get_settings_service),
    token_payload: dict = Depends(AdminAccessBearer()),
):
    resp = await contract_settings_service.update_contract_general_settings(data=data, token_payload=token_payload)

    return JSONResponse(
        content=ServerRespModel[bool](data=resp, message="contract general settings updated").model_dump()
    )
