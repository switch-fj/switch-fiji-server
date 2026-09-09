import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends

from app.core.auth import Authentication
from app.core.config import Config
from app.core.exceptions import (
    BadRequest,
    InvalidToken,
    NotFound,
    UserEmailExists,
    WrongCredentials,
)
from app.core.logger import setup_logger
from app.database.redis import async_redis_client
from app.jobs.on_demand.schedulers.auth import (
    send_email_verification_task,
    send_verify_login_task,
)
from app.modules.clients.model import Client
from app.modules.clients.repository import ClientRepository, get_client_repo
from app.modules.clients.schema import (
    ClientPortfolioRespModel,
    CreateClientModel,
    UpdateClientModel,
)
from app.modules.devices.device_repository import DeviceRepository, get_device_repo
from app.modules.invoices.repository import InvoiceRepository, get_invoice_repo
from app.modules.settings.repository import SettingsRepository, get_settings_repo
from app.modules.sites.repository import SiteRepository, get_site_repo
from app.modules.sites.schema import SiteRespWithMetrics, SiteSummaryMetrics
from app.services.portfolio_metrics import PortfolioMetricsService
from app.shared.constants import Constants
from app.shared.schema import (
    AuthType,
    CursorPaginationModel,
    EmailModel,
    IdentityLoginModel,
    PaginatedRespModel,
    TokenModel,
    UserResponseModel,
    VerifyLoginModel,
)
from app.utils import generate_token_identity_model, get_request_origin

logger = setup_logger(__name__)


class ClientService:
    def __init__(
        self,
        client_repo: ClientRepository,
        site_repo: SiteRepository,
        invoice_repo: InvoiceRepository,
        settings_repo: SettingsRepository,
        device_repo: DeviceRepository,
    ):
        self.client_repo = client_repo
        self.site_repo = site_repo
        self.invoice_repo = invoice_repo
        self.settings_repo = settings_repo
        self.device_repo = device_repo
        self.portfolio_metrics = PortfolioMetricsService(invoice_repo=invoice_repo, settings_repo=settings_repo)

    async def _initiate_verify_login_task(self, email: str):
        text = await Authentication.generate_passcode(email=email)

        send_verify_login_task.delay(
            email=email,
            text=text,
        )

    async def _initiate_acct_verification_task(self, email: str):
        token_payload = {"email": email}
        email_token = await Authentication.create_url_safe_token(data=token_payload)
        verification_url = f"{get_request_origin()}/auth/verify?token={email_token}"

        send_email_verification_task.delay(
            email=email,
            verification_url=verification_url,
        )

    async def get_current_client(self, token_payload: dict):
        return UserResponseModel.model_validate(token_payload["user"])

    async def login(self, data: IdentityLoginModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise WrongCredentials()

        auth_type = AuthType.PWD.value if client.password_hash else AuthType.OTP.value

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not data.password:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not await Authentication.verify_password(data.password, client.password_hash):
            raise WrongCredentials()

        token_identity_model = generate_token_identity_model(client)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=client.is_email_verified,
                auth_type=auth_type,
            ),
        )

    async def register_client(self, token_payload: dict, data: CreateClientModel):
        token_user = token_payload.get("user")
        token_user_uid = token_user.get("uid")
        client = await self.client_repo.get_client_by_mail(email=data.client_email)

        if client:
            raise UserEmailExists()

        new_client = await self.client_repo.create_client(user_uid=token_user_uid, data=data)
        return new_client

    async def update_client(self, client_uid: UUID, data: UpdateClientModel):
        client = await self.client_repo.get_client_by_uid(client_uid=client_uid)
        if not client:
            raise NotFound("Client not found!")

        updated_client = await self.client_repo.update_client(client=client, data=data)
        return updated_client

    async def request_login(self, data: EmailModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound()

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await self._initiate_verify_login_task(email=client.client_email)
        return True

    async def verify_login_code(self, data: VerifyLoginModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound()

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await Authentication.decode_passcode(otp=data.otp, email=data.email)
        token_identity_model = generate_token_identity_model(client)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=client.is_email_verified,
                auth_type=AuthType.OTP.value,
            ),
        )

    async def verify_account(self, token: str):
        try:
            payload = await Authentication.decode_url_safe_token(token=token)
            client_email = payload.get("email")

            if not client_email:
                raise InvalidToken("Invalid token.")

            client = await self.client_repo.get_client_by_mail(client_email)

            if not client:
                raise NotFound("User doesn't exist.")

            if client.is_email_verified:
                return "Account already verified."

            await self.client_repo.verify_email(client=client)
            await async_redis_client.add_to_blocklist(token)

            return "Account verified successfully."

        except Exception as e:
            logger.error(f"Error verifying account: {e}")
            raise

    async def send_verification_email(self, data: EmailModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound("client doesn't exist.")

        if client.is_email_verified:
            return "Account already verified."

        if await async_redis_client.client.exists(f"verify:{client.client_email}") > 0:
            return "A verification email was recently sent. Check your inbox."

        await self._initiate_acct_verification_task(email=client.client_email)

        return "Verification email sent. Check your inbox"

    async def get_clients_v2(
        self,
        q: Optional[str],
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        if next_cursor and prev_cursor:
            raise BadRequest("Provide either next_cursor or prev_cursor, not both")

        result = await self.client_repo.get_clients(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

        now = datetime.now(timezone.utc)

        clients: list[Client] = result.items
        portfolio_items = []
        for client in clients:
            site_metrics = []
            contracts = []

            for site in client.sites:
                logger.info(site.contract)
                contract = site.contract
                if contract is None or contract.details is None:
                    continue
                contracts.append(contract)
                computed_site_metrics = await self.portfolio_metrics.compute_site_metrics(
                    site=site, contract=contract, devices=site.devices, now=now
                )
                site_metrics.append(computed_site_metrics)

            client_metrics = await self.portfolio_metrics.aggregate_client_metrics(
                site_metrics=site_metrics, contracts=contracts
            )
            portfolio_items.append(
                ClientPortfolioRespModel(
                    client=client,
                    sites_count=len(client.sites),
                    devices_count=sum(len(s.devices) for s in client.sites),
                    metrics=client_metrics,
                )
            )

        return PaginatedRespModel.model_validate(
            {
                "items": portfolio_items,
                "pagination": result.pagination,
            }
        )

    async def get_clients(
        self,
        q: Optional[str],
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        if next_cursor and prev_cursor:
            raise BadRequest("Provide either next_cursor or prev_cursor, not both")

        result = await self.client_repo.get_clients(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

        return result

    async def get_sites(
        self,
        q: Optional[str],
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        if next_cursor and prev_cursor:
            raise BadRequest("Provide either next_cursor or prev_cursor, not both")

        result = await self.site_repo.get_sites(
            q=q,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            portfolio_metrics=self.portfolio_metrics,
        )

        return result

    async def get_client_sites(self, client_uid: UUID):
        resp = await self.site_repo.get_sites_by_client_uid_v2(
            client_uid=client_uid, portfolio_metrics=self.portfolio_metrics
        )

        if resp is None:
            raise NotFound("Client not found!")

        return resp

    async def get_client_sites_summary(self, client_uid: UUID) -> SiteSummaryMetrics:
        cache_key = Constants.CLIENT_SITE_SUMMARY.replace(":client_uid", str(client_uid))
        cached = await async_redis_client.client.get(cache_key)

        if cached:
            return SiteSummaryMetrics.model_validate(json.loads(cached))

        resp = await self.site_repo.get_sites_by_client_uid_v2(
            client_uid=client_uid, portfolio_metrics=self.portfolio_metrics
        )

        if resp is None:
            raise NotFound("Client not found!")

        site_health = await self.site_repo.site_health_by_client_uid(client_uid=client_uid)

        summary = self.portfolio_metrics.site_summary_metrics(
            site_health=site_health,
            site_metrics=[s.metrics for s in resp],
        )

        await async_redis_client.client.set(
            cache_key,
            summary.model_dump_json(),
            ex=3600,
        )

        return summary

    async def get_sites_summary(self) -> SiteSummaryMetrics:
        cache_key = Constants.SITES_SUMMARY
        cached = await async_redis_client.client.get(cache_key)

        if cached:
            return SiteSummaryMetrics.model_validate(json.loads(cached))

        resp: PaginatedRespModel[SiteRespWithMetrics, CursorPaginationModel] = await self.site_repo.get_sites(
            _is_all_sites=True, portfolio_metrics=self.portfolio_metrics
        )

        if resp is None:
            raise NotFound("Client not found!")

        site_health = await self.site_repo.site_health_counts()

        summary = self.portfolio_metrics.site_summary_metrics(
            site_health=site_health,
            site_metrics=[s.metrics for s in resp.items],
        )

        await async_redis_client.client.set(
            cache_key,
            summary.model_dump_json(),
            ex=3600,
        )

        return summary

    async def engineers_get_clients(
        self,
        q: Optional[str],
        limit: int,
        next_cursor: Optional[str],
        prev_cursor: Optional[str],
    ):
        clients = await self.client_repo.get_clients_for_engineers(
            q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor
        )

        return clients


def get_client_service(
    client_repo: ClientRepository = Depends(get_client_repo),
    site_repo: SiteRepository = Depends(get_site_repo),
    invoice_repo: InvoiceRepository = Depends(get_invoice_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
    device_repo: DeviceRepository = Depends(get_device_repo),
):
    return ClientService(
        client_repo=client_repo,
        site_repo=site_repo,
        invoice_repo=invoice_repo,
        settings_repo=settings_repo,
        device_repo=device_repo,
    )
