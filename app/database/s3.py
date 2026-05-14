import boto3
from botocore.config import Config as BotcoreConfig

from app.core.config import Config

s3_client = boto3.client(
    "s3",
    region_name=Config.AWS_REGION,
    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
    config=BotcoreConfig(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)
