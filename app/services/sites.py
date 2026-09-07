import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends

from app.api.v1.engineer.schema import EngineeringDashboardSiteModel
from app.core.exceptions import BadRequest, NotFound
from app.database.redis import async_redis_client
from app.jobs.on_demand.schedulers.site_energy_usage import (
    schedule_site_energy_usage_on_demand,
)
from app.modules.clients.repository import ClientRepository, get_client_repo
from app.modules.mppt_function_check.schema import DateCheckQuery
from app.modules.settings.schema import SiteFlowGraphStreamResp
from app.modules.sites.repository import (
    SiteEnergyUsageRepository,
    SiteRepository,
    get_site_energy_usage_repo,
    get_site_repo,
)
from app.modules.sites.schema import (
    CreateSiteModel,
    SiteEnergyUsageModel,
    UpdateSiteModel,
)
from app.shared.constants import Constants
from app.utils.date import is_future_date


class SiteService:
    def __init__(
        self,
        site_repo: SiteRepository = Depends(get_site_repo),
        site_energy_usage_repo: SiteEnergyUsageRepository = Depends(get_site_energy_usage_repo),
        client_repo: ClientRepository = Depends(get_client_repo),
    ):
        self.site_repo = site_repo
        self.client_repo = client_repo
        self.site_energy_usage_repo = site_energy_usage_repo

    async def get_sites_by_client_uid(self, client_uid: UUID):
        sites_by_client = await self.site_repo.get_sites_by_client_uid(client_uid=client_uid)

        return sites_by_client

    async def get_detailed_sites_by_client_uid(self, client_uid: UUID):
        client = await self.client_repo.get_client_by_uid(client_uid=client_uid)

        if not client:
            raise NotFound("Client with uid not found")

        sites_by_client = await self.site_repo.get_detailed_sites_by_client_uid(client_uid=client_uid)
        return sites_by_client

    async def create_site(self, data: CreateSiteModel):
        new_site = await self.site_repo.create_site(data=data)
        if not new_site:
            raise BadRequest("Unable to add site to client.")

        return new_site

    async def update_site(self, site_uid: UUID, data: UpdateSiteModel):
        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)
        if not site:
            raise NotFound("Site not found!")

        updated_site = await self.site_repo.update_site(site=site, data=data)
        return updated_site

    async def compute_site_stats(self, site_uid: UUID):
        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)
        if not site:
            raise NotFound("Site not found.")

        stats = await self.site_repo.compute_site_stats(site_uid=site_uid)
        if not stats:
            raise NotFound("No active contract found for this site.")

        return stats

    async def engineers_get_site_details_by_client_uid(self, client_uid: UUID):
        sites = await self.site_repo.engineers_get_details_by_client_uid(client_uid=client_uid)

        return [EngineeringDashboardSiteModel.model_validate(site) for site in sites]

    async def site_energy_usage(self, site_uid: UUID, params: DateCheckQuery):
        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)
        if site is None:
            raise NotFound("site not found!")

        tz = site.tz or site.contract.timezone
        date_at = datetime.fromtimestamp(params.date_at, tz=ZoneInfo(tz)).date()

        if is_future_date(date_at, tz):
            raise BadRequest("Only current and past date allowed.")

        cache_key = Constants.SITE_ENERGY_USAGE.replace("site_uid", str(site_uid)).replace(
            "date_at", date_at.isoformat()
        )
        cached = await async_redis_client.client.get(cache_key)
        if cached:
            SiteEnergyUsageModel.model_validate(json.loads(cached))

        site_energy_usage = await self.site_energy_usage_repo.get_usage(site_uid=site_uid, date_at=date_at)
        if site_energy_usage is None:
            site_energy_usage = await self.site_energy_usage_repo.create(site_uid=site_uid, date_at=date_at)

        lock_key = Constants.SITE_ENERGY_USAGE_LOCK.replace("site_uid", str(site_uid)).replace(
            "date_at", date_at.isoformat()
        )
        lock_acquired = await async_redis_client.client.set(lock_key, "1", nx=True, ex=300)

        if lock_acquired:
            schedule_site_energy_usage_on_demand.delay(site_uid, date_at)

        return SiteEnergyUsageModel.model_validate(site_energy_usage)

    async def flow_graph_generator(self, site_uid: UUID):
        while True:
            try:
                now = datetime.now(tz=timezone.utc)
                flow_graph_site_key = Constants.SITE_FLOW_GRAPH.replace("site_uid", str(site_uid))
                result = await async_redis_client.client.get(flow_graph_site_key)

                if result is None:
                    flow_graph_data = SiteFlowGraphStreamResp(
                        status="No data",
                        site_uid=site_uid,
                    )
                    yield f"data: {flow_graph_data.model_dump_json()}\n\n".encode("utf-8")
                    await asyncio.sleep(60)
                    continue

                payload = json.loads(result)

                if payload["graph"]:
                    last_seen = datetime.strptime(payload["computed_at"], "%Y-%m-%dT%H:%M:%S.%f%z")
                    age = now - last_seen
                    if age > timedelta(minutes=10):
                        flow_graph_data = SiteFlowGraphStreamResp(
                            status="Stale data",
                            site_uid=site_uid,
                            graph=payload["graph"],
                            last_seen=last_seen,
                        )
                        yield f"data: {flow_graph_data.model_dump_json()}\n\n".encode("utf-8")
                    else:
                        flow_graph_data = SiteFlowGraphStreamResp(
                            status="Live data",
                            site_uid=site_uid,
                            graph=payload["graph"],
                        )
                        yield f"data: {flow_graph_data.model_dump_json()}\n\n".encode("utf-8")
                else:
                    flow_graph_data = SiteFlowGraphStreamResp(
                        status="No data",
                        site_uid=site_uid,
                    )
                    yield f"data: {flow_graph_data.model_dump_json()}\n\n".encode("utf-8")

            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'detail': str(e)})}\n\n".encode("utf-8")

            await asyncio.sleep(60)

    async def sites_health_summary(self):
        result = await self.site_repo.site_health_counts()

        return result


def get_site_service(
    site_repo: SiteRepository = Depends(get_site_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    site_energy_usage_repo: SiteEnergyUsageRepository = Depends(get_site_energy_usage_repo),
):
    return SiteService(
        site_repo=site_repo,
        client_repo=client_repo,
        site_energy_usage_repo=site_energy_usage_repo,
    )
