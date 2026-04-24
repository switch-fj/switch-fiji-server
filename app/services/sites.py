from uuid import UUID

from fastapi import Depends

from app.core.exceptions import BadRequest, NotFound
from app.modules.clients.repository import ClientRepository, get_client_repo
from app.modules.sites.repository import SiteRepository, get_site_repo
from app.modules.sites.schema import CreateSiteModel, UpdateSiteModel


class SiteService:
    def __init__(
        self,
        site_repo: SiteRepository = Depends(get_site_repo),
        client_repo: ClientRepository = Depends(get_client_repo),
    ):
        self.site_repo = site_repo
        self.client_repo = client_repo

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


def get_site_service(
    site_repo: SiteRepository = Depends(get_site_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
):
    return SiteService(site_repo=site_repo, client_repo=client_repo)
