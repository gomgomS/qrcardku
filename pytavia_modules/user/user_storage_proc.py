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

    def get_garbage_files(self, fk_user_id: str) -> list:
        """
        Return db_qr_assets records that are tracked (ACTIVE) but whose R2 key is no
        longer referenced by any field in any of the user's QR / frame documents.
        These are safe to delete — orphaned files left behind after edits.
        """
        try:
            _r2 = r2_mod.r2_storage_proc()
            base_url = _r2._public_base.rstrip("/")

            # ── 1. All tracked active assets for this user ────────────────
            all_assets = list(self.mgdDB.db_qr_assets.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE"},
                {"asset_id": 1, "r2_key": 1, "file_name": 1, "file_size": 1,
                 "file_category": 1, "qrcard_id": 1, "qr_type": 1, "_id": 0}
            ))
            if not all_assets:
                return []

            # ── 2. Collect all R2 keys currently referenced in any document ─
            referenced_keys = set()

            def _extract(obj):
                if isinstance(obj, str):
                    s = obj.strip()
                    if s.startswith(base_url + "/"):
                        referenced_keys.add(s[len(base_url) + 1:])
                elif isinstance(obj, dict):
                    for v in obj.values():
                        _extract(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _extract(item)

            scan_collections = [
                "db_qrcard", "db_qrcard_pdf", "db_qrcard_allinone",
                "db_qrcard_images", "db_qrcard_video", "db_qrcard_ecard",
                "db_qr_frame",
            ]
            for col_name in scan_collections:
                col = getattr(self.mgdDB, col_name, None)
                if col is None:
                    continue
                for doc in col.find(
                    {"fk_user_id": fk_user_id, "status": {"$in": ["ACTIVE", "DRAFT"]}},
                    {"_id": 0},
                ):
                    _extract(doc)

            # ── 3. Garbage = tracked but not referenced ───────────────────
            garbage = []
            for asset in all_assets:
                key = asset.get("r2_key", "")
                if key and key not in referenced_keys:
                    garbage.append({
                        "asset_id":     asset.get("asset_id", ""),
                        "r2_key":       key,
                        "fname":        asset.get("file_name", key.split("/")[-1]),
                        "size":         asset.get("file_size", 0),
                        "size_fmt":     _fmt_size(asset.get("file_size", 0)),
                        "category":     asset.get("file_category", _file_category(key)),
                        "qrcard_id":    asset.get("qrcard_id", ""),
                        "qr_type":      asset.get("qr_type", ""),
                    })

            garbage.sort(key=lambda x: x["size"], reverse=True)
            return garbage
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return []

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
                qr_type = doc.get("qr_type", meta.get("qr_type", ""))
                if qr_type == "frame":
                    storage_group = "template"
                elif qr_type == "composite":
                    storage_group = "generated"
                else:
                    storage_group = "assets"
                files.append({
                    "key":           key,
                    "url":           _r2.public_url(key),
                    "fname":         doc.get("file_name", key.split("/")[-1]),
                    "size":          size,
                    "size_fmt":      _fmt_size(size),
                    "category":      doc.get("file_category", _file_category(key)),
                    "qr_name":       meta.get("qr_name", ""),
                    "qr_type":       qr_type,
                    "qrcard_id":     qid,
                    "edit_url":      meta.get("edit_url", "#"),
                    "storage_group": storage_group,
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
                        key      = obj["key"]
                        size     = obj["size"]
                        _qt      = meta["qr_type"]
                        _sg      = "template" if _qt == "frame" else "generated" if _qt == "composite" else "assets"
                        total_bytes += size
                        files.append({
                            "key":           key,
                            "url":           _r2.public_url(key),
                            "fname":         key.split("/")[-1],
                            "size":          size,
                            "size_fmt":      _fmt_size(size),
                            "category":      _file_category(key),
                            "qr_name":       meta["qr_name"],
                            "qr_type":       _qt,
                            "qrcard_id":     qid,
                            "edit_url":      meta["edit_url"],
                            "storage_group": _sg,
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
