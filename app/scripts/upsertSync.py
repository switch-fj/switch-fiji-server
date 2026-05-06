import json
import os
from datetime import datetime, timezone

import psycopg2
from boto3.dynamodb.types import TypeDeserializer
from dateutil.relativedelta import relativedelta

_conn = None
_deser = TypeDeserializer()


def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode="require",
            connect_timeout=5,
        )
        _conn.autocommit = False
    return _conn


def deserialize(dynamo_item: dict) -> dict:
    return {k: _deser.deserialize(v) for k, v in dynamo_item.items()}


def extract_payload(raw: dict) -> dict:
    is_nested_format = "client" in raw and isinstance(raw.get("client"), dict)

    if is_nested_format:
        client = raw["client"]
        gateway = raw["gateway"]
        return {
            "client_id": client.get("client_id"),
            "client_name": client.get("client_name"),
            "client_email": client.get("client_email"),
            "site_id": client.get("site_id"),
            "gateway_id": gateway.get("gateway_id"),
            "firmware": gateway.get("firmware"),
            "ts_epoch_ms": raw.get("timestamp", {}).get("ts_epoch_ms") or raw.get("ts_epoch_ms"),
            "meters": raw.get("meters", []),
            "inverters": raw.get("inverters", []),
            "ac_units": raw.get("ac_units", []),
            "irradiance_meters": raw.get("irradiance_meters", []),
            "generator": raw.get("generator"),
        }

    # flat format
    return {
        "client_id": raw.get("client_ID") or raw.get("client_id"),
        "client_name": raw.get("client_name"),
        "client_email": raw.get("client_email"),
        "site_id": raw.get("site_id"),
        "gateway_id": raw.get("gateway_id"),
        "firmware": raw.get("fw") or raw.get("firmware"),
        "ts_epoch_ms": raw.get("ts_epoch_ms"),
        "meters": raw.get("meters", []),
        "inverters": raw.get("inverters", []),
        "ac_units": raw.get("ac_units", []),
        "irradiance_meters": raw.get("irradiance_meters", []),
        "generator": raw.get("generator"),
    }


def upsert_client(conn, payload) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO clients (client_id, client_name, client_email)
            VALUES (%(client_id)s, %(client_name)s, %(client_email)s)
            ON CONFLICT (client_id) DO UPDATE
                SET client_name  = EXCLUDED.client_name,
                    client_email = EXCLUDED.client_email
            RETURNING uid
        """,
            {
                "client_id": payload["client_id"],
                "client_name": payload["client_name"],
                "client_email": payload["client_email"],
            },
        )
        return cur.fetchone()[0]


def upsert_site(conn, payload, client_uid: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sites (client_uid, site_id, gateway_id, firmware)
            VALUES (%(client_uid)s, %(site_id)s, %(gateway_id)s, %(firmware)s)
            ON CONFLICT (client_uid, site_id) DO UPDATE
                SET gateway_id = EXCLUDED.gateway_id,
                    firmware   = EXCLUDED.firmware
            RETURNING uid
        """,
            {
                "client_uid": client_uid,
                "site_id": payload["site_id"],
                "gateway_id": payload["gateway_id"],
                "firmware": payload["firmware"],
            },
        )
        return cur.fetchone()[0]


def upsert_devices(conn, payload, site_uid: str):
    device_groups = [
        ("meter", payload["meters"]),
        ("inverter", payload["inverters"]),
        ("ac_unit", payload["ac_units"]),
        ("irradiance_meter", payload["irradiance_meters"]),
    ]

    with conn.cursor() as cur:
        for device_type, devices in device_groups:
            for device in devices:
                is_meter = device_type == "meter"

                cur.execute(
                    """
                    INSERT INTO devices (site_uid, slave_id, device_type, meter_role, is_dual_tariff)
                    VALUES (%(site_uid)s, %(slave_id)s, %(device_type)s, %(meter_role)s, %(is_dual_tariff)s)
                    ON CONFLICT (site_uid, slave_id, device_type) DO UPDATE
                        SET meter_role     = EXCLUDED.meter_role,
                            is_dual_tariff = EXCLUDED.is_dual_tariff
                    """,
                    {
                        "site_uid": site_uid,
                        "slave_id": int(device["slave_id"]),
                        "device_type": device_type,
                        "meter_role": device.get("description") if is_meter else None,
                        "is_dual_tariff": (bool(device.get("tariff")) if is_meter else False),
                    },
                )


def try_lock_contract_dates(conn, site_uid: str, first_seen_at_ms: int):
    """
    1. Sets site.first_seen_at if not already set.
    2. If a contract exists for this site with no actual dates,
       locks actual_commissioning_at and actual_end_at.
    """
    first_seen_at = datetime.fromtimestamp(first_seen_at_ms / 1000, tz=timezone.utc)

    with conn.cursor() as cur:
        # 1. lock first_seen_at on site — only on first push
        cur.execute(
            """
                UPDATE sites
                SET first_seen_at = COALESCE(first_seen_at, %(first_seen_at)s)
                WHERE uid = %(site_uid)s
            """,
            {
                "first_seen_at": first_seen_at,
                "site_uid": site_uid,
            },
        )

        # 2. check if contract exists with no actual dates set
        cur.execute(
            """
            SELECT
                cd.uid,
                cd.term_years
            FROM contract_details cd
            JOIN contracts c ON c.uid = cd.contract_uid
            WHERE c.site_uid = %(site_uid)s
              AND cd.actual_commissioning_at IS NULL
            LIMIT 1
        """,
            {"site_uid": site_uid},
        )
        row = cur.fetchone()

        if not row:
            return  # no pending contract — nothing to do

        details_uid = row[0]
        term_years = row[1]

        actual_end_at = None
        if term_years:
            actual_end_at = first_seen_at + relativedelta(years=term_years)

        # 3. lock actual dates on contract — only once
        cur.execute(
            """
            UPDATE contract_details
            SET actual_commissioning_at = %(actual_commissioning_at)s,
                actual_end_at = %(actual_end_at)s
            WHERE uid = %(details_uid)s
        """,
            {
                "actual_commissioning_at": first_seen_at,
                "actual_end_at": actual_end_at,
                "details_uid": details_uid,
            },
        )


def lambda_handler(event, context):
    print(f"[INFO] Connecting to DB host={os.environ.get('DB_HOST')} port={os.environ.get('DB_PORT')}")

    try:
        conn = get_conn()
        print("[INFO] DB connection successful")
    except Exception as e:
        print(f"[ERROR] DB connection failed: {e}")
        raise

    for record in event["Records"]:
        if record["eventName"] != "INSERT":
            continue

        raw = record["dynamodb"].get("NewImage")
        if not raw:
            continue

        deserialized = deserialize(raw)
        payload = extract_payload(deserialized)

        print(f"[INFO] Processing client_id={payload['client_id']} site_id={payload['site_id']}")

        try:
            client_uid = upsert_client(conn, payload)
            print(f"[INFO] Client upserted uid={client_uid}")
            site_uid = upsert_site(conn, payload, client_uid)
            print(f"[INFO] Site upserted uid={site_uid}")
            upsert_devices(conn, payload, site_uid)
            print("[INFO] Devices upserted")
            try_lock_contract_dates(
                conn,
                site_uid=site_uid,
                first_seen_at_ms=int(payload["ts_epoch_ms"]),
            )
            conn.commit()
            print(f"[INFO] Committed — client_uid={client_uid} site_uid={site_uid}")
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Rolled back: {e}")
            raise

    return {"statusCode": 200, "body": json.dumps("Sync complete")}
