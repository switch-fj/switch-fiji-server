from datetime import datetime, timezone

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.shared import update_job_run
from app.modules.billing.engine import BillingEngine
from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.job_run.schema import JobRunStatus
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_contract_invoice_for_period_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_contract_invoice_for_period_on_demand(
    self, job_run_task_id, contract_uid, gateway_id, site_uid, period_start, period_end
):
    update_job_run(
        reference_uid=contract_uid,
        task_id=job_run_task_id,
        status=JobRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(
                select(Contract)
                .options(
                    joinedload(Contract.details),
                    joinedload(Contract.client),
                )
                .where(Contract.uid == contract_uid)
            ).scalar_one_or_none()

            devices = (
                session.execute(
                    select(Device).where(
                        Device.site_uid == site_uid,
                        Device.device_type == DeviceType.METER.value,
                    )
                )
                .scalars()
                .all()
            )

            contract_settings = (
                session.execute(
                    select(ContractSettings).options(
                        selectinload(ContractSettings.efl_rate_history),
                        selectinload(ContractSettings.vat_rate_history),
                    )
                )
                .scalars()
                .first()
            )

            if not contract or not devices:
                update_job_run(
                    reference_uid=contract_uid,
                    task_id=job_run_task_id,
                    status=JobRunStatus.FAILED,
                    error="Contract or devices not found",
                )
                return

            invoice_uid = BillingEngine.handle_invoice_bill(
                session=session,
                contract=contract,
                contract_settings=contract_settings,
                devices=devices,
                gateway_id=gateway_id,
                period_start=period_start,
                period_end=period_end,
            )

            if not invoice_uid:
                logger.error(f"Unable to create invoice: for task {job_run_task_id}")

            update_job_run(
                reference_uid=contract_uid,
                task_id=job_run_task_id,
                status=JobRunStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                result_uid=invoice_uid,
            )

    except Exception as exc:
        update_job_run(
            reference_uid=contract_uid,
            task_id=job_run_task_id,
            status=JobRunStatus.FAILED,
            error=str(exc),
        )
        raise self.retry(exc=exc)
