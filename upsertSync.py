import json
import os

import psycopg2
from boto3.dynamodb.types import TypeDeserializer

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
    """
    Normalize the flat DynamoDB payload into a consistent
    internal structure the upsert functions can rely on.
    Handles the renamed and flattened fields from the IoT engineer.
    """
    return {
        "client_id": raw.get("client_ID") or raw.get("client_id"),
        "client_name": raw["client_name"],
        "client_email": raw["client_email"],
        "site_id": raw["site_id"],
        "gateway_id": raw["gateway_id"],
        "firmware": raw.get("fw") or raw.get("firmware"),
        "ts_epoch_ms": raw["ts_epoch_ms"],
        "meters": raw.get("meters", []),
        "inverters": raw.get("inverters", []),
        "ac_units": raw.get("ac_units", []),
        "irradiance_meters": raw.get("irradiance_meters", []),
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
                cur.execute(
                    """
                    INSERT INTO devices (site_uid, slave_id, device_type)
                    VALUES (%(site_uid)s, %(slave_id)s, %(device_type)s)
                    ON CONFLICT (site_uid, slave_id, device_type) DO UPDATE
                        SET device_type = EXCLUDED.device_type
                """,
                    {
                        "site_uid": site_uid,
                        "slave_id": int(device["slave_id"]),
                        "device_type": device_type,
                    },
                )


def lambda_handler(event, context):
    conn = get_conn()

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
            site_uid = upsert_site(conn, payload, client_uid)
            upsert_devices(conn, payload, site_uid)
            conn.commit()
            print(f"[INFO] Committed — client_uid={client_uid} site_uid={site_uid}")
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Rolled back: {e}")
            raise

    return {"statusCode": 200, "body": json.dumps("Sync complete")}
