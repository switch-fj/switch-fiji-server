from sqlmodel import Session, text


def _get_active_contracts(session: Session) -> list:
    result = session.execute(
        text("""
        SELECT DISTINCT
            c.uid::text AS contract_uid,
            s.uid::text AS site_uid,
            s.gateway_id AS gateway_id
        FROM sites s
        JOIN contracts c ON c.site_uid = s.uid
        JOIN contract_details cd ON cd.contract_uid = c.uid
        WHERE COALESCE(cd.actual_commissioned_at, cd.commissioned_at) IS NOT NULL
            AND NOW() > COALESCE(cd.actual_commissioned_at, cd.commissioned_at)
            AND NOW() < COALESCE(cd.actual_end_at, cd.end_at)
    """)
    )
    return result.fetchall()
