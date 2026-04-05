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
    """HTML date inputs need YYYY-MM-DD; Mongo may store datetime or ISO strings."""
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


PDF_FIELDS = [
    "pdf_template", "pdf_primary_color", "pdf_secondary_color",
    "pdf_title_font", "pdf_title_color", "pdf_text_font",
    "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
    "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
    "welcome_img_url", "pdf_font_apply_all",
    "pdf_t1_header_img_url", "pdf_t3_circle_img_url", "pdf_t4_circle_img_url",
]


class qr_pdf_proc:
    """Standalone processor for PDF-type QR cards."""

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
        """Create a new PDF qrcard and mirror into db_qrcard_pdf."""
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
            qrcard_rec["qr_type"] = "pdf"
            qrcard_rec["name"] = name
            qrcard_rec["url_content"] = url_content
            qrcard_rec["short_code"] = short_code
            qrcard_rec["design_data"] = {}
            qrcard_rec["qr_image_url"] = ""

            for f in PDF_FIELDS:
                if f in params:
                    qrcard_rec[f] = params.get(f, "")

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

            pdf_rec = database.get_record("db_qrcard_pdf")
            pdf_rec["qrcard_id"] = qrcard_id
            pdf_rec["fk_user_id"] = fk_user_id
            pdf_rec["qr_type"] = "pdf"
            pdf_rec["name"] = name
            pdf_rec["url_content"] = url_content
            pdf_rec["short_code"] = short_code
            for f in PDF_FIELDS:
                pdf_rec[f] = qrcard_rec.get(f, params.get(f, ""))
            pdf_rec["stats"] = qrcard_rec.get("stats", {"scan_count": 0})
            pdf_rec["scan_limit_enabled"] = qrcard_rec.get("scan_limit_enabled", False)
            pdf_rec["scan_limit_value"] = qrcard_rec.get("scan_limit_value", 0)
            pdf_rec["schedule_enabled"] = qrcard_rec.get("schedule_enabled", False)
            pdf_rec["schedule_since"] = qrcard_rec.get("schedule_since", "")
            pdf_rec["schedule_until"] = qrcard_rec.get("schedule_until", "")
            pdf_rec["status"] = qrcard_rec.get("status", "ACTIVE")
            pdf_rec["created_at"] = created_at
            pdf_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard_pdf.insert_one(pdf_rec)

            # Also write summary index entry
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "pdf"
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
                self.mgdDB.db_qrcard_pdf.find(
                    {"fk_user_id": fk_user_id, "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )
        except Exception:
            self.webapp.logger.debug("qr_pdf_proc.get_qrcard_by_user failed", exc_info=True)
            return []

    def get_qrcard(self, fk_user_id, qrcard_id):
        try:
            doc = self.mgdDB.db_qrcard_pdf.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "status": "ACTIVE",
                }
            )
            base_doc = self.mgdDB.db_qrcard.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "status": "ACTIVE",
                }
            )
            if doc and base_doc:
                for key in ["qr_image_url", "qr_composite_url", "frame_id", "url_content", "name", "short_code"]:
                    if key in base_doc:
                        doc[key] = base_doc[key]
                # Schedule is mirrored on both collections; prefer db_qrcard if pdf doc is missing/stale.
                for sk in ("schedule_enabled", "schedule_since", "schedule_until"):
                    if sk in base_doc:
                        doc[sk] = base_doc[sk]
                for dk in ("schedule_since", "schedule_until"):
                    if doc.get(dk) not in (None, ""):
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
                return doc
            if doc:
                for dk in ("schedule_since", "schedule_until"):
                    if doc.get(dk) not in (None, ""):
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
                return doc
            if base_doc:
                for dk in ("schedule_since", "schedule_until"):
                    if base_doc.get(dk) not in (None, ""):
                        base_doc[dk] = _schedule_date_for_html_input(base_doc[dk])
            return base_doc
        except Exception:
            self.webapp.logger.debug("qr_pdf_proc.get_qrcard failed", exc_info=True)
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
            for f in PDF_FIELDS:
                if f in params:
                    update_data[f] = params.get(f)

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

            # Handle welcome image asset URL when editing (no upload in this method)
            ac_welcome = (params.get("welcome_img_autocomplete_url") or "").strip()
            if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                update_data["welcome_img_url"] = ac_welcome

            # Handle cover image asset URL when editing (no upload in this method)
            ac_cover = (params.get("pdf_t1_header_img_autocomplete_url") or "").strip()
            if ac_cover and (ac_cover.startswith("http://") or ac_cover.startswith("https://")):
                update_data["pdf_t1_header_img_url"] = ac_cover
                update_data["pdf_t3_circle_img_url"] = ac_cover
                update_data["pdf_t4_circle_img_url"] = ac_cover

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

            pdf_update = {
                "name": name,
                "url_content": url_content,
            }
            for f in PDF_FIELDS:
                if f in update_data:
                    pdf_update[f] = update_data[f]
            if "short_code" in update_data:
                pdf_update["short_code"] = update_data["short_code"]
            if "scan_limit_enabled" in update_data:
                pdf_update["scan_limit_enabled"] = update_data["scan_limit_enabled"]
            if "scan_limit_value" in update_data:
                pdf_update["scan_limit_value"] = update_data["scan_limit_value"]
            if "schedule_enabled" in update_data:
                pdf_update["schedule_enabled"] = update_data["schedule_enabled"]
                pdf_update["schedule_since"] = update_data.get("schedule_since", "")
                pdf_update["schedule_until"] = update_data.get("schedule_until", "")

            self.mgdDB.db_qrcard_pdf.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": pdf_update},
                upsert=True,
            )
            # Keep db_qr_index in sync for listing (name, short_code)
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

    def update_pdf_files(self, fk_user_id, qrcard_id, pdf_files_list):
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"pdf_files": pdf_files_list}},
            )
            self.mgdDB.db_qrcard_pdf.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"pdf_files": pdf_files_list}},
                upsert=True,
            )
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def remove_pdf_file(self, fk_user_id, qrcard_id, file_url):
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$pull": {"pdf_files": {"url": file_url}}},
            )
            self.mgdDB.db_qrcard_pdf.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$pull": {"pdf_files": {"url": file_url}}},
            )
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def complete_pdf_save(self, request, session, root_path):
        """
        Full PDF save flow: build params from request, add_qrcard, then move uploads
        and update DB. Returns dict with success=True or success=False + error/form data.
        """
        r2 = r2_mod.r2_storage_proc()
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated", "url_content": "", "qr_name": "", "short_code": "", "qr_encode_url": None, "pdf_data": {}}

        _url_content_raw = request.form.get("url_content", "").strip()
        params = {
            "fk_user_id": fk_user_id,
            "qr_type": "pdf",
            "name": request.form.get("qr_name", "Untitled QR"),
            "url_content": _url_content_raw or config.G_BASE_URL.rstrip("/"),
            "short_code": (request.form.get("short_code") or "").strip().lower(),
            "pdf_template": request.form.get("pdf_template", "default"),
            "pdf_primary_color": request.form.get("pdf_primary_color", "#2F6BFD"),
            "pdf_secondary_color": request.form.get("pdf_secondary_color", "#0E379A"),
            "pdf_title_font": request.form.get("pdf_title_font", "Lato"),
            "pdf_title_color": request.form.get("pdf_title_color", "#000000"),
            "pdf_text_font": request.form.get("pdf_text_font", "Lato"),
            "pdf_text_color": request.form.get("pdf_text_color", "#000000"),
            "pdf_company": request.form.get("pdf_company", ""),
            "pdf_title": request.form.get("pdf_title", ""),
            "pdf_desc": request.form.get("pdf_desc", ""),
            "pdf_website": request.form.get("pdf_website", ""),
            "pdf_btn_text": request.form.get("pdf_btn_text", "See PDF"),
            "welcome_time": request.form.get("welcome_time", "5.0"),
            "welcome_bg_color": request.form.get("welcome_bg_color", "#2F6BFD"),
            "pdf_font_apply_all": request.form.get("pdf_font_apply_all", ""),
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
            encode = (base + "/pdf/" + sc) if sc else None
            pdf_field_names = [
                "pdf_template", "pdf_primary_color", "pdf_secondary_color",
                "pdf_title_font", "pdf_title_color", "pdf_text_font",
                "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                "pdf_font_apply_all",
            ]
            pdf_data = {f: request.form.get(f, "") for f in pdf_field_names}
            pdf_data["scan_limit_enabled"] = request.form.get("scan_limit_enabled", "")
            pdf_data["scan_limit_value"] = request.form.get("scan_limit_value", "")
            return {
                "success": False,
                "error_msg": result.get("message_desc", "Save failed."),
                "url_content": request.form.get("url_content", ""),
                "qr_name": request.form.get("qr_name", ""),
                "short_code": sc,
                "qr_encode_url": encode,
                "pdf_data": pdf_data,
            }

        new_qrcard_id = result["message_data"]["qrcard_id"]
        if not _url_content_raw:
            _qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": new_qrcard_id}, {"short_code": 1}) or {}
            _sc = _qrcard.get("short_code", "")
            if _sc:
                _real_url = config.G_BASE_URL.rstrip("/") + "/pdf/" + _sc
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})
                self.mgdDB.db_qrcard_pdf.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})
        tmp_key = session.pop("pdf_tmp_key", None)
        tmp_files = session.pop("pdf_tmp_files", [])
        welcome_tmp_key = session.pop("welcome_img_tmp_key", None)
        welcome_tmp_name = session.pop("welcome_img_tmp_name", "welcome.jpg")
        cover_tmp_key = session.pop("cover_img_tmp_key", None)
        cover_tmp_name = session.pop("cover_img_tmp_name", "pdf_cover_img.jpg")
        saved_display_names = request.form.getlist("pdf_display_names") or session.pop("pdf_display_names", []) or []
        saved_item_descs = request.form.getlist("pdf_item_descs") or session.pop("pdf_item_descs", []) or []
        session.modified = True

        import os

        if welcome_tmp_key:
            ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
            src_key = f"pdf/_tmp/{welcome_tmp_key}/{welcome_tmp_name}"
            dst_key = f"pdf/{new_qrcard_id}/welcome{ext}"
            try:
                welcome_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "pdf", "file_name": f"welcome{ext}"})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                self.mgdDB.db_qrcard_pdf.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            except Exception:
                pass
        else:
            ac_welcome = (request.form.get("welcome_img_autocomplete_url", "")
                          or session.pop("welcome_img_autocomplete_url", "")).strip()
            if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                try:
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}})
                    self.mgdDB.db_qrcard_pdf.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"welcome_img_url": ac_welcome}})
                except Exception:
                    pass
        if cover_tmp_key:
            ext = os.path.splitext(cover_tmp_name)[1] or ".jpg"
            src_key = f"pdf/_tmp/{cover_tmp_key}/{cover_tmp_name}"
            unique_cover_name = f"pdf_cover_img_{uuid.uuid4().hex[:12]}{ext}"
            dst_key = f"pdf/{new_qrcard_id}/{unique_cover_name}"
            try:
                cover_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "pdf", "file_name": unique_cover_name})
                self.mgdDB.db_qrcard.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"pdf_t1_header_img_url": cover_url, "pdf_t3_circle_img_url": cover_url, "pdf_t4_circle_img_url": cover_url}},
                )
                self.mgdDB.db_qrcard_pdf.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"pdf_t1_header_img_url": cover_url, "pdf_t3_circle_img_url": cover_url, "pdf_t4_circle_img_url": cover_url}},
                )
            except Exception:
                pass
        else:
            ac_cover = request.form.get("pdf_t1_header_img_autocomplete_url", "").strip() or session.pop("pdf_t1_header_img_autocomplete_url", "") or ""
            if ac_cover and (ac_cover.startswith("http://") or ac_cover.startswith("https://")):
                # Existing R2 asset URL — store directly, no re-upload
                try:
                    self.mgdDB.db_qrcard.update_one(
                        {"qrcard_id": new_qrcard_id},
                        {"$set": {"pdf_t1_header_img_url": ac_cover, "pdf_t3_circle_img_url": ac_cover, "pdf_t4_circle_img_url": ac_cover}},
                    )
                    self.mgdDB.db_qrcard_pdf.update_one(
                        {"qrcard_id": new_qrcard_id},
                        {"$set": {"pdf_t1_header_img_url": ac_cover, "pdf_t3_circle_img_url": ac_cover, "pdf_t4_circle_img_url": ac_cover}},
                    )
                except Exception:
                    pass
            elif ac_cover and ac_cover.startswith("/static/"):
                ext = os.path.splitext(ac_cover)[1] or ".jpg"
                local_path = os.path.join(root_path or config.G_HOME_PATH, ac_cover.lstrip("/").replace("/", os.sep))
                if os.path.isfile(local_path):
                    try:
                        unique_cover_name = f"pdf_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                        with open(local_path, "rb") as f:
                            cover_url = r2.upload_bytes(f.read(), f"pdf/{new_qrcard_id}/{unique_cover_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "pdf", "file_name": unique_cover_name})
                        self.mgdDB.db_qrcard.update_one(
                            {"qrcard_id": new_qrcard_id},
                            {"$set": {"pdf_t1_header_img_url": cover_url, "pdf_t3_circle_img_url": cover_url, "pdf_t4_circle_img_url": cover_url}},
                        )
                        self.mgdDB.db_qrcard_pdf.update_one(
                            {"qrcard_id": new_qrcard_id},
                            {"$set": {"pdf_t1_header_img_url": cover_url, "pdf_t3_circle_img_url": cover_url, "pdf_t4_circle_img_url": cover_url}},
                        )
                    except Exception:
                        pass
        saved_files = []
        if tmp_key and tmp_files:
            for idx, f_info in enumerate(tmp_files):
                src_key = f"pdf/_tmp/{tmp_key}/{f_info['safe_name']}"
                dst_key = f"pdf/{new_qrcard_id}/{f_info['safe_name']}"
                try:
                    file_url = r2.move_file(src_key, dst_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "pdf", "file_name": f_info["safe_name"]})
                    entry = {"name": f_info["name"], "url": file_url}
                    if idx < len(saved_display_names) and saved_display_names[idx].strip():
                        entry["display_name"] = saved_display_names[idx].strip()
                    if idx < len(saved_item_descs):
                        entry["item_desc"] = saved_item_descs[idx].strip()
                    saved_files.append(entry)
                except Exception:
                    pass
            try:
                r2.delete_prefix(f"pdf/_tmp/{tmp_key}/")
            except Exception:
                pass
        elif tmp_key:
            try:
                r2.delete_prefix(f"pdf/_tmp/{tmp_key}/")
            except Exception:
                pass
        if welcome_tmp_key and (not tmp_key or welcome_tmp_key != tmp_key):
            try:
                r2.delete_prefix(f"pdf/_tmp/{welcome_tmp_key}/")
            except Exception:
                pass
        if saved_files:
            self.update_pdf_files(fk_user_id, new_qrcard_id, saved_files)
        elif not saved_files:
            ac_pdf_urls = request.form.getlist("pdf_autocomplete_urls") or session.pop("pdf_autocomplete_urls", []) or []
            if ac_pdf_urls:
                ac_saved_files = []
                for i, ac_url in enumerate(ac_pdf_urls):
                    if not ac_url.startswith("/static/"):
                        continue
                    local_path = os.path.join(root_path or config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                    if os.path.isfile(local_path):
                        try:
                            fname = os.path.basename(local_path)
                            safe_name = fname.replace(" ", "_")
                            with open(local_path, "rb") as f:
                                file_url = r2.upload_bytes(f.read(), f"pdf/{new_qrcard_id}/{safe_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "pdf", "file_name": safe_name})
                            entry = {"name": fname, "url": file_url}
                            if i < len(saved_display_names) and saved_display_names[i].strip():
                                entry["display_name"] = saved_display_names[i].strip()
                            if i < len(saved_item_descs) and saved_item_descs[i].strip():
                                entry["item_desc"] = saved_item_descs[i].strip()
                            ac_saved_files.append(entry)
                        except Exception:
                            pass
                if ac_saved_files:
                    self.update_pdf_files(fk_user_id, new_qrcard_id, ac_saved_files)
        return {"success": True, "qrcard_id": new_qrcard_id}

    def save_draft(self, request, session, root_path=None):
        """Create pdf QR as DRAFT: calls complete_pdf_save then downgrades status."""
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
                self.mgdDB.db_qrcard_pdf.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_pdf_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_pdf.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/pdf/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}


    # ##### edit section pdf #####
    # Handles update (save from design step): updates db_qrcard, db_qrcard_pdf, db_qr_index; manages pdf_files.

    def complete_pdf_update(self, request, session, qrcard_id, root_path):
        """
        Full PDF update from design step: build params from request + draft, edit_qrcard (db_qrcard + db_qrcard_pdf + db_qr_index), merge pdf_files, clear draft.
        Returns {"success": True} or {"success": False, "error_msg": "..."}.
        """
        import os
        r2 = r2_mod.r2_storage_proc()
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated"}
        draft = (session.get("qr_draft") or {}).get(qrcard_id) or {}

        def _get_field(field, default=""):
            val = (request.form.get(field) or "").strip()
            if not val:
                val = draft.get(field, default)
            return val

        url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
        qrcard_for_save = self.get_qrcard(fk_user_id, qrcard_id)
        if "welcome_img_url" in draft:
            welcome_url = draft["welcome_img_url"]
        else:
            welcome_url = (qrcard_for_save.get("welcome_img_url") if qrcard_for_save else "") or ""
        cover_url = (
            draft.get("pdf_t1_header_img_url") or draft.get("pdf_t3_circle_img_url") or draft.get("pdf_t4_circle_img_url")
            or (qrcard_for_save.get("pdf_t1_header_img_url") if qrcard_for_save else "")
            or (qrcard_for_save.get("pdf_t3_circle_img_url") if qrcard_for_save else "")
            or (qrcard_for_save.get("pdf_t4_circle_img_url") if qrcard_for_save else "") or ""
        )
        params = {
            "fk_user_id": fk_user_id,
            "qrcard_id": qrcard_id,
            "name": qr_name,
            "url_content": url_content,
            "welcome_img_url": welcome_url,
            "pdf_t1_header_img_url": cover_url,
            "pdf_t3_circle_img_url": cover_url,
            "pdf_t4_circle_img_url": cover_url,
            "pdf_template": _get_field("pdf_template", "default"),
            "pdf_primary_color": _get_field("pdf_primary_color", "#2F6BFD"),
            "pdf_secondary_color": _get_field("pdf_secondary_color", "#0E379A"),
            "pdf_title_font": _get_field("pdf_title_font", "Lato"),
            "pdf_title_color": _get_field("pdf_title_color", "#000000"),
            "pdf_text_font": _get_field("pdf_text_font", "Lato"),
            "pdf_text_color": _get_field("pdf_text_color", "#000000"),
            "pdf_company": _get_field("pdf_company"),
            "pdf_title": _get_field("pdf_title"),
            "pdf_desc": _get_field("pdf_desc"),
            "pdf_website": _get_field("pdf_website"),
            "pdf_btn_text": _get_field("pdf_btn_text", "See PDF"),
            "welcome_time": _get_field("welcome_time", "5.0"),
            "welcome_bg_color": _get_field("welcome_bg_color", "#2F6BFD"),
            "pdf_font_apply_all": _get_field("pdf_font_apply_all", ""),
        }
        params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        if not raw_limit and "scan_limit_value" in draft:
            raw_limit = str(draft.get("scan_limit_value") or "")
        params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else int(draft.get("scan_limit_value", 0) or 0)
        params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
        params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
        params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()
        short_code_form = (request.form.get("short_code") or "").strip().lower()
        short_code_draft = (draft.get("short_code") or "").strip().lower()
        if short_code_form or short_code_draft:
            params["short_code"] = short_code_form or short_code_draft
        result = self.edit_qrcard(params)
        if result.get("status") != "SUCCESS":
            return {"success": False, "error_msg": result.get("message", "Update failed.")}
        existing_urls = request.form.getlist("existing_pdf_urls") or draft.get("pdf_existing_urls", [])
        display_names = request.form.getlist("pdf_display_names") or draft.get("pdf_display_names", [])
        item_descs = request.form.getlist("pdf_item_descs") or draft.get("pdf_item_descs", [])
        qrcard_db = self.get_qrcard(fk_user_id, qrcard_id)
        db_files = list(qrcard_db.get("pdf_files", [])) if qrcard_db else []
        if existing_urls:
            db_map = {f.get("url"): f for f in db_files}
            existing_files = []
            for i, url in enumerate(existing_urls):
                entry = dict(db_map.get(url, {"name": url.split("/")[-1], "url": url}))
                if i < len(display_names) and display_names[i].strip():
                    entry["display_name"] = display_names[i].strip()
                if i < len(item_descs):
                    entry["item_desc"] = item_descs[i].strip()
                existing_files.append(entry)
        else:
            existing_files = list(db_files)
        pdf_file_list = request.files.getlist("pdf_files")
        if pdf_file_list and any(f.filename for f in pdf_file_list):
            new_file_offset = len(existing_urls)
            new_file_idx = 0
            for f in pdf_file_list:
                if f and f.filename and f.filename.lower().endswith(".pdf"):
                    safe_name = f.filename.replace(" ", "_")
                    r2_key = f"pdf/{qrcard_id}/{safe_name}"
                    file_url = r2.upload_file(f, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf", "file_name": safe_name})
                    file_entry = {"name": f.filename, "url": file_url}
                    form_idx = new_file_offset + new_file_idx
                    if form_idx < len(display_names) and display_names[form_idx].strip():
                        file_entry["display_name"] = display_names[form_idx].strip()
                    if form_idx < len(item_descs) and item_descs[form_idx].strip():
                        file_entry["item_desc"] = item_descs[form_idx].strip()
                    new_file_idx += 1
                    if not any(x.get("name") == f.filename for x in existing_files):
                        existing_files.append(file_entry)
        if existing_files:
            self.update_pdf_files(fk_user_id, qrcard_id, existing_files)
        if "qr_draft" in session and qrcard_id in session.get("qr_draft", {}):
            del session["qr_draft"][qrcard_id]
            session.modified = True
        return {"success": True}

