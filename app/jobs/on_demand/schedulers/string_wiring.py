import json
from datetime import datetime, timezone
from typing import List

from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.shared import update_job_run
from app.modules.job_run.schema import JobRunStatus
from app.modules.panel_references.model import PanelReference
from app.modules.string_wiring.model import StringWiring
from app.modules.string_wiring.schema import (
    ExpectedMPPT_ATable,
    MPPTFunctionTable,
    StringSchematicsModel,
    StringsInputItemModel,
)

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_string_wiring_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_string_wiring_on_demand(
    self,
    job_run_task_id,
    site_uid,
    string_wiring_uid,
):
    update_job_run(
        reference_uid=string_wiring_uid,
        task_id=job_run_task_id,
        status=JobRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )

    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            panel_refs = (
                session.execute(
                    select(PanelReference).where(
                        PanelReference.site_uid == site_uid,
                        PanelReference.deleted_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )

            if len(panel_refs) == 0:
                raise ValueError(f"PanelReference for site {site_uid} not found")

            string_wiring = session.execute(
                select(StringWiring).where(StringWiring.site_uid == site_uid, StringWiring.deleted_at.is_(None))
            ).scalar_one_or_none()

            if not string_wiring:
                raise ValueError(f"String wiring for {site_uid} not found")

            # 1. compute all the strings.
            string_inputs: List[StringsInputItemModel] = json.loads(string_wiring.string_input)
            string_schematics_model: List[StringSchematicsModel] = []

            for string_input in string_inputs:
                selected_panel: PanelReference
                for panel_ref in panel_refs:
                    if panel_ref.uid == string_input.panel_ref_uid:
                        selected_panel = panel_ref

                string_schematics_model.append(
                    StringSchematicsModel(
                        inverter=string_input.inverter,
                        mppt=string_input.mppt,
                        panel_ref_uid=string_input.panel_ref_uid,
                        panel_qty=string_input.panel_qty,
                        panel_watt=selected_panel.watt,
                        panel_voc=selected_panel.voc,
                        panel_vmp=selected_panel.vmp,
                        ip=selected_panel.imp,
                    ).model_dump()
                )
            string_wiring.wring_schematics = json.dumps(string_schematics_model)

            # 2. compute all the mppt function table.
            mppt_fn_table = MPPTFunctionTable.build(string_schematics_model)
            string_wiring.mppt_fn_table = mppt_fn_table.to_json()

            # 3. compute all the expected mppt_a table
            expected_mppt_a_table = ExpectedMPPT_ATable.build(mppt_table=mppt_fn_table.root)
            string_wiring.expected_mppt_a_table = expected_mppt_a_table.to_json()

            session.commit()

        update_job_run(
            reference_uid=string_wiring_uid,
            task_id=job_run_task_id,
            status=JobRunStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )

    except Exception as exc:
        update_job_run(
            reference_uid=string_wiring_uid,
            task_id=job_run_task_id,
            status=JobRunStatus.FAILED,
            error=str(exc),
        )
        raise self.retry(exc=exc)
