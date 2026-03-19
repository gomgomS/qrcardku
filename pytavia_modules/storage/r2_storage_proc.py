"""Cloudflare R2 storage abstraction (S3-compatible via boto3).

All file uploads in the application go through this module instead of the
local filesystem.  Key naming mirrors the old static/uploads/ structure:

    frames/{frame_id}/frame_bg.ext
    admin_frames/{frame_id}/frame_bg.ext
    pdf/{qrcard_id}/welcome.ext
    pdf/{qrcard_id}/{safe_name}
    pdf/_tmp/{tmp_key}/{safe_name}
    ecard/{qrcard_id}/...
    images/{qrcard_id}/{safe_name}
    images/_tmp/{tmp_key}/{safe_name}
    videos/{qrcard_id}/{safe_name}
    videos/_tmp/{tmp_key}/{safe_name}
    special/{qrcard_id}/...
    special/images/{unique_name}
"""

import sys
import traceback
from io import BytesIO

sys.path.append("pytavia_core")
sys.path.append("pytavia_settings")

import boto3
from botocore.exceptions import ClientError
from pytavia_core import config

# Content-type helpers
_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".svg":  "image/svg+xml",
    ".pdf":  "application/pdf",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".webm": "video/webm",
}


def _mime_from_key(key: str) -> str:
    import os
    ext = os.path.splitext(key)[1].lower()
    return _MIME.get(ext, "application/octet-stream")


class r2_storage_proc:
    """Thin wrapper around boto3 S3 client pointed at Cloudflare R2."""

    def __init__(self):
        self._client = boto3.client(
            "s3",
            endpoint_url=config.CLOUDEFLARE_S3_ENDPOINT,
            aws_access_key_id=config.ACCESS_KEY_ID,
            aws_secret_access_key=config.SECRET_ACCESS_KEY,
            region_name="auto",
        )
        self._bucket = config.R2_BUCKET_NAME
        self._public_base = config.R2_PUBLIC_BASE_URL.rstrip("/")

    # ── Public URL helper ───────────────────────────────────────────────────

    def public_url(self, key: str) -> str:
        return f"{self._public_base}/{key}"

    # ── Upload ──────────────────────────────────────────────────────────────

    def upload_file(self, file_obj, key: str, content_type: str = None) -> str:
        """Upload a Flask FileStorage / file-like object to R2.
        Rewinds to position 0 before upload. Returns the public URL."""
        try:
            file_obj.seek(0)
        except Exception:
            pass
        ct = content_type or _mime_from_key(key)
        self._client.upload_fileobj(
            file_obj,
            self._bucket,
            key,
            ExtraArgs={"ContentType": ct},
        )
        return self.public_url(key)

    def upload_bytes(self, data, key: str, content_type: str = None) -> str:
        """Upload raw bytes or BytesIO to R2. Returns the public URL."""
        if isinstance(data, (bytes, bytearray)):
            data = BytesIO(data)
        elif not hasattr(data, "read"):
            raise ValueError("data must be bytes or a file-like object")
        ct = content_type or _mime_from_key(key)
        self._client.upload_fileobj(
            data,
            self._bucket,
            key,
            ExtraArgs={"ContentType": ct},
        )
        return self.public_url(key)

    # ── Move (copy + delete) ────────────────────────────────────────────────

    def move_file(self, source_key: str, dest_key: str) -> str:
        """Copy source_key → dest_key within the same bucket, then delete source.
        Returns the public URL for dest_key."""
        copy_source = {"Bucket": self._bucket, "Key": source_key}
        self._client.copy_object(
            CopySource=copy_source,
            Bucket=self._bucket,
            Key=dest_key,
            MetadataDirective="COPY",
        )
        self._client.delete_object(Bucket=self._bucket, Key=source_key)
        return self.public_url(dest_key)

    # ── Delete ──────────────────────────────────────────────────────────────

    def delete_file(self, key: str) -> None:
        """Delete a single object from R2 (silently ignores missing keys)."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError:
            pass

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects whose key starts with prefix (simulates rmtree)."""
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self._client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": objects, "Quiet": True},
                    )
        except ClientError:
            pass

    # ── List ────────────────────────────────────────────────────────────

    def list_prefix(self, prefix: str) -> list:
        """List all objects under prefix. Returns list of dicts with Key and Size."""
        results = []
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    results.append({"key": obj["Key"], "size": obj["Size"]})
        except ClientError:
            pass
        return results

    # ── Existence check ─────────────────────────────────────────────────────

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False
