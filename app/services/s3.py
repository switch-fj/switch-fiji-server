from app.core.config import Config
from app.database.s3 import s3_client


class S3Service:
    BUCKET = Config.AWS_S3_BUCKET

    @staticmethod
    def upload_pdf(key: str, pdf_bytes: bytes) -> str:
        s3_client.put_object(
            Bucket=S3Service.BUCKET,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        return key

    @staticmethod
    def generate_presigned_url(key: str, expires_in: int = 300) -> str:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3Service.BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
