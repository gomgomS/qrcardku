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


class qr_ecard_proc:
    """Standalone processor for e-card QR cards."""

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
        """Create a new e-card qrcard."""
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
            qrcard_rec["qr_type"] = "ecard"
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

            ecard_rec = database.get_record("db_qrcard_ecard")
            ecard_rec["qrcard_id"] = qrcard_id
            ecard_rec["fk_user_id"] = fk_user_id
            ecard_rec["qr_type"] = "ecard"
            ecard_rec["name"] = name
            ecard_rec["url_content"] = url_content
            ecard_rec["short_code"] = short_code
            ecard_rec["stats"] = qrcard_rec.get("stats", {"scan_count": 0})
            ecard_rec["scan_limit_enabled"] = qrcard_rec.get("scan_limit_enabled", False)
            ecard_rec["scan_limit_value"] = qrcard_rec.get("scan_limit_value", 0)
            ecard_rec["schedule_enabled"] = qrcard_rec.get("schedule_enabled", False)
            ecard_rec["schedule_since"] = qrcard_rec.get("schedule_since", "")
            ecard_rec["schedule_until"] = qrcard_rec.get("schedule_until", "")
            ecard_rec["status"] = qrcard_rec.get("status", "ACTIVE")
            ecard_rec["created_at"] = created_at
            ecard_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard_ecard.insert_one(ecard_rec)

            # Also write summary index entry
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "ecard"
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
                    {"fk_user_id": fk_user_id, "qr_type": "ecard", "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )
        except Exception:
            self.webapp.logger.debug("qr_ecard_proc.get_qrcard_by_user failed", exc_info=True)
            return []

    def get_qrcard(self, fk_user_id, qrcard_id):
        """Return ecard doc for edit (same pattern as PDF: type-specific collection first)."""
        try:
            doc = self.mgdDB.db_qrcard_ecard.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
            base_doc = self.mgdDB.db_qrcard.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "qr_type": "ecard",
                    "status": "ACTIVE",
                }
            )
            if doc and base_doc:
                for key in [
                    "qr_image_url",
                    "qr_composite_url",
                    "frame_id",
                    "url_content",
                    "name",
                    "short_code",
                    "scan_limit_enabled",
                    "scan_limit_value",
                    "schedule_enabled",
                    "schedule_since",
                    "schedule_until",
                ]:
                    if key in base_doc:
                        doc[key] = base_doc[key]
                for dk in ("schedule_since", "schedule_until"):
                    if dk in doc and doc[dk] is not None and doc[dk] != "":
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
                return doc
            if doc:
                for dk in ("schedule_since", "schedule_until"):
                    if dk in doc and doc[dk] is not None and doc[dk] != "":
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
                return doc
            if base_doc:
                for dk in ("schedule_since", "schedule_until"):
                    if dk in base_doc and base_doc[dk] is not None and base_doc[dk] != "":
                        base_doc[dk] = _schedule_date_for_html_input(base_doc[dk])
            return base_doc
        except Exception:
            self.webapp.logger.debug("qr_ecard_proc.get_qrcard failed", exc_info=True)
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
                if key.startswith("E-card_") or key in ["welcome_time", "welcome_bg_color", "welcome_img_url", "E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    update_data[key] = val

            # Support asset-picker fields in edit flow (same output fields as "new")
            cover_ac = (params.get("ecard_cover_img_autocomplete_url") or "").strip()
            if cover_ac:
                update_data["E-card_t1_header_img_url"] = cover_ac
                update_data["E-card_t3_circle_img_url"] = cover_ac
                update_data["E-card_t4_circle_img_url"] = cover_ac
            welcome_ac = (params.get("ecard_welcome_img_autocomplete_url") or "").strip()
            if welcome_ac:
                update_data["welcome_img_url"] = welcome_ac
            gallery_ac = params.get("ecard_gallery_autocomplete_url[]") or params.get("ecard_gallery_autocomplete_url") or []
            if isinstance(gallery_ac, str):
                gallery_ac = [gallery_ac]
            gallery_ac = [{"url": (u or "").strip()} for u in gallery_ac if (u or "").strip()]
            if gallery_ac:
                update_data["ecard_gallery_files"] = gallery_ac

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
            self.mgdDB.db_qrcard_ecard.update_one(
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
            self.mgdDB.db_qrcard_ecard.update_one(
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

    def complete_ecard_save(self, request, session, root_path):
        """
        Full e-card save: build params, add_qrcard, then move uploads and update db_qrcard.
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
            encode = (base + "/ecard/" + sc) if sc else None
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
                _real_url = config.G_BASE_URL.rstrip("/") + "/ecard/" + _sc
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})
                self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})

        # ---- Persist About You + contact info into db_qrcard and db_qrcard_ecard ----
        company = (request.form.get("E-card_company") or "").strip()
        title = (request.form.get("E-card_title") or "").strip()
        desc = (request.form.get("E-card_desc") or "").strip()
        btn_text = (request.form.get("E-card_btn_text") or "").strip()

        # Build structured contact lists
        def _build_contact_list(label_key, value_key):
            labels = request.form.getlist(label_key)
            values = request.form.getlist(value_key)
            items = []
            for lbl, val in zip(labels, values):
                lbl = (lbl or "").strip()
                val = (val or "").strip()
                if not val:
                    continue
                items.append({"label": lbl, "value": val})
            return items

        phones = []
        phone_labels = request.form.getlist("E-card_phone_label[]")
        phone_numbers = request.form.getlist("E-card_phone_number[]")
        for lbl, num in zip(phone_labels, phone_numbers):
            lbl = (lbl or "").strip()
            num = (num or "").strip()
            if not num:
                continue
            phones.append({"label": lbl, "number": num})

        emails = _build_contact_list("E-card_email_label[]", "E-card_email_value[]")
        websites = _build_contact_list("E-card_website_label[]", "E-card_website_value[]")

        # Backwards‑compat main website field: use first website contact's value, if any
        main_website = ""
        if websites:
            main_website = websites[0].get("value", "").strip()

        about_update = {
            "E-card_company": company,
            "E-card_title": title,
            "E-card_desc": desc,
            "E-card_website": main_website,
            "E-card_btn_text": btn_text or "See E-card",
            "E-card_phones": phones,
            "E-card_emails": emails,
            "E-card_websites": websites,
        }

        # Design fields from design step form (template, colors, fonts, welcome)
        design_update = {}
        for key in request.form:
            if key.startswith("E-card_") or key in ["welcome_time", "welcome_bg_color", "E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                if key.endswith("[]"):
                    continue
                val = request.form.get(key)
                if val is not None and str(val).strip() != "":
                    design_update[key] = str(val).strip()
                    
        if request.form.get("E-card_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["E-card_font_apply_all"] = True
        else:
            design_update["E-card_font_apply_all"] = False

        # Store into main and ecard-specific collections
        full_update = {**about_update, **design_update}
        self.mgdDB.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
        )
        self.mgdDB.db_qrcard_ecard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
            {"$set": full_update},
            upsert=True,
        )
        tmp_key = session.pop("pdf_tmp_key", None)
        tmp_files = session.pop("pdf_tmp_files", [])
        welcome_tmp_key = session.pop("welcome_img_tmp_key", None)
        welcome_tmp_name = session.pop("welcome_img_tmp_name", "welcome.jpg")
        cover_tmp_key = session.pop("cover_img_tmp_key", None)
        cover_tmp_name = session.pop("cover_img_tmp_name", "pdf_cover_img.jpg")
        saved_display_names = session.pop("pdf_display_names", [])
        saved_item_descs = session.pop("pdf_item_descs", [])
        gallery_tmp_files = session.pop("ecard_gallery_tmp_files", [])
        session.modified = True
        if welcome_tmp_key:
            ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
            src_key = f"ecard/_tmp/{welcome_tmp_key}/{welcome_tmp_name}"
            dst_key = f"ecard/{new_qrcard_id}/welcome{ext}"
            try:
                welcome_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": f"welcome{ext}"})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
            except Exception:
                pass
        else:
            # Priority: direct file upload from request (when user uploads their own welcome image)
            _direct_welcome = request.files.get("E-card_welcome_img") if request.files else None
            if _direct_welcome and _direct_welcome.filename:
                _direct_welcome.seek(0, 2)
                _dw_size = _direct_welcome.tell()
                _direct_welcome.seek(0)
                if _dw_size <= 1 * 1024 * 1024:
                    _dw_ext = os.path.splitext(_direct_welcome.filename)[1].lower() or ".jpg"
                    if _dw_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        _dw_ext = ".jpg"
                    _dw_name = f"welcome_{uuid.uuid4().hex[:12]}{_dw_ext}"
                    try:
                        welcome_url = r2.upload_file(_direct_welcome, f"ecard/{new_qrcard_id}/{_dw_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": _dw_name})
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                        self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                    except Exception:
                        pass
            else:
                # Handle autocomplete/static welcome image selection
                ac_welcome = (request.form.get("ecard_welcome_img_autocomplete_url", "")
                              or session.pop("ecard_welcome_img_autocomplete_url", "")).strip()
                if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                    try:
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}})
                        self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}}, upsert=True)
                    except Exception:
                        pass
                elif ac_welcome and ac_welcome.startswith("/static/"):
                    import os as _os
                    ext = _os.path.splitext(ac_welcome)[1] or ".jpg"
                    local_path = _os.path.join(root_path or config.G_HOME_PATH, ac_welcome.lstrip("/").replace("/", _os.sep))
                    if _os.path.isfile(local_path):
                        try:
                            unique_welcome_name = f"welcome_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as f:
                                welcome_url = r2.upload_bytes(f.read(), f"ecard/{new_qrcard_id}/{unique_welcome_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": unique_welcome_name})
                            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                            self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                        except Exception:
                            pass
        if cover_tmp_key:
            ext = os.path.splitext(cover_tmp_name)[1] or ".jpg"
            src_key = f"ecard/_tmp/{cover_tmp_key}/{cover_tmp_name}"
            unique_cover_name = f"profile_img_{uuid.uuid4().hex[:12]}{ext}"
            dst_key = f"ecard/{new_qrcard_id}/{unique_cover_name}"
            try:
                cover_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": unique_cover_name})
                self.mgdDB.db_qrcard.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}},
                )
                self.mgdDB.db_qrcard_ecard.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}},
                    upsert=True,
                )
            except Exception:
                pass
        else:
            # Priority: direct file upload from request (when user uploads their own profile image)
            _direct_cover = request.files.get("E-card_profile_img") if request.files else None
            if _direct_cover and _direct_cover.filename:
                _direct_cover.seek(0, 2)
                _dc_size = _direct_cover.tell()
                _direct_cover.seek(0)
                if _dc_size <= 2 * 1024 * 1024:
                    _dc_ext = os.path.splitext(_direct_cover.filename)[1].lower() or ".jpg"
                    if _dc_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        _dc_ext = ".jpg"
                    _dc_name = f"profile_img_{uuid.uuid4().hex[:12]}{_dc_ext}"
                    try:
                        cover_url = r2.upload_file(_direct_cover, f"ecard/{new_qrcard_id}/{_dc_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": _dc_name})
                        img_update = {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update})
                        self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update}, upsert=True)
                    except Exception:
                        pass
            else:
                # Handle autocomplete image (asset picker or legacy static path)
                ac_url = (request.form.get("ecard_cover_img_autocomplete_url", "")
                          or session.pop("ecard_cover_img_autocomplete_url", "")).strip()
                if ac_url and (ac_url.startswith("http://") or ac_url.startswith("https://")):
                    # Existing R2 asset URL — store directly, no re-upload
                    try:
                        img_update = {"E-card_t1_header_img_url": ac_url, "E-card_t3_circle_img_url": ac_url, "E-card_t4_circle_img_url": ac_url}
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update})
                        self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update}, upsert=True)
                    except Exception:
                        pass
                elif ac_url and ac_url.startswith("/static/"):
                    import os as _os
                    ext = _os.path.splitext(ac_url)[1] or ".jpg"
                    local_path = _os.path.join(root_path or config.G_HOME_PATH, ac_url.lstrip("/").replace("/", _os.sep))
                    if _os.path.isfile(local_path):
                        try:
                            unique_cover_name = f"profile_img_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as f:
                                cover_url = r2.upload_bytes(f.read(), f"ecard/{new_qrcard_id}/{unique_cover_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": unique_cover_name})
                            img_update = {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}
                            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update})
                            self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": img_update}, upsert=True)
                        except Exception:
                            pass
        saved_files = []
        if tmp_key and tmp_files:
            for idx, f_info in enumerate(tmp_files):
                src_key = f"ecard/_tmp/{tmp_key}/{f_info['safe_name']}"
                dst_key = f"ecard/{new_qrcard_id}/{f_info['safe_name']}"
                try:
                    file_url = r2.move_file(src_key, dst_key)
                    entry = {"name": f_info["name"], "url": file_url}
                    if idx < len(saved_display_names) and saved_display_names[idx].strip():
                        entry["display_name"] = saved_display_names[idx].strip()
                    if idx < len(saved_item_descs):
                        entry["item_desc"] = saved_item_descs[idx].strip()
                    saved_files.append(entry)
                except Exception:
                    pass
            try:
                r2.delete_prefix(f"ecard/_tmp/{tmp_key}/")
            except Exception:
                pass
        elif tmp_key:
            try:
                r2.delete_prefix(f"ecard/_tmp/{tmp_key}/")
            except Exception:
                pass
        if welcome_tmp_key and (not tmp_key or welcome_tmp_key != tmp_key):
            try:
                r2.delete_prefix(f"ecard/_tmp/{welcome_tmp_key}/")
            except Exception:
                pass
        if saved_files:
            # For e-card we keep legacy pdf_files on main doc for reuse,
            # but normalized list lives under E-card_files in db_qrcard_ecard.
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
                {"$set": {"pdf_files": saved_files}},
            )
            self.mgdDB.db_qrcard_ecard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id},
                {"$set": {"E-card_files": saved_files}},
                upsert=True,
            )
        # Handle gallery images
        saved_gallery = []
        # Real uploaded files (moved from tmp storage)
        for g_info in gallery_tmp_files:
            g_tmp_key = g_info.get("tmp_key")
            g_safe_name = g_info.get("safe_name")
            if not g_tmp_key or not g_safe_name:
                continue
            src_key = f"ecard/_tmp/{g_tmp_key}/{g_safe_name}"
            dst_key = f"ecard/{new_qrcard_id}/gallery/{g_safe_name}"
            try:
                file_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": g_safe_name})
                saved_gallery.append({"url": file_url})
            except Exception:
                pass
        # Autocomplete gallery images (asset picker URLs or static paths)
        ac_gallery_urls = request.form.getlist("ecard_gallery_autocomplete_url[]")
        for ac_url in ac_gallery_urls:
            if not ac_url:
                continue
            if ac_url.startswith("http://") or ac_url.startswith("https://"):
                saved_gallery.append({"url": ac_url})
                continue
            if not ac_url.startswith("/static/"):
                continue
            _ext = os.path.splitext(ac_url)[1] or ".jpg"
            local_path = os.path.join(root_path or config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                try:
                    safe_name = uuid.uuid4().hex + _ext
                    with open(local_path, "rb") as f:
                        file_url = r2.upload_bytes(f.read(), f"ecard/{new_qrcard_id}/gallery/{safe_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "ecard", "file_name": safe_name})
                    saved_gallery.append({"url": file_url})
                except Exception:
                    pass
        if saved_gallery:
            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}})
            self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}}, upsert=True)

        return {"success": True, "qrcard_id": new_qrcard_id}

    def save_draft(self, request, session, root_path=None):
        """Create ecard QR as DRAFT: calls complete_ecard_save then downgrades status."""
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
                self.mgdDB.db_qrcard_ecard.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_ecard_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/ecard/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}

