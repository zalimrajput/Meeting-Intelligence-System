"""Object storage service supporting AWS S3 and Cloudflare R2 via S3-compatible API.

Handles streaming uploads (never buffering full files in memory), presigned URL generation,
and file deletion. Supports local disk fallback for offline development and testing.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    Config = None
    ClientError = Exception


class StorageService:
    """Service providing S3/R2 object storage operations with streaming support."""

    def __init__(self) -> None:
        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.S3_REGION
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.access_key = settings.S3_ACCESS_KEY
        self.secret_key = settings.S3_SECRET_KEY
        self.storage_driver = settings.STORAGE_DRIVER
        self.local_storage_path = Path(settings.LOCAL_STORAGE_PATH)

        # Detect if we should use local disk storage (e.g. test or mock credentials)
        self.is_mock = (
            boto3 is None
            or self.storage_driver == "local"
            or self.access_key in ("mock_access_key", "", "none")
            or self.secret_key in ("mock_secret_key", "", "none")
        )

        if not self.is_mock and boto3 is not None and Config is not None:
            # Configure S3/R2 client
            s3_config = Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual" if not self.endpoint_url else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
            )
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=s3_config,
            )
        else:
            self.s3_client = None
            self.local_storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Using local disk storage driver at %s (mock/dev mode)",
                str(self.local_storage_path),
            )

    async def upload_file(
        self,
        file_obj: BinaryIO,
        destination_path: str,
        content_type: str = "application/octet-stream",
    ) -> tuple[str, str, int]:
        """
        Streams file content chunk-by-chunk to storage without loading entire file in memory.
        Calculates SHA-256 checksum and total byte count during streaming.

        Returns:
            tuple[str, str, int]: (storage_path, sha256_checksum, total_bytes)
        """
        return await asyncio.to_thread(
            self._sync_upload_file,
            file_obj,
            destination_path,
            content_type,
        )

    def _sync_upload_file(
        self,
        file_obj: BinaryIO,
        destination_path: str,
        content_type: str,
    ) -> tuple[str, str, int]:
        """Synchronous streaming upload implementation."""
        hasher = hashlib.sha256()
        total_bytes = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        if self.is_mock or self.s3_client is None:
            # Local storage stream
            local_target = self.local_storage_path / destination_path
            local_target.parent.mkdir(parents=True, exist_ok=True)

            with open(local_target, "wb") as f_out:
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    total_bytes += len(chunk)
                    f_out.write(chunk)

            checksum = hasher.hexdigest()
            logger.info(
                "Uploaded file to local storage: path=%s bytes=%d checksum=%s",
                destination_path,
                total_bytes,
                checksum,
            )
            return destination_path, checksum, total_bytes

        # Real S3/R2 streaming upload via S3 upload_fileobj
        try:

            class HashingReader:
                def __init__(self, raw_file: BinaryIO) -> None:
                    self.raw_file = raw_file
                    self.bytes_read = 0

                def read(self, size: int = -1) -> bytes:
                    data = self.raw_file.read(size)
                    if data:
                        hasher.update(data)
                        self.bytes_read += len(data)
                    return data

            hashing_reader = HashingReader(file_obj)
            self.s3_client.upload_fileobj(
                Fileobj=hashing_reader,
                Bucket=self.bucket_name,
                Key=destination_path,
                ExtraArgs={"ContentType": content_type},
            )
            total_bytes = hashing_reader.bytes_read
            checksum = hasher.hexdigest()
            logger.info(
                "Uploaded file to S3/R2: bucket=%s key=%s bytes=%d checksum=%s",
                self.bucket_name,
                destination_path,
                total_bytes,
                checksum,
            )
            return destination_path, checksum, total_bytes
        except ClientError as e:
            logger.error("Failed to upload file to S3/R2: %s", str(e))
            raise RuntimeError(f"Storage upload error: {e}") from e

    async def get_presigned_url(
        self,
        storage_path: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Generates a secure presigned URL for file playback and download."""
        return await asyncio.to_thread(
            self._sync_get_presigned_url,
            storage_path,
            expires_in_seconds,
        )

    def _sync_get_presigned_url(
        self,
        storage_path: str,
        expires_in_seconds: int,
    ) -> str:
        """Synchronous presigned URL generation."""
        if self.is_mock or self.s3_client is None:
            return f"http://localhost:{settings.PORT}/api/v1/storage/{storage_path}"

        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": storage_path,
                },
                ExpiresIn=expires_in_seconds,
            )
            return url
        except ClientError as e:
            logger.error("Failed to generate presigned URL for %s: %s", storage_path, str(e))
            raise RuntimeError(f"Storage presigned URL error: {e}") from e

    async def get_file_bytes(self, storage_path: str) -> bytes:
        """Retrieves raw file bytes from local or S3 storage."""
        return await asyncio.to_thread(self._sync_get_file_bytes, storage_path)

    def _sync_get_file_bytes(self, storage_path: str) -> bytes:
        """Synchronous get file bytes."""
        if self.is_mock or self.s3_client is None:
            local_target = self.local_storage_path / storage_path
            if not local_target.exists():
                raise FileNotFoundError(f"Storage file not found locally: {local_target}")
            return local_target.read_bytes()

        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_path,
            )
            return response["Body"].read()
        except ClientError as e:
            logger.error("Failed to read S3/R2 object %s: %s", storage_path, str(e))
            raise RuntimeError(f"Storage read error: {e}") from e

    def get_local_path(self, storage_path: str) -> Path | None:
        """Returns Path if the file exists on local storage, or None if in S3."""
        if self.is_mock or self.s3_client is None:
            local_target = self.local_storage_path / storage_path
            if local_target.exists():
                return local_target
        return None

    async def delete_file(self, storage_path: str) -> bool:
        """Deletes an object from storage."""
        return await asyncio.to_thread(self._sync_delete_file, storage_path)

    def _sync_delete_file(self, storage_path: str) -> bool:
        """Synchronous file deletion."""
        if self.is_mock or self.s3_client is None:
            local_target = self.local_storage_path / storage_path
            if local_target.exists():
                try:
                    local_target.unlink()
                    logger.info("Deleted local file: %s", str(local_target))
                except OSError as e:
                    logger.warning("Could not delete local file %s: %s", str(local_target), str(e))
            return True

        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_path,
            )
            logger.info("Deleted S3/R2 object: bucket=%s key=%s", self.bucket_name, storage_path)
            return True
        except ClientError as e:
            logger.warning("Failed to delete S3/R2 object %s: %s", storage_path, str(e))
            return False


# Global singleton storage service instance
storage_service: StorageService = StorageService()

