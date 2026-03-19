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


class qr_sosmed_proc:
    """Standalone processor for Sosmed QR cards."""

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
            return self.mgdDB.db_qrcard.find_one(query) is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def add_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            name = params.get("name", "Untitled QR")
            url_content = params.get("url_content", "")
            short_code = (params.get("short_code") or "").strip().lower()

            if not fk_user_id:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "User authentication required.", "message_data": {}}
            if not url_content:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "URL Content is required.", "message_data": {}}

            import re
            if short_code:
                if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                    return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces.", "message_data": {}}
                if not self.is_short_code_unique(short_code):
                    return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "This address identifier is already in use. Please choose another.", "message_data": {}}
            else:
                for _ in range(20):
                    short_code = self._generate_short_code()
                    if self.is_short_code_unique(short_code):
                        break
                else:
                    return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "Could not generate a unique code.", "message_data": {}}

            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            qrcard_rec = {
                "qrcard_id": qrcard_id,
                "fk_user_id": fk_user_id,
                "qr_type": "sosmed",
                "name": name,
                "url_content": url_content,
                "short_code": short_code,
                "design_data": {},
                "qr_image_url": "",
                "stats": {"scan_count": 0},
                "scan_limit_enabled": bool(params.get("scan_limit_enabled", False)),
                "scan_limit_value": max(int(params.get("scan_limit_value", 0)) if str(params.get("scan_limit_value", 0)).strip().isdigit() else 0, 0),
                "status": "ACTIVE",
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            sosmed_rec = dict(qrcard_rec)
            self.mgdDB.db_qrcard_sosmed.insert_one(sosmed_rec)

            idx = {
                "qrcard_id": qrcard_id,
                "fk_user_id": fk_user_id,
                "qr_type": "sosmed",
                "name": name,
                "short_code": short_code,
                "status": "ACTIVE",
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qr_index.insert_one(idx)

            return {"message_action": "ADD_QRCARD_SUCCESS", "message_desc": "QR card saved.", "message_data": {"qrcard_id": qrcard_id}}
        except Exception:
            err = traceback.format_exc()
            self.webapp.logger.debug(err)
            return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "An internal error occurred.", "message_data": {}}

    def get_qrcard(self, fk_user_id, qrcard_id):
        try:
            doc = self.mgdDB.db_qrcard_sosmed.find_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"})
            if doc:
                return doc
            return self.mgdDB.db_qrcard.find_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed", "status": "ACTIVE"})
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def edit_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            update_data = {"name": params.get("name"), "url_content": params.get("url_content")}

            for key, val in params.items():
                if key.startswith("Sosmed_") or key in ["welcome_time", "welcome_bg_color", "welcome_img_url"]:
                    update_data[key] = val

            if "scan_limit_enabled" in params:
                update_data["scan_limit_enabled"] = bool(params.get("scan_limit_enabled"))
            if "scan_limit_value" in params:
                try:
                    lv = int(params.get("scan_limit_value", 0)) if str(params.get("scan_limit_value", 0)).strip().isdigit() else 0
                    update_data["scan_limit_value"] = max(lv, 0)
                except Exception:
                    pass

            doc = self.get_qrcard(fk_user_id, qrcard_id)
            if doc:
                import re
                new_sc = (params.get("short_code") or "").strip().lower()
                cur_sc = (doc.get("short_code") or "").strip().lower()
                if new_sc and new_sc != cur_sc:
                    if re.match(r"^[a-z0-9_-]{2,32}$", new_sc) and self.is_short_code_unique(new_sc, exclude_qrcard_id=qrcard_id):
                        update_data["short_code"] = new_sc

            self.mgdDB.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data})
            self.mgdDB.db_qrcard_sosmed.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data}, upsert=True)

            idx_update = {}
            if "name" in update_data:
                idx_update["name"] = update_data["name"]
            if "short_code" in update_data:
                idx_update["short_code"] = update_data["short_code"]
            if idx_update:
                self.mgdDB.db_qr_index.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": idx_update})

            return {"status": "SUCCESS", "message": "QR card updated."}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"status": "FAILED", "message": "Error updating QR card."}

    def delete_qrcard(self, fk_user_id, qrcard_id):
        try:
            self.mgdDB.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "DELETED"}})
            self.mgdDB.db_qrcard_sosmed.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "DELETED"}}, upsert=True)
            self.mgdDB.db_qr_index.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "DELETED"}})
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def complete_sosmed_save(self, request, session, root_path):
        """Full sosmed save: build params, add_qrcard, persist content + move uploads."""
        import os, shutil
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated", "url_content": "", "qr_name": "", "short_code": "", "qr_encode_url": None}

        params = {
            "fk_user_id": fk_user_id,
            "name": request.form.get("qr_name", "Untitled QR"),
            "url_content": request.form.get("url_content", ""),
            "short_code": (request.form.get("short_code") or "").strip().lower(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(v) if (v := (request.form.get("scan_limit_value") or "").strip()).isdigit() else 0,
        }

        result = self.add_qrcard(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            sc = params.get("short_code") or ""
            return {"success": False, "error_msg": result.get("message_desc", "Save failed."), "url_content": request.form.get("url_content", ""), "qr_name": request.form.get("qr_name", ""), "short_code": sc, "qr_encode_url": (config.G_BASE_URL + "/sosmed/" + sc) if sc else None}

        new_id = result["message_data"]["qrcard_id"]

        # Build sosmed items list
        icons = request.form.getlist("Sosmed_item_icon[]")
        names = request.form.getlist("Sosmed_item_name[]")
        descs = request.form.getlist("Sosmed_item_desc[]")
        items_list = []
        for ic, n, d in zip(icons, names, descs):
            n = (n or "").strip()
            if not n:
                continue
            items_list.append({"icon": (ic or "fa-solid fa-globe").strip(), "name": n, "desc": (d or "").strip()})

        content_update = {
            "Sosmed_title": (request.form.get("Sosmed_title") or "").strip(),
            "Sosmed_desc": (request.form.get("Sosmed_desc") or "").strip(),
            "Sosmed_items": items_list,
        }

        design_update = {}
        for key in request.form:
            if key.startswith("Sosmed_") and not key.endswith("[]") and key not in ["Sosmed_title", "Sosmed_desc"]:
                val = request.form.get(key)
                if val is not None:
                    design_update[key] = val.strip()
        if request.form.get("Sosmed_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["Sosmed_font_apply_all"] = True
        for key in ["welcome_time", "welcome_bg_color"]:
            if request.form.get(key):
                design_update[key] = request.form.get(key)

        full_update = {**content_update, **design_update}
        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": full_update})
        self.mgdDB.db_qrcard_sosmed.update_one({"qrcard_id": new_id}, {"$set": full_update}, upsert=True)

        dest_dir = os.path.join(root_path, "static", "uploads", "sosmed", new_id)
        welcome_tmp_key = session.pop("welcome_img_tmp_key", None)
        welcome_tmp_name = session.pop("welcome_img_tmp_name", "welcome.jpg")
        cover_tmp_key = session.pop("cover_img_tmp_key", None)
        cover_tmp_name = session.pop("cover_img_tmp_name", "sosmed_cover_img.jpg")
        session.modified = True

        if welcome_tmp_key:
            tmp_dir_w = os.path.join(root_path, "static", "uploads", "sosmed", "_tmp", welcome_tmp_key)
            src = os.path.join(tmp_dir_w, welcome_tmp_name)
            if os.path.exists(src):
                os.makedirs(dest_dir, exist_ok=True)
                ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
                shutil.move(src, os.path.join(dest_dir, "welcome" + ext))
                welcome_url = f"/static/uploads/sosmed/{new_id}/welcome{ext}"
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                self.mgdDB.db_qrcard_sosmed.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)

        if cover_tmp_key:
            tmp_dir_c = os.path.join(root_path, "static", "uploads", "sosmed", "_tmp", cover_tmp_key)
            src = os.path.join(tmp_dir_c, cover_tmp_name)
            if os.path.exists(src):
                os.makedirs(dest_dir, exist_ok=True)
                ext = os.path.splitext(cover_tmp_name)[1] or ".jpg"
                shutil.move(src, os.path.join(dest_dir, "sosmed_cover_img" + ext))
                cover_url = f"/static/uploads/sosmed/{new_id}/sosmed_cover_img{ext}"
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Sosmed_cover_img_url": cover_url}})
                self.mgdDB.db_qrcard_sosmed.update_one({"qrcard_id": new_id}, {"$set": {"Sosmed_cover_img_url": cover_url}}, upsert=True)

        return {"success": True, "qrcard_id": new_id}
