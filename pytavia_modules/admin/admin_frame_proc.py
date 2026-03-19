"""Processor for admin-managed default QR frame presets."""
import os
import time
import uuid
import traceback
from datetime import datetime

import sys
sys.path.append("pytavia_core")
sys.path.append("pytavia_modules")
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib")
sys.path.append("pytavia_storage")

from pytavia_core import database, config

ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE   = 5 * 1024 * 1024  # 5 MB


class admin_frame_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def get_all_frames(self):
        """Return all active admin frames sorted newest-first."""
        try:
            return list(
                self.mgdDB.db_admin_frame.find({"status": "ACTIVE"}).sort("timestamp", -1)
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return []

    def add_frame(self, name, image_file, qr_x, qr_y, qr_w, qr_h, root_path):
        """Save uploaded image and frame metadata. Returns dict with frame_id or error."""
        try:
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

            frame_id   = uuid.uuid4().hex
            upload_dir = os.path.join(root_path, "static", "uploads", "admin_frames", frame_id)
            os.makedirs(upload_dir, exist_ok=True)

            filename  = "frame_bg" + ext
            save_path = os.path.join(upload_dir, filename)
            image_file.save(save_path)
            image_url = f"/static/uploads/admin_frames/{frame_id}/{filename}"

            current_time = int(time.time() * 1000)
            created_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.mgdDB.db_admin_frame.insert_one({
                "frame_id"  : frame_id,
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
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "An internal error occurred."}

    def delete_frame(self, frame_id):
        """Soft-delete an admin frame by frame_id."""
        try:
            self.mgdDB.db_admin_frame.update_one(
                {"frame_id": frame_id},
                {"$set": {"status": "DELETED"}},
            )
            return {"ok": True}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Delete failed."}
