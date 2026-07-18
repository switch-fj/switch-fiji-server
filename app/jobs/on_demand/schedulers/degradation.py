from datetime import date, datetime, timezone

from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.on_demand.triggers.string_wiring import (
    trigger_compute_string_wiring_on_demand,
)
from app.jobs.shared import update_job_run
from app.modules.job_run.schema import JobRunStatus
from app.modules.pv_degradation.model import PvDegradation
from app.modules.pv_degradation.schema import PvDegradationSchedule, YearlyDegradation
from app.modules.string_wiring.model import StringWiring

logger = setup_logger(__name__)

NUM_YEARS = 12


@celery_app.task(
    name="compute_site_yearly_degradation_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_site_yearly_degradation_on_demand(
    self,
    job_run_task_id,
    degradation_uid,
    comissioned_at,
    year1_degradation,
    year2plus_degradation,
):
    update_job_run(
        reference_uid=degradation_uid,
        task_id=job_run_task_id,
        status=JobRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )

    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            pv_degradation = session.execute(
                select(PvDegradation).where(
                    PvDegradation.uid == degradation_uid,
                    PvDegradation.deleted_at.is_(None),
                )
            ).scalar_one_or_none()

            if not pv_degradation:
                raise ValueError(f"PvDegradation {degradation_uid} not found")

            current_schedule = PvDegradationSchedule.from_json(pv_degradation.degradation)
            if not current_schedule.root:
                raise ValueError(f"PvDegradation {degradation_uid} has no year 1 values seeded")

            year_1 = current_schedule.root[0]
            year_1_values = list(year_1.root.values())

            commissioning_date: date = comissioned_at.date() if isinstance(comissioned_at, datetime) else comissioned_at
            months = PvDegradationSchedule.build_month_sequence(commissioning_date, num_years=NUM_YEARS)

            all_years: list[YearlyDegradation] = [year_1]
            previous_year_values = year_1_values

            # Year 2 decays from year 1 using year1_degradation.
            # Years 3..12 each decay from the year before using year2plus_degradation.
            for year_idx in range(1, NUM_YEARS):
                rate = year1_degradation if year_idx == 1 else year2plus_degradation
                current_year_values = [round(v * (1 - rate), 2) for v in previous_year_values]

                year_months = months[year_idx * 12 : (year_idx + 1) * 12]
                all_years.append(YearlyDegradation(root=dict(zip(year_months, current_year_values))))

                previous_year_values = current_year_values

            full_schedule = PvDegradationSchedule(root=all_years)
            pv_degradation.degradation = full_schedule.to_json()

            session.add(pv_degradation)
            session.commit()

            string_wiring = session.execute(
                select(StringWiring).where(
                    StringWiring.site_uid == pv_degradation.site_uid,
                    StringWiring.deleted_at.is_(None),
                )
            ).scalar_one_or_none()

            if string_wiring:
                trigger_compute_string_wiring_on_demand.delay(
                    requesting_user_uid=string_wiring.user_uid,
                    site_uid=string_wiring.site_uid,
                    string_wiring_uid=string_wiring.uid,
                )

            update_job_run(
                reference_uid=degradation_uid,
                task_id=job_run_task_id,
                status=JobRunStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
            )

    except Exception as exc:
        update_job_run(
            reference_uid=degradation_uid,
            task_id=job_run_task_id,
            status=JobRunStatus.FAILED,
            error=str(exc),
        )
        raise self.retry(exc=exc)
