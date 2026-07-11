from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.automatic.schedulers.snapshot import (
    compute_contract_invoice_snapshot_on_auto,
)
from app.jobs.celery import celery_app
from app.jobs.shared import get_active_contracts

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_compute_contract_invoice_snapshot_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_compute_contract_invoice_snapshot_on_auto(self):
    try:
        with get_celery_db_session() as session:
            ctive_contracts = get_active_contracts(session)

        for datum in ctive_contracts:
            compute_contract_invoice_snapshot_on_auto.delay(
                contract_uid=str(datum.contract_uid),
                gateway_id=datum.gateway_id,
                site_uid=str(datum.site_uid),
            )
    except Exception as exc:
        raise self.retry(exc=exc)
