import sys
import time
import uuid
import random
import string
import traceback
from datetime import datetime

sys.path.append("pytavia_core")

from pytavia_core import database, config  # noqa: F401

SHORT_CODE_LENGTH = 8
SHORT_CODE_CHARS = string.ascii_lowercase + string.digits


class qr_video_proc:
    """Standalone processor for video QR cards."""

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def _generate_short_code(self):
        return "".join(random.choices(SHORT_CODE_CHARS, k=SHORT_CODE_LENGTH))

    def is_short_code_unique(self, short_code, exclude_qrcard_id=None):
        try:
            query = {"short_code": short_code, "status": "ACTIVE"}
            if exclude_qrcard_id:
                query["qrcard_id"] = {"$ne": exclude_qrcard_id}
            return self.mgdDB.db_qrcard.find_one(query) is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def is_name_unique(self, fk_user_id, name, exclude_id=None):
        try:
            query = {"fk_user_id": fk_user_id, "name": name, "status": "ACTIVE"}
            if exclude_id:
                query["qrcard_id"] = {"$ne": exclude_id}
            existing = self.mgdDB.db_qrcard.find_one(query)
            return existing is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def add_qrcard(self, params):
        """Create a new video qrcard."""
        try:
            fk_user_id = params.get("fk_user_id")
            name = params.get("name", "Untitled QR")
            url_content = params.get("url_content", "")
            short_code = (params.get("short_code") or "").strip().lower()

            if not fk_user_id:
                return {
                    "message_action": "ADD_QRCARD_FAILED",
                    "message_desc": "User authentication required.",
                    "message_data": {},
                }
            if not url_content:
                return {
                    "message_action": "ADD_QRCARD_FAILED",
                    "message_desc": "URL Content is required.",
                    "message_data": {},
                }

            import re

            if short_code:
                if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                    return {
                        "message_action": "ADD_QRCARD_FAILED",
                        "message_desc": "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols.",
                        "message_data": {},
                    }
                if not self.is_short_code_unique(short_code):
                    return {
                        "message_action": "ADD_QRCARD_FAILED",
                        "message_desc": "This address identifier is already in use. Please choose another.",
                        "message_data": {},
                    }
            else:
                for _ in range(20):
                    short_code = self._generate_short_code()
                    if self.is_short_code_unique(short_code):
                        break
                else:
                    return {
                        "message_action": "ADD_QRCARD_FAILED",
                        "message_desc": "Could not generate a unique code. Please try again.",
                        "message_data": {},
                    }

            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            qrcard_rec = database.get_record("db_qrcard")
            qrcard_rec["qrcard_id"] = qrcard_id
            qrcard_rec["fk_user_id"] = fk_user_id
            qrcard_rec["qr_type"] = "video"
            qrcard_rec["name"] = name
            qrcard_rec["url_content"] = url_content
            qrcard_rec["short_code"] = short_code
            qrcard_rec["design_data"] = {}
            qrcard_rec["qr_image_url"] = ""

            qrcard_rec["stats"] = {"scan_count": 0}
            try:
                enabled_raw = params.get("scan_limit_enabled", False)
                qrcard_rec["scan_limit_enabled"] = bool(enabled_raw)
                limit_raw = params.get("scan_limit_value", 0)
                limit_val = int(limit_raw) if str(limit_raw).strip().isdigit() else 0
                qrcard_rec["scan_limit_value"] = max(limit_val, 0)
            except Exception:
                qrcard_rec["scan_limit_enabled"] = False
                qrcard_rec["scan_limit_value"] = 0

            qrcard_rec["status"] = "ACTIVE"
            qrcard_rec["created_at"] = created_at
            qrcard_rec["timestamp"] = current_time

            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            video_rec = database.get_record("db_qrcard_video")
            video_rec["qrcard_id"] = qrcard_id
            video_rec["fk_user_id"] = fk_user_id
            video_rec["qr_type"] = "video"
            video_rec["name"] = name
            video_rec["url_content"] = url_content
            video_rec["short_code"] = short_code
            video_rec["stats"] = qrcard_rec.get("stats", {"scan_count": 0})
            video_rec["scan_limit_enabled"] = qrcard_rec.get("scan_limit_enabled", False)
            video_rec["scan_limit_value"] = qrcard_rec.get("scan_limit_value", 0)
            video_rec["status"] = qrcard_rec.get("status", "ACTIVE")
            video_rec["created_at"] = created_at
            video_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard_video.insert_one(video_rec)

            # Also write summary index entry
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "video"
            idx["name"] = name
            idx["short_code"] = short_code
            idx["status"] = "ACTIVE"
            idx["created_at"] = created_at
            idx["timestamp"] = current_time
            self.mgdDB.db_qr_index.insert_one(idx)

            return {
                "message_action": "ADD_QRCARD_SUCCESS",
                "message_desc": "QR card generated and saved successfully.",
                "message_data": {"qrcard_id": qrcard_id},
            }
        except Exception:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "ADD_QRCARD_FAILED",
                "message_desc": "An internal error occurred.",
                "message_data": {"trace": err_trace},
            }

    def get_qrcard_by_user(self, fk_user_id):
        try:
            return list(
                self.mgdDB.db_qrcard.find(
                    {"fk_user_id": fk_user_id, "qr_type": "video", "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )
        except Exception:
            self.webapp.logger.debug("qr_video_proc.get_qrcard_by_user failed", exc_info=True)
            return []

    def get_qrcard(self, fk_user_id, qrcard_id):
        """Return video doc for edit."""
        try:
            doc = self.mgdDB.db_qrcard_video.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
            if doc:
                return doc
            return self.mgdDB.db_qrcard.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "qr_type": "video",
                    "status": "ACTIVE",
                }
            )
        except Exception:
            self.webapp.logger.debug("qr_video_proc.get_qrcard failed", exc_info=True)
            return None

    def edit_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            name = params.get("name")
            url_content = params.get("url_content")

            update_data = {
                "name": name,
                "url_content": url_content,
            }

            for key, val in params.items():
                if key.startswith("video_") and not key.endswith("[]"):
                    update_data[key] = val

            # Also handle video_links which is passed manually in save
            if "video_links" in params:
                update_data["video_links"] = params["video_links"]

            if "scan_limit_enabled" in params:
                update_data["scan_limit_enabled"] = bool(params.get("scan_limit_enabled"))
            if "scan_limit_value" in params:
                try:
                    limit_raw = params.get("scan_limit_value", 0)
                    limit_val = int(limit_raw) if str(limit_raw).strip().isdigit() else 0
                    update_data["scan_limit_value"] = max(limit_val, 0)
                except Exception:
                    pass

            doc = self.get_qrcard(fk_user_id, qrcard_id)
            if doc:
                import re

                new_short = (params.get("short_code") or "").strip().lower()
                current_short = (doc.get("short_code") or "").strip().lower()
                if new_short and new_short != current_short:
                    if re.match(r"^[a-z0-9_-]{2,32}$", new_short) and self.is_short_code_unique(
                        new_short, exclude_qrcard_id=qrcard_id
                    ):
                        update_data["short_code"] = new_short

            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": update_data},
            )
            self.mgdDB.db_qrcard_video.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": update_data},
                upsert=True,
            )
            index_update = {}
            if "name" in update_data:
                index_update["name"] = update_data["name"]
            if "short_code" in update_data:
                index_update["short_code"] = update_data["short_code"]
            if index_update:
                self.mgdDB.db_qr_index.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": index_update},
                )
            return {"status": "SUCCESS", "message": "QR card updated."}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"status": "FAILED", "message": "Error updating QR card."}

    def delete_qrcard(self, fk_user_id, qrcard_id):
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"status": "DELETED"}},
            )
            self.mgdDB.db_qrcard_video.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"status": "DELETED"}},
                upsert=True,
            )
            self.mgdDB.db_qr_index.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"status": "DELETED"}},
            )
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def complete_video_save(self, request, session, root_path=None):
        """
        Full video save: build params, add_qrcard, and update db_qrcard.
        Returns dict with success=True or success=False + form data for error re-render.
        """
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated", "url_content": "", "qr_name": "", "short_code": "", "qr_encode_url": None}
        params = {
            "fk_user_id": fk_user_id,
            "name": request.form.get("qr_name", "Untitled QR"),
            "url_content": request.form.get("url_content", ""),
            "short_code": (request.form.get("short_code") or "").strip().lower(),
        }
        params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
        result = self.add_qrcard(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            sc = params.get("short_code") or ""
            base = config.G_BASE_URL
            encode = (base + "/video/" + sc) if sc else None
            return {
                "success": False,
                "error_msg": result.get("message_desc", "Save failed."),
                "url_content": request.form.get("url_content", ""),
                "qr_name": request.form.get("qr_name", ""),
                "short_code": sc,
                "qr_encode_url": encode,
            }
        new_qrcard_id = result["message_data"]["qrcard_id"]

        video_title = (request.form.get("video_title") or "").strip()
        video_desc = (request.form.get("video_desc") or "").strip()

        about_update = {
            "video_title": video_title,
            "video_desc": video_desc,
        }

        # Design fields from form
        design_update = {}
        for key in request.form:
            if key.startswith("video_") and not key.endswith("[]"):
                val = request.form.get(key)
                if val is not None and str(val).strip() != "":
                    design_update[key] = str(val).strip()

        if request.form.get("video_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["video_font_apply_all"] = True
        else:
            design_update["video_font_apply_all"] = False

        import os
        import shutil

        # ---- Move uploaded videos from tmp ----
        tmp_key = session.pop("video_tmp_key", None)
        tmp_gallery = session.pop("video_tmp_gallery", [])
        session.modified = True

        dest_dir = os.path.join(root_path, "static", "uploads", "videos", new_qrcard_id)

        video_links = []
        
        if tmp_key and tmp_gallery:
            tmp_dir = os.path.join(root_path, "static", "uploads", "videos", "_tmp", tmp_key)
            os.makedirs(dest_dir, exist_ok=True)
            for f_info in tmp_gallery:
                if f_info.get("type") == "upload":
                    src = os.path.join(tmp_dir, f_info["safe_name"])
                    dst = os.path.join(dest_dir, f_info["safe_name"])
                    if os.path.exists(src):
                        shutil.move(src, dst)
                        video_links.append({
                            "url": f"/static/uploads/videos/{new_qrcard_id}/{f_info['safe_name']}",
                            "name": f_info.get("name", ""),
                            "desc": f_info.get("desc", ""),
                            "type": "upload"
                        })
                else:
                    video_links.append({
                        "url": f_info.get("url", ""),
                        "name": f_info.get("name", ""),
                        "desc": f_info.get("desc", ""),
                        "type": "link"
                    })
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        else:
            # Fallback if session wasn't fully processed
            url_list = request.form.getlist("video_url[]")
            name_list = request.form.getlist("video_name[]")
            desc_list = request.form.getlist("video_desc[]")
            from itertools import zip_longest
            for u, n, d in zip_longest(url_list, name_list, desc_list, fillvalue=""):
                if u.strip():
                    video_links.append({"url": u.strip(), "name": n.strip(), "desc": d.strip(), "type": "link"})

        # Store into main and video-specific collections
        full_update = {**about_update, **design_update, "video_links": video_links}
        self.mgdDB.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
        )
        self.mgdDB.db_qrcard_video.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
            upsert=True,
        )

        return {"success": True}
