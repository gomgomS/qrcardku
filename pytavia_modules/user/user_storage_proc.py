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
        Return storage info for a user.
        Reads from db_qr_assets (MongoDB) — no R2 API calls.
        Falls back to R2 listing for QRs that have no tracked assets yet
        (backward compatibility for uploads made before tracking was added).
        """
        try:
            _r2 = r2_mod.r2_storage_proc()

            # ── Build qrcard_id → QR meta map from DB ───────────────────
            qr_meta = {}  # qrcard_id -> {qr_name, qr_type, edit_url}

            cards = list(self.mgdDB.db_qrcard.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
                {"qrcard_id": 1, "qr_type": 1, "name": 1}
            ))
            for c in cards:
                qid   = c.get("qrcard_id", "")
                qtype = c.get("qr_type", "")
                if qid:
                    qr_meta[qid] = {
                        "qr_name":  c.get("name", "Untitled"),
                        "qr_type":  qtype,
                        "edit_url": f"/qr/update/{qtype}/{qid}",
                    }

            frames = list(self.mgdDB.db_qr_frame.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
                {"frame_id": 1, "name": 1}
            ))
            frame_meta = {}
            for f in frames:
                fid = f.get("frame_id", "")
                if fid:
                    frame_meta[fid] = {"qr_name": f.get("name", "Frame"), "qr_type": "frame", "edit_url": "/user/templates"}

            # ── 1. Read tracked assets from db_qr_assets ────────────────
            tracked_docs = list(self.mgdDB.db_qr_assets.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"}
            ))

            files       = []
            total_bytes = 0
            tracked_qrs = set()  # which qrcard_ids have tracked assets

            for doc in tracked_docs:
                qid   = doc.get("qrcard_id", "") or doc.get("frame_id", "")
                meta  = qr_meta.get(qid) or frame_meta.get(qid) or {}
                size  = doc.get("file_size", 0)
                key   = doc.get("r2_key", "")
                total_bytes += size
                tracked_qrs.add(qid)
                files.append({
                    "key":       key,
                    "url":       _r2.public_url(key),
                    "fname":     doc.get("file_name", key.split("/")[-1]),
                    "size":      size,
                    "size_fmt":  _fmt_size(size),
                    "category":  doc.get("file_category", _file_category(key)),
                    "qr_name":   meta.get("qr_name", ""),
                    "qr_type":   doc.get("qr_type", meta.get("qr_type", "")),
                    "qrcard_id": qid,
                    "edit_url":  meta.get("edit_url", "#"),
                })

            # ── 2. R2 fallback for QRs with no tracked assets yet ────────
            untracked_pairs = []
            for qid, meta in qr_meta.items():
                if qid not in tracked_qrs:
                    folder = _QR_TYPE_PREFIX.get(meta["qr_type"], meta["qr_type"])
                    if folder:
                        untracked_pairs.append((f"{folder}/{qid}/", qid, meta))
            for fid, meta in frame_meta.items():
                if fid not in tracked_qrs:
                    untracked_pairs.append((f"frames/{fid}/", fid, meta))

            if untracked_pairs:
                for prefix, qid, meta in untracked_pairs:
                    for obj in _r2.list_prefix(prefix):
                        key  = obj["key"]
                        size = obj["size"]
                        total_bytes += size
                        files.append({
                            "key":       key,
                            "url":       _r2.public_url(key),
                            "fname":     key.split("/")[-1],
                            "size":      size,
                            "size_fmt":  _fmt_size(size),
                            "category":  _file_category(key),
                            "qr_name":   meta["qr_name"],
                            "qr_type":   meta["qr_type"],
                            "qrcard_id": qid,
                            "edit_url":  meta["edit_url"],
                        })

            files.sort(key=lambda x: x["size"], reverse=True)
            pct        = min(int(total_bytes / STORAGE_LIMIT_BYTES * 100), 100)
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
