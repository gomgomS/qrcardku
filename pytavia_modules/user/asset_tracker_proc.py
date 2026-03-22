"""Asset metadata tracker.

Every file uploaded to R2 gets a corresponding db_qr_assets document so that
storage calculations can be served from MongoDB instead of listing R2 objects.
"""
import os
import time
import uuid
import traceback

from pytavia_core import database, config

_IMG_EXT  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_VID_EXT  = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_PDF_EXT  = {".pdf"}


def _file_category(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    if ext in _IMG_EXT: return "image"
    if ext in _VID_EXT: return "video"
    if ext in _PDF_EXT: return "pdf"
    return "other"


def _fmt_size(n: int) -> str:
    if n >= 1048576: return f"{n / 1048576:.1f} MB"
    if n >= 1024:    return f"{n / 1024:.1f} KB"
    return f"{n} B"


class asset_tracker_proc:

    def __init__(self, app=None):
        self.webapp = app

    def _db(self):
        return database.get_db_conn(config.mainDB)

    # ── Write ────────────────────────────────────────────────────────────────

    def track(self, fk_user_id: str, r2_key: str, file_size: int,
              qrcard_id: str = "", frame_id: str = "", qr_type: str = "",
              file_name: str = ""):
        """Insert one asset metadata record. Called right after a successful R2 upload."""
        try:
            now = time.time()
            self._db().db_qr_assets.insert_one({
                "asset_id"      : uuid.uuid4().hex,
                "fk_user_id"    : fk_user_id,
                "qrcard_id"     : qrcard_id,
                "frame_id"      : frame_id,
                "qr_type"       : qr_type,
                "r2_key"        : r2_key,
                "file_name"     : file_name or os.path.basename(r2_key),
                "file_size"     : int(file_size),
                "file_category" : _file_category(r2_key),
                "status"        : "ACTIVE",
                "created_at"    : time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now)),
                "timestamp"     : now,
            })
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())

    def untrack_key(self, r2_key: str):
        """Mark a single asset DELETED by its R2 key."""
        try:
            self._db().db_qr_assets.update_many(
                {"r2_key": r2_key},
                {"$set": {"status": "DELETED"}},
            )
        except Exception:
            pass

    def untrack_qr(self, qrcard_id: str):
        """Mark all assets for a QR card as DELETED."""
        try:
            self._db().db_qr_assets.update_many(
                {"qrcard_id": qrcard_id},
                {"$set": {"status": "DELETED"}},
            )
        except Exception:
            pass

    def untrack_frame(self, frame_id: str):
        """Mark all assets for a frame as DELETED."""
        try:
            self._db().db_qr_assets.update_many(
                {"frame_id": frame_id},
                {"$set": {"status": "DELETED"}},
            )
        except Exception:
            pass

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_qr_size(self, qrcard_id: str) -> dict:
        """Return total bytes and file count for one QR from DB."""
        try:
            docs = list(self._db().db_qr_assets.find(
                {"qrcard_id": qrcard_id, "status": "ACTIVE"},
                {"file_size": 1, "_id": 0},
            ))
            total = sum(d["file_size"] for d in docs)
            return {"bytes": total, "files": len(docs), "size_fmt": _fmt_size(total), "from_db": True}
        except Exception:
            return {"bytes": 0, "files": 0, "size_fmt": "0 B", "from_db": False}

    def get_user_assets(self, fk_user_id: str) -> list:
        """Return all active asset docs for a user (for storage page)."""
        try:
            return list(self._db().db_qr_assets.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
            ))
        except Exception:
            return []

    def has_assets(self, qrcard_id: str) -> bool:
        """Return True if DB has any tracked assets for this QR."""
        try:
            return self._db().db_qr_assets.count_documents(
                {"qrcard_id": qrcard_id, "status": "ACTIVE"}, limit=1
            ) > 0
        except Exception:
            return False
