"""Processor for user storage usage — scans R2 for all files owned by a user."""
import os
import sys
import traceback

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config
from storage import r2_storage_proc as r2_mod

STORAGE_LIMIT_BYTES = int(config.LIMIT_STORAGE_EACH_USER) * 1024 * 1024

# R2 key prefix per QR type
_QR_TYPE_PREFIX = {
    "allinone": "allinone",
    "pdf":      "pdf",
    "images":   "images",
    "video":    "videos",
    "special":  "special",
    "ecard":    "ecard",
    "web":      "web",
    "links":    "links",
    "sosmed":   "sosmed",
}

_IMG_EXT  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_VID_EXT  = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_PDF_EXT  = {".pdf"}


def _file_category(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    if ext in _IMG_EXT:
        return "image"
    if ext in _VID_EXT:
        return "video"
    if ext in _PDF_EXT:
        return "pdf"
    return "other"


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


class user_storage_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app

    def get_storage_info(self, fk_user_id: str) -> dict:
        """
        Scan R2 for all files belonging to this user.
        Returns:
            total_bytes, limit_bytes, percent_used, files (list), total_fmt, limit_fmt
        """
        try:
            _r2 = r2_mod.r2_storage_proc()

            # ── 1. Collect (prefix, meta) pairs ──────────────────────────
            pairs = []  # (r2_prefix, {qr_name, qr_type, qrcard_id, edit_url})

            # QR cards (all types)
            cards = list(self.mgdDB.db_qrcard.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
                {"qrcard_id": 1, "qr_type": 1, "name": 1}
            ))
            for c in cards:
                qid   = c.get("qrcard_id", "")
                qtype = c.get("qr_type", "")
                name  = c.get("name", "Untitled")
                folder = _QR_TYPE_PREFIX.get(qtype, qtype)
                if qid and folder:
                    edit_url = f"/qr/update/{qtype}/{qid}"
                    pairs.append((
                        f"{folder}/{qid}/",
                        {"qr_name": name, "qr_type": qtype, "qrcard_id": qid, "edit_url": edit_url}
                    ))

            # User custom frames
            frames = list(self.mgdDB.db_qr_frame.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
                {"frame_id": 1, "name": 1}
            ))
            for f in frames:
                fid  = f.get("frame_id", "")
                name = f.get("name", "Frame")
                if fid:
                    pairs.append((
                        f"frames/{fid}/",
                        {"qr_name": name, "qr_type": "frame", "qrcard_id": fid, "edit_url": "/user/templates"}
                    ))

            # ── 2. List objects in R2 for each prefix ────────────────────
            files = []
            total_bytes = 0

            for prefix, meta in pairs:
                objects = _r2.list_prefix(prefix)
                for obj in objects:
                    key  = obj["key"]
                    size = obj["size"]
                    total_bytes += size
                    fname = key.split("/")[-1]
                    files.append({
                        "key":      key,
                        "url":      _r2.public_url(key),
                        "fname":    fname,
                        "size":     size,
                        "size_fmt": _fmt_size(size),
                        "category": _file_category(key),
                        "qr_name":  meta["qr_name"],
                        "qr_type":  meta["qr_type"],
                        "qrcard_id": meta["qrcard_id"],
                        "edit_url": meta["edit_url"],
                    })

            # Sort largest first
            files.sort(key=lambda x: x["size"], reverse=True)

            pct = min(int(total_bytes / STORAGE_LIMIT_BYTES * 100), 100)
            free_bytes = max(STORAGE_LIMIT_BYTES - total_bytes, 0)

            return {
                "ok":           True,
                "total_bytes":  total_bytes,
                "limit_bytes":  STORAGE_LIMIT_BYTES,
                "free_bytes":   free_bytes,
                "percent_used": pct,
                "total_fmt":    _fmt_size(total_bytes),
                "limit_fmt":    _fmt_size(STORAGE_LIMIT_BYTES),
                "free_fmt":     _fmt_size(free_bytes),
                "file_count":   len(files),
                "files":        files,
            }
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {
                "ok": False,
                "total_bytes": 0, "limit_bytes": STORAGE_LIMIT_BYTES,
                "free_bytes": STORAGE_LIMIT_BYTES, "percent_used": 0,
                "total_fmt": "0 B", "limit_fmt": _fmt_size(STORAGE_LIMIT_BYTES),
                "free_fmt": _fmt_size(STORAGE_LIMIT_BYTES),
                "file_count": 0, "files": [],
            }
