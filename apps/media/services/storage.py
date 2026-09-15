"""MEDIA-A : client MinIO/S3 (boto3). Bucket auto-créé, jamais de path public."""

import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils import timezone

_PRESIGN_EXPIRES = 900


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.MINIO_ENDPOINT,
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _ensure_bucket(client) -> None:
    bucket = settings.MINIO_BUCKET
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def build_key(media_type: str, ext: str = "") -> str:
    year = timezone.now().year
    return f"{media_type.lower()}/{year}/{uuid.uuid4()}{ext}"


def presigned_put_url(key: str, content_type: str, expires: int = _PRESIGN_EXPIRES) -> str:
    client = _client()
    _ensure_bucket(client)
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.MINIO_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presigned_get_url(key: str, expires: int = _PRESIGN_EXPIRES) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.MINIO_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def put_object_bytes(key: str, data: bytes, content_type: str) -> None:
    client = _client()
    _ensure_bucket(client)
    client.put_object(Bucket=settings.MINIO_BUCKET, Key=key, Body=data, ContentType=content_type)


def head_object(key: str) -> dict | None:
    client = _client()
    try:
        return client.head_object(Bucket=settings.MINIO_BUCKET, Key=key)
    except ClientError:
        return None


def delete_object(key: str) -> None:
    client = _client()
    try:
        client.delete_object(Bucket=settings.MINIO_BUCKET, Key=key)
    except ClientError:
        pass
