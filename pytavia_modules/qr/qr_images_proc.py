import sys
import time
import uuid
import random
import string
import traceback
from datetime import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config  # noqa: F401
from storage import r2_storage_proc as r2_mod

SHORT_CODE_LENGTH = 8
SHORT_CODE_CHARS = string.ascii_lowercase + string.digits


def _schedule_date_for_html_input(val):
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    if "T" in s:
        return s.split("T", 1)[0][:10]
    return s


class qr_images_proc:
    """Standalone processor for images (image gallery) QR cards."""

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
        """Create a new images qrcard."""
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
            qrcard_rec["qr_type"] = "images"
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

            qrcard_rec["schedule_enabled"] = bool(params.get("schedule_enabled"))
            qrcard_rec["schedule_since"] = (params.get("schedule_since") or "").strip()
            qrcard_rec["schedule_until"] = (params.get("schedule_until") or "").strip()

            qrcard_rec["status"] = "ACTIVE"
            qrcard_rec["created_at"] = created_at
            qrcard_rec["timestamp"] = current_time

            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            images_rec = database.get_record("db_qrcard_images")
            images_rec["qrcard_id"] = qrcard_id
            images_rec["fk_user_id"] = fk_user_id
            images_rec["qr_type"] = "images"
            images_rec["name"] = name
            images_rec["url_content"] = url_content
            images_rec["short_code"] = short_code
            images_rec["stats"] = qrcard_rec.get("stats", {"scan_count": 0})
            images_rec["scan_limit_enabled"] = qrcard_rec.get("scan_limit_enabled", False)
            images_rec["scan_limit_value"] = qrcard_rec.get("scan_limit_value", 0)
            images_rec["schedule_enabled"] = qrcard_rec.get("schedule_enabled", False)
            images_rec["schedule_since"] = qrcard_rec.get("schedule_since", "")
            images_rec["schedule_until"] = qrcard_rec.get("schedule_until", "")
            images_rec["status"] = qrcard_rec.get("status", "ACTIVE")
            images_rec["created_at"] = created_at
            images_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard_images.insert_one(images_rec)

            # Also write summary index entry
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "images"
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
                    {"fk_user_id": fk_user_id, "qr_type": "images", "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )
        except Exception:
            self.webapp.logger.debug("qr_images_proc.get_qrcard_by_user failed", exc_info=True)
            return []

    def _merge_schedule_from_main_qrcard(self, fk_user_id, qrcard_id, doc):
        """Fill schedule on images row from db_qrcard when missing."""
        if not doc:
            return
        try:
            main = self.mgdDB.db_qrcard.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "images"}
            )
            if not main:
                return
            for sk in ("schedule_enabled", "schedule_since", "schedule_until"):
                if sk not in doc and sk in main:
                    doc[sk] = main[sk]
        except Exception:
            self.webapp.logger.debug("merge_schedule_from_main_qrcard failed", exc_info=True)

    def merge_stats_from_images_row(self, fk_user_id, qrcard_id, main_doc):
        """Draft design: fill schedule/scan on main dict from db_qrcard_images if missing."""
        if not main_doc:
            return
        try:
            row = self.mgdDB.db_qrcard_images.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
            )
            if not row:
                return
            for sk in ("schedule_enabled", "schedule_since", "schedule_until", "scan_limit_enabled", "scan_limit_value"):
                if sk not in main_doc and sk in row:
                    main_doc[sk] = row[sk]
        except Exception:
            self.webapp.logger.debug("merge_stats_from_images_row failed", exc_info=True)

    def get_qrcard(self, fk_user_id, qrcard_id):
        """Return images doc for edit."""
        try:
            doc = self.mgdDB.db_qrcard_images.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
            if doc:
                self._merge_schedule_from_main_qrcard(fk_user_id, qrcard_id, doc)
                for dk in ("schedule_since", "schedule_until"):
                    if doc.get(dk) not in (None, ""):
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
                return doc
            doc = self.mgdDB.db_qrcard.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "qr_type": "images",
                    "status": "ACTIVE",
                }
            )
            if doc:
                for dk in ("schedule_since", "schedule_until"):
                    if doc.get(dk) not in (None, ""):
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
            return doc
        except Exception:
            self.webapp.logger.debug("qr_images_proc.get_qrcard failed", exc_info=True)
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
                if key.startswith("images_") or key in ["welcome_time", "welcome_bg_color", "welcome_img_url"]:
                    update_data[key] = val

            if "scan_limit_enabled" in params:
                update_data["scan_limit_enabled"] = bool(params.get("scan_limit_enabled"))
            if "scan_limit_value" in params:
                try:
                    limit_raw = params.get("scan_limit_value", 0)
                    limit_val = int(limit_raw) if str(limit_raw).strip().isdigit() else 0
                    update_data["scan_limit_value"] = max(limit_val, 0)
                except Exception:
                    pass

            if "schedule_enabled" in params:
                update_data["schedule_enabled"] = bool(params.get("schedule_enabled"))
                update_data["schedule_since"] = (params.get("schedule_since") or "").strip()
                update_data["schedule_until"] = (params.get("schedule_until") or "").strip()

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
            self.mgdDB.db_qrcard_images.update_one(
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
            self.mgdDB.db_qrcard_images.update_one(
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

    def complete_images_save(self, request, session, root_path):
        """
        Full images save: build params, add_qrcard, then move uploads and update db_qrcard.
        Returns dict with success=True or success=False + form data for error re-render.
        """
        import os
        r2 = r2_mod.r2_storage_proc()
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated", "url_content": "", "qr_name": "", "short_code": "", "qr_encode_url": None}
        _url_content_raw = request.form.get("url_content", "").strip()
        params = {
            "fk_user_id": fk_user_id,
            "name": request.form.get("qr_name", "Untitled QR"),
            "url_content": _url_content_raw or config.G_BASE_URL.rstrip("/"),
            "short_code": (request.form.get("short_code") or "").strip().lower(),
        }
        params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
        params["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
        params["schedule_since"] = (request.form.get("schedule_since") or "").strip()
        params["schedule_until"] = (request.form.get("schedule_until") or "").strip()
        result = self.add_qrcard(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            sc = params.get("short_code") or ""
            base = config.G_BASE_URL
            encode = (base + "/images/" + sc) if sc else None
            return {
                "success": False,
                "error_msg": result.get("message_desc", "Save failed."),
                "url_content": request.form.get("url_content", ""),
                "qr_name": request.form.get("qr_name", ""),
                "short_code": sc,
                "qr_encode_url": encode,
            }
        new_qrcard_id = result["message_data"]["qrcard_id"]
        if not _url_content_raw:
            _qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": new_qrcard_id}, {"short_code": 1}) or {}
            _sc = _qrcard.get("short_code", "")
            if _sc:
                _real_url = config.G_BASE_URL.rstrip("/") + "/images/" + _sc
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})
                self.mgdDB.db_qrcard_images.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})

        # ---- Persist gallery info ----
        gallery_title = (request.form.get("images_gallery_title") or "").strip()
        gallery_desc = (request.form.get("images_gallery_desc") or "").strip()

        about_update = {
            "images_gallery_title": gallery_title,
            "images_gallery_desc": gallery_desc,
        }

        # Design fields from form
        design_update = {}
        for key in request.form:
            if key.startswith("images_") or key in ["welcome_time", "welcome_bg_color"]:
                if key.endswith("[]"):
                    continue
                val = request.form.get(key)
                if val is not None and str(val).strip() != "":
                    design_update[key] = str(val).strip()

        if request.form.get("images_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["images_font_apply_all"] = True
        else:
            design_update["images_font_apply_all"] = False

        if request.form.get("images_hide_labels") in ("on", "true", "1", "yes"):
            design_update["images_hide_labels"] = True
        else:
            design_update["images_hide_labels"] = False

        # Store into main and images-specific collections
        full_update = {**about_update, **design_update}
        self.mgdDB.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
        )
        self.mgdDB.db_qrcard_images.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
            upsert=True,
        )

        # ---- Move uploaded gallery images from tmp ----
        tmp_key = session.pop("images_tmp_key", None)
        tmp_gallery = session.pop("images_tmp_gallery", [])
        welcome_tmp_key = session.pop("welcome_img_tmp_key", None)
        welcome_tmp_name = session.pop("welcome_img_tmp_name", "welcome.jpg")
        session.modified = True

        # Welcome image
        if welcome_tmp_key:
            ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
            src_key = f"images/_tmp/{welcome_tmp_key}/{welcome_tmp_name}"
            dst_key = f"images/{new_qrcard_id}/welcome{ext}"
            try:
                welcome_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "images", "file_name": f"welcome{ext}"})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                self.mgdDB.db_qrcard_images.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
            except Exception:
                pass
        else:
            ac_welcome = (request.form.get("images_welcome_img_autocomplete_url", "")
                          or session.pop("images_welcome_img_autocomplete_url", "")).strip()
            if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                try:
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}})
                    self.mgdDB.db_qrcard_images.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}}, upsert=True)
                except Exception:
                    pass

        # Gallery images
        saved_gallery = []
        if tmp_key and tmp_gallery:
            for f_info in tmp_gallery:
                src_key = f"images/_tmp/{tmp_key}/{f_info['safe_name']}"
                dst_key = f"images/{new_qrcard_id}/{f_info['safe_name']}"
                try:
                    file_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "images", "file_name": f_info["safe_name"]})
                    saved_gallery.append({
                        "url": file_url,
                        "name": f_info.get("name", ""),
                        "desc": f_info.get("desc", ""),
                    })
                except Exception:
                    pass
            try:
                r2.delete_prefix(f"images/_tmp/{tmp_key}/")
            except Exception:
                pass

        if welcome_tmp_key and (not tmp_key or welcome_tmp_key != tmp_key):
            try:
                r2.delete_prefix(f"images/_tmp/{welcome_tmp_key}/")
            except Exception:
                pass

        # Autocomplete images (asset picker URLs or static paths) — always process alongside uploads
        ac_urls = request.form.getlist("images_autocomplete_urls[]") or session.pop("images_autocomplete_urls", []) or []
        ac_names = request.form.getlist("images_autocomplete_names[]") or session.pop("images_autocomplete_names", []) or []
        ac_descs = request.form.getlist("images_autocomplete_descs[]") or session.pop("images_autocomplete_descs", []) or []
        for i, ac_url in enumerate(ac_urls):
            if not ac_url:
                continue
            if ac_url.startswith("http://") or ac_url.startswith("https://"):
                entry = {"url": ac_url, "name": (ac_names[i] if i < len(ac_names) else ""), "desc": (ac_descs[i] if i < len(ac_descs) else "")}
                saved_gallery.append(entry)
                continue
            if not ac_url.startswith("/static/"):
                continue
            local_path = os.path.join(root_path or config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                try:
                    ext = os.path.splitext(local_path)[1].lower() or ".png"
                    safe_name = uuid.uuid4().hex + ext
                    with open(local_path, "rb") as f:
                        file_url = r2.upload_bytes(f.read(), f"images/{new_qrcard_id}/{safe_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "images", "file_name": safe_name})
                    entry = {"url": file_url, "name": (ac_names[i] if i < len(ac_names) else ""), "desc": (ac_descs[i] if i < len(ac_descs) else "")}
                    saved_gallery.append(entry)
                except Exception:
                    pass

        if saved_gallery:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
                {"$set": {"images_gallery_files": saved_gallery}},
            )
            self.mgdDB.db_qrcard_images.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
                {"$set": {"images_gallery_files": saved_gallery}},
                upsert=True,
            )
        return {"success": True, "qrcard_id": new_qrcard_id}

    def save_draft(self, request, session, root_path=None):
        """Create images QR as DRAFT: calls complete_images_save then downgrades status."""
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"status": "error", "message_desc": "Not authenticated"}
        qr_name = (request.form.get("qr_name") or "Untitled QR").strip()
        # Delete orphaned DRAFTs with same name
        try:
            old_drafts = list(self.mgdDB.db_qrcard.find(
                {"fk_user_id": fk_user_id, "name": qr_name, "status": "DRAFT"},
                {"qrcard_id": 1}
            ))
            if old_drafts:
                old_ids = [d["qrcard_id"] for d in old_drafts]
                self.mgdDB.db_qrcard.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qrcard_images.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_images_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_images.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/images/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}
