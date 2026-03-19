"""Processor for custom QR frame templates."""
import os
import time
import uuid
import traceback
from datetime import datetime

from pytavia_core import database, config

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

    def add_frame(self, fk_user_id, name, image_file, qr_x, qr_y, qr_w, qr_h, root_path):
        """Save uploaded image and frame metadata. Returns dict with frame_id or error."""
        try:
            if not fk_user_id:
                return {"ok": False, "error": "Not authenticated."}
            if not name:
                return {"ok": False, "error": "Frame name is required."}

            ext = os.path.splitext(image_file.filename)[1].lower()
            if ext not in ALLOWED_IMG_EXT:
                return {"ok": False, "error": "Image must be JPG, PNG, or WebP."}

            # Check size by reading into memory (small buffer)
            image_file.seek(0, 2)
            size = image_file.tell()
            image_file.seek(0)
            if size > MAX_FILE_SIZE:
                return {"ok": False, "error": "Image exceeds 5 MB limit."}

            frame_id = uuid.uuid4().hex
            upload_dir = os.path.join(root_path, "static", "uploads", "frames", frame_id)
            os.makedirs(upload_dir, exist_ok=True)

            filename = "frame_bg" + ext
            save_path = os.path.join(upload_dir, filename)
            image_file.save(save_path)
            image_url = f"/static/uploads/frames/{frame_id}/{filename}"

            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            doc = {
                "frame_id": frame_id,
                "fk_user_id": fk_user_id,
                "name": name,
                "image_url": image_url,
                "qr_x": float(qr_x),
                "qr_y": float(qr_y),
                "qr_w": float(qr_w),
                "qr_h": float(qr_h),
                "status": "ACTIVE",
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qr_frame.insert_one(doc)
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
