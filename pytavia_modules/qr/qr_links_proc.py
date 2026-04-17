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


class qr_links_proc:
    """Standalone processor for Links QR cards."""

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
                    return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "Could not generate a unique code. Please try again.", "message_data": {}}

            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            qrcard_rec = {
                "qrcard_id": qrcard_id,
                "fk_user_id": fk_user_id,
                "qr_type": "links",
                "name": name,
                "url_content": url_content,
                "short_code": short_code,
                "design_data": {},
                "qr_image_url": "",
                "stats": {"scan_count": 0},
                "scan_limit_enabled": bool(params.get("scan_limit_enabled", False)),
                "scan_limit_value": max(int(params.get("scan_limit_value", 0)) if str(params.get("scan_limit_value", 0)).strip().isdigit() else 0, 0),
                "schedule_enabled": bool(params.get("schedule_enabled")),
                "schedule_since": (params.get("schedule_since") or "").strip(),
                "schedule_until": (params.get("schedule_until") or "").strip(),
                "status": "ACTIVE",
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            links_rec = dict(qrcard_rec)
            self.mgdDB.db_qrcard_links.insert_one(links_rec)

            idx = {
                "qrcard_id": qrcard_id,
                "fk_user_id": fk_user_id,
                "qr_type": "links",
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

    def get_qrcard(self, fk_user_id, qrcard_id, allow_draft=False):
        """Prefer links row; merge scan/schedule and shell fields from db_qrcard when both exist."""
        try:
            status_filter = {"$in": ["ACTIVE", "DRAFT"]} if allow_draft else "ACTIVE"
            doc = self.mgdDB.db_qrcard_links.find_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": status_filter})
            base_doc = self.mgdDB.db_qrcard.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links", "status": status_filter}
            )
            out = None
            if doc and base_doc:
                for sk in (
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
                    "stats",
                ):
                    if sk in base_doc:
                        doc[sk] = base_doc[sk]
                out = doc
            elif doc:
                out = doc
            else:
                out = base_doc
            if out:
                for dk in ("schedule_since", "schedule_until"):
                    if dk in out and out[dk] is not None and out[dk] != "":
                        out[dk] = _schedule_date_for_html_input(out[dk])
            return out
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def edit_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            update_data = {"name": params.get("name"), "url_content": params.get("url_content")}
            cover_ac_url = (params.get("links_cover_img_autocomplete_url") or "").strip()
            welcome_ac_url = (params.get("links_welcome_img_autocomplete_url") or "").strip()

            for key, val in params.items():
                if key.startswith("Links_") or key in ["welcome_time", "welcome_bg_color", "welcome_img_url"]:
                    update_data[key] = val
            if cover_ac_url and not update_data.get("Links_cover_img_url"):
                update_data["Links_cover_img_url"] = cover_ac_url
            if welcome_ac_url and not update_data.get("welcome_img_url"):
                update_data["welcome_img_url"] = welcome_ac_url

            if "scan_limit_enabled" in params:
                update_data["scan_limit_enabled"] = bool(params.get("scan_limit_enabled"))
            if "scan_limit_value" in params:
                try:
                    lv = int(params.get("scan_limit_value", 0)) if str(params.get("scan_limit_value", 0)).strip().isdigit() else 0
                    update_data["scan_limit_value"] = max(lv, 0)
                except Exception:
                    pass
            if "schedule_enabled" in params:
                update_data["schedule_enabled"] = bool(params.get("schedule_enabled"))
                update_data["schedule_since"] = (params.get("schedule_since") or "").strip()
                update_data["schedule_until"] = (params.get("schedule_until") or "").strip()

            doc = self.get_qrcard(fk_user_id, qrcard_id)
            if doc:
                import re
                new_sc = (params.get("short_code") or "").strip().lower()
                cur_sc = (doc.get("short_code") or "").strip().lower()
                if new_sc and new_sc != cur_sc:
                    if re.match(r"^[a-z0-9_-]{2,32}$", new_sc) and self.is_short_code_unique(new_sc, exclude_qrcard_id=qrcard_id):
                        update_data["short_code"] = new_sc

            self.mgdDB.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data})
            self.mgdDB.db_qrcard_links.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data}, upsert=True)

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
            self.mgdDB.db_qrcard_links.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "DELETED"}}, upsert=True)
            self.mgdDB.db_qr_index.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "DELETED"}})
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def complete_links_save(self, request, session, root_path):
        """Full links save: build params, add_qrcard, persist content + move uploads."""
        import os
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated", "url_content": "", "qr_name": "", "short_code": "", "qr_encode_url": None}

        _url_content_raw = request.form.get("url_content", "").strip()
        params = {
            "fk_user_id": fk_user_id,
            "name": request.form.get("qr_name", "Untitled QR"),
            "url_content": _url_content_raw or config.G_BASE_URL.rstrip("/"),
            "short_code": (request.form.get("short_code") or "").strip().lower(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(v) if (v := (request.form.get("scan_limit_value") or "").strip()).isdigit() else 0,
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
        }

        result = self.add_qrcard(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            sc = params.get("short_code") or ""
            return {"success": False, "error_msg": result.get("message_desc", "Save failed."), "url_content": request.form.get("url_content", ""), "qr_name": request.form.get("qr_name", ""), "short_code": sc, "qr_encode_url": (config.G_BASE_URL + "/links/" + sc) if sc else None}

        new_id = result["message_data"]["qrcard_id"]
        if not _url_content_raw:
            _qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": new_id}, {"short_code": 1}) or {}
            _sc = _qrcard.get("short_code", "")
            if _sc:
                _real_url = config.G_BASE_URL.rstrip("/") + "/links/" + _sc
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"url_content": _real_url}})
                self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"url_content": _real_url}})

        # Build links list
        urls = request.form.getlist("Links_link_url[]")
        names = request.form.getlist("Links_link_name[]")
        descs = request.form.getlist("Links_link_desc[]")
        links_list = []
        for u, n, d in zip(urls, names, descs):
            u = (u or "").strip()
            if not u:
                continue
            links_list.append({"url": u, "name": (n or "").strip(), "desc": (d or "").strip()})

        content_update = {
            "Links_title": (request.form.get("Links_title") or "").strip(),
            "Links_desc": (request.form.get("Links_desc") or "").strip(),
            "Links_links": links_list,
        }

        design_update = {}
        for key in request.form:
            if key.startswith("Links_") and not key.endswith("[]") and key not in ["Links_title", "Links_desc", "Links_link_url[]", "Links_link_name[]", "Links_link_desc[]"]:
                val = request.form.get(key)
                if val is not None:
                    design_update[key] = val.strip()
        if request.form.get("Links_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["Links_font_apply_all"] = True
        for key in ["welcome_time", "welcome_bg_color"]:
            if request.form.get(key):
                design_update[key] = request.form.get(key)

        full_update = {**content_update, **design_update}
        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": full_update})
        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": full_update}, upsert=True)

        # Move welcome/cover images from R2 _tmp → final
        _r2 = r2_mod.r2_storage_proc()
        welcome_tmp_key  = session.pop("links_welcome_tmp_key", None)
        welcome_tmp_name = session.pop("links_welcome_tmp_name", None)
        cover_tmp_key    = session.pop("links_cover_tmp_key", None)
        cover_tmp_name   = session.pop("links_cover_tmp_name", None)
        session.modified = True

        if welcome_tmp_key and welcome_tmp_name:
            ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
            try:
                welcome_url = _r2.move_file(f"links/_tmp/{welcome_tmp_key}/{welcome_tmp_name}", f"links/{new_id}/welcome{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": f"welcome{ext}"})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
            except Exception:
                pass
        else:
            # Priority: direct file upload from request (when user uploads their own welcome image)
            _direct_welcome = request.files.get("Links_welcome_img") if request.files else None
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
                        welcome_url = _r2.upload_file(_direct_welcome, f"links/{new_id}/{_dw_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": _dw_name})
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                    except Exception:
                        pass
            else:
                # Handle autocomplete/static welcome image
                ac_welcome = (request.form.get("links_welcome_img_autocomplete_url", "")
                              or session.pop("links_welcome_img_autocomplete_url", "")).strip()
                if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                    try:
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": ac_welcome}})
                        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": ac_welcome}}, upsert=True)
                    except Exception:
                        pass
                elif ac_welcome and ac_welcome.startswith("/static/"):
                    ext = os.path.splitext(ac_welcome)[1] or ".jpg"
                    local_path = os.path.join(root_path or config.G_HOME_PATH, ac_welcome.lstrip("/").replace("/", os.sep))
                    if os.path.isfile(local_path):
                        try:
                            unique_welcome_name = f"welcome_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as f:
                                welcome_url = _r2.upload_bytes(f.read(), f"links/{new_id}/{unique_welcome_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": unique_welcome_name})
                            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                            self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                        except Exception:
                            pass

        if cover_tmp_key and cover_tmp_name:
            ext = os.path.splitext(cover_tmp_name)[1] or ".jpg"
            unique_cover_name = f"links_cover_img_{uuid.uuid4().hex[:12]}{ext}"
            try:
                cover_url = _r2.move_file(f"links/_tmp/{cover_tmp_key}/{cover_tmp_name}", f"links/{new_id}/{unique_cover_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": unique_cover_name})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}})
                self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}}, upsert=True)
            except Exception:
                pass
        else:
            # Priority: direct file upload from request (when user uploads their own cover image)
            _direct_cover = request.files.get("Links_profile_img") if request.files else None
            if _direct_cover and _direct_cover.filename:
                _direct_cover.seek(0, 2)
                _dc_size = _direct_cover.tell()
                _direct_cover.seek(0)
                if _dc_size <= 2 * 1024 * 1024:
                    _dc_ext = os.path.splitext(_direct_cover.filename)[1].lower() or ".jpg"
                    if _dc_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        _dc_ext = ".jpg"
                    _dc_name = f"links_cover_img_{uuid.uuid4().hex[:12]}{_dc_ext}"
                    try:
                        cover_url = _r2.upload_file(_direct_cover, f"links/{new_id}/{_dc_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": _dc_name})
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}})
                        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}}, upsert=True)
                    except Exception:
                        pass
            else:
                # Handle autocomplete image (asset picker or legacy static path)
                ac_url = (request.form.get("links_cover_img_autocomplete_url", "")
                          or session.pop("links_cover_img_autocomplete_url", "")).strip()
                if ac_url and (ac_url.startswith("http://") or ac_url.startswith("https://")):
                    # Existing R2 asset URL — store directly, no re-upload
                    try:
                        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": ac_url}})
                        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": ac_url}}, upsert=True)
                    except Exception:
                        pass
                elif ac_url and ac_url.startswith("/static/"):
                    ext = os.path.splitext(ac_url)[1] or ".jpg"
                    local_path = os.path.join(root_path or config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                    if os.path.isfile(local_path):
                        try:
                            unique_cover_name = f"links_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as f:
                                cover_url = _r2.upload_bytes(f.read(), f"links/{new_id}/{unique_cover_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "links", "file_name": unique_cover_name})
                            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}})
                            self.mgdDB.db_qrcard_links.update_one({"qrcard_id": new_id}, {"$set": {"Links_cover_img_url": cover_url}}, upsert=True)
                        except Exception:
                            pass

        return {"success": True, "qrcard_id": new_id}

    def save_draft(self, request, session, root_path=None):
        """Create links QR as DRAFT: calls complete_links_save then downgrades status."""
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
                self.mgdDB.db_qrcard_links.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_links_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_links.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/links/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}
