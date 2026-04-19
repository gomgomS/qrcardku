"""Cloudflare R2 storage abstraction (S3-compatible via boto3).

All file uploads in the application go through this module instead of the
local filesystem.  Key naming mirrors the old static/uploads/ structure:

    frames/{frame_id}/frame_bg_{frame_id}.ext
    admin_frames/{frame_id}/frame_bg_{frame_id}.ext
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

    def upload_file(self, file_obj, key: str, content_type: str = None,
                    track_meta: dict = None) -> str:
        """Upload a Flask FileStorage / file-like object to R2.
        Rewinds to position 0 before upload. Returns the public URL.

        track_meta (optional): if provided, saves asset metadata to db_qr_assets.
            Required keys: fk_user_id, qrcard_id (or frame_id), qr_type
            Optional keys: file_name
        """
        # Measure size before uploading
        file_size = 0
        try:
            file_obj.seek(0, 2)
            file_size = file_obj.tell()
            file_obj.seek(0)
        except Exception:
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
        url = self.public_url(key)

        if track_meta and track_meta.get("fk_user_id"):
            self._track(key, file_size, track_meta)

        return url

    def upload_bytes(self, data, key: str, content_type: str = None,
                     track_meta: dict = None) -> str:
        """Upload raw bytes or BytesIO to R2. Returns the public URL.

        track_meta: same as upload_file.
        """
        if isinstance(data, (bytes, bytearray)):
            file_size = len(data)
            data = BytesIO(data)
        elif hasattr(data, "read"):
            try:
                data.seek(0, 2)
                file_size = data.tell()
                data.seek(0)
            except Exception:
                file_size = 0
        else:
            raise ValueError("data must be bytes or a file-like object")

        ct = content_type or _mime_from_key(key)
        self._client.upload_fileobj(
            data,
            self._bucket,
            key,
            ExtraArgs={"ContentType": ct},
        )
        url = self.public_url(key)

        if track_meta and track_meta.get("fk_user_id"):
            self._track(key, file_size, track_meta)

        return url

    # ── Move (copy + delete) ────────────────────────────────────────────────

    def move_file(self, source_key: str, dest_key: str,
                  track_meta: dict = None) -> str:
        """Copy source_key → dest_key within the same bucket, then delete source.
        Returns the public URL for dest_key.

        track_meta: if provided, saves asset metadata to db_qr_assets after move.
            File size is fetched via head_object on dest_key after the copy.
        """
        copy_source = {"Bucket": self._bucket, "Key": source_key}
        self._client.copy_object(
            CopySource=copy_source,
            Bucket=self._bucket,
            Key=dest_key,
            MetadataDirective="COPY",
        )
        self._client.delete_object(Bucket=self._bucket, Key=source_key)
        url = self.public_url(dest_key)

        if track_meta and track_meta.get("fk_user_id"):
            file_size = self.get_file_size(dest_key)
            self._track(dest_key, file_size, track_meta)

        return url

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

    def delete_keys_batch(self, keys: list) -> dict:
        """Delete a specific list of R2 keys concurrently.
        Returns a dictionary containing the count of deleted objects and the exact R2 responses."""
        if not keys:
            return {"deleted": 0, "results": []}
            
        import concurrent.futures
        
        def _del_single(key):
            try:
                resp = self._client.delete_object(Bucket=self._bucket, Key=key)
                return {"key": key, "status": "success", "r2_resp": resp.get("ResponseMetadata", {})}
            except Exception as e:
                print(f"Failed to delete {key}: {e}")
                return {"key": key, "status": "error", "error_msg": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(_del_single, keys))
            deleted = sum(1 for r in results if r["status"] == "success")
            
        return {"deleted": deleted, "results": results}

    # ── Parallel moves / uploads ────────────────────────────────────────

    def move_files_parallel(self, file_specs: list, max_workers: int = 5) -> list:
        """Move multiple R2 objects (copy + delete source) in parallel.
        file_specs: list of (source_key, dest_key, track_meta|None).
        Returns list of {"source", "dest", "url", "status"} dicts preserving input order.
        """
        if not file_specs:
            return []

        import concurrent.futures

        def _move_single(spec):
            source_key, dest_key, track_meta = spec
            try:
                url = self.move_file(source_key, dest_key, track_meta=track_meta)
                return {"source": source_key, "dest": dest_key, "url": url, "status": "success"}
            except Exception as e:
                return {"source": source_key, "dest": dest_key, "url": None, "status": "error", "error_msg": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_move_single, file_specs))

        return results

    def upload_files_parallel(self, file_specs: list, max_workers: int = 5) -> list:
        """Upload multiple file-like objects to R2 in parallel.
        file_specs: list of (file_obj, key, track_meta|None).
        Returns list of {"key", "url", "status"} dicts preserving input order.
        """
        if not file_specs:
            return []

        import concurrent.futures

        def _upload_single(spec):
            file_obj, key, track_meta = spec
            try:
                url = self.upload_file(file_obj, key, track_meta=track_meta)
                return {"key": key, "url": url, "status": "success"}
            except Exception as e:
                return {"key": key, "url": None, "status": "error", "error_msg": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_upload_single, file_specs))

        return results

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

    # ── Size ────────────────────────────────────────────────────────────────

    def get_file_size(self, key: str) -> int:
        """Return ContentLength of an R2 object via HEAD request (cheap). Returns 0 on error."""
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
            return resp.get("ContentLength", 0)
        except ClientError:
            return 0

    # ── Internal asset tracking ──────────────────────────────────────────────

    def _track(self, r2_key: str, file_size: int, meta: dict):
        """Write one record to db_qr_assets. Fails silently so upload is never blocked."""
        try:
            import sys
            sys.path.append("pytavia_modules")
            from pytavia_modules.user import asset_tracker_proc as _atp
            _atp.asset_tracker_proc().track(
                fk_user_id  = meta.get("fk_user_id", ""),
                r2_key      = r2_key,
                file_size   = file_size,
                qrcard_id   = meta.get("qrcard_id", ""),
                frame_id    = meta.get("frame_id", ""),
                qr_type     = meta.get("qr_type", ""),
                file_name   = meta.get("file_name", ""),
            )
        except Exception:
            pass
