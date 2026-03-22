"""Processor for custom QR frame templates."""
import os
import sys
import time
import uuid
import traceback
from datetime import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config
from storage import r2_storage_proc as r2_mod

ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class qr_frame_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def get_frames(self, fk_user_id):
        try:
            return list(
                self.mgdDB.db_qr_frame.find(
                    {"fk_user_id": fk_user_id, "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def add_frame(self, fk_user_id, name, image_file, qr_x, qr_y, qr_w, qr_h, root_path=None):
        """Upload image to R2 and save frame metadata. Returns dict with frame_id or error."""
        try:
            if not fk_user_id:
                return {"ok": False, "error": "Not authenticated."}
            if not name:
                return {"ok": False, "error": "Frame name is required."}

            ext = os.path.splitext(image_file.filename)[1].lower()
            if ext not in ALLOWED_IMG_EXT:
                return {"ok": False, "error": "Image must be JPG, PNG, or WebP."}

            image_file.seek(0, 2)
            size = image_file.tell()
            image_file.seek(0)
            if size > MAX_FILE_SIZE:
                return {"ok": False, "error": "Image exceeds 5 MB limit."}

            frame_id  = uuid.uuid4().hex
            key       = f"frames/{frame_id}/frame_bg{ext}"
            image_url = r2_mod.r2_storage_proc().upload_file(image_file, key, track_meta={"fk_user_id": fk_user_id, "frame_id": frame_id, "qr_type": "frame"})

            current_time = int(time.time() * 1000)
            created_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.mgdDB.db_qr_frame.insert_one({
                "frame_id"  : frame_id,
                "fk_user_id": fk_user_id,
                "name"      : name,
                "image_url" : image_url,
                "qr_x"      : float(qr_x),
                "qr_y"      : float(qr_y),
                "qr_w"      : float(qr_w),
                "qr_h"      : float(qr_h),
                "status"    : "ACTIVE",
                "created_at": created_at,
                "timestamp" : current_time,
            })
            return {"ok": True, "frame_id": frame_id}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "An internal error occurred."}

    def delete_frame(self, fk_user_id, frame_id):
        try:
            self.mgdDB.db_qr_frame.update_one(
                {"fk_user_id": fk_user_id, "frame_id": frame_id},
                {"$set": {"status": "DELETED"}},
            )
            return {"ok": True}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Delete failed."}
