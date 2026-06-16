import asyncio
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.core.config import Config
from app.core.security import AccessTokenBearer, AdminAccessBearer
from app.database.redis import async_redis_client
from app.modules.clients.schema import ClientRespModel, CreateClientModel
from app.modules.contracts.schema import EnergyPortfolioRespModel
from app.modules.sites.schema import CreateSiteModel, SiteRespModel
from app.modules.users.schema import UsersRespModel
from app.services.client import ClientService, get_client_service
from app.services.contract import ContractService, get_contract_service
from app.services.sites import SiteService, get_site_service
from app.services.user import UserService, get_user_service
from app.shared.schema import (
    CursorPaginationModel,
    IdentityTypeEnum,
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

    return ServerRespModel[str](data=str(client.uid), message="client added successfully")


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

    return ServerRespModel[str](data=str(site.uid), message="Site added to client successfully")


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
    _: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
        )
    ),
):
    result = await client_service.get_clients(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

    return ServerRespModel[PaginatedRespModel[ClientRespModel, CursorPaginationModel]](
        data=result, message="clients retrieved"
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

    return ServerRespModel[list[SiteRespModel]](data=sites, message="client's sites retrieved")


@admin_router.get(
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
            "Connection": "keep-alive",
        },
    )


@admin_router.get(
    "/portfolio/stats",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[EnergyPortfolioRespModel],
)
async def get_portfolio_stats(
    contract_service: ContractService = Depends(get_contract_service),
    _: dict = Depends(AdminAccessBearer()),
):
    energy_portfolio = await async_redis_client.get_energy_portfolio()

    if energy_portfolio:
        return ServerRespModel[dict[str, float]](
            data=json.loads(energy_portfolio), message="Energy portfolio retrieved"
        )

    resp = await contract_service.energy_portfolio()
    await async_redis_client.set_energy_portfolio(data=resp.model_dump_json())
    return ServerRespModel[EnergyPortfolioRespModel](data=resp, message="Energy portfolio retrieved")


@admin_router.get(
    "/users",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[UsersRespModel, CursorPaginationModel]],
)
async def users(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=Config.DEFAULT_PAGE_LIMIT),
    next_cursor: Optional[str] = Query(default=None),
    prev_cursor: Optional[str] = Query(default=None),
    user_service: UserService = Depends(get_user_service),
    _: dict = Depends(AdminAccessBearer()),
):
    result = await user_service.get_users(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

    return ServerRespModel[PaginatedRespModel[UsersRespModel, CursorPaginationModel]](
        data=result, message="users retrieved"
    )
