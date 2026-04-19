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

            qrcard_rec["schedule_enabled"] = bool(params.get("schedule_enabled"))
            qrcard_rec["schedule_since"] = (params.get("schedule_since") or "").strip()
            qrcard_rec["schedule_until"] = (params.get("schedule_until") or "").strip()

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
            video_rec["schedule_enabled"] = qrcard_rec.get("schedule_enabled", False)
            video_rec["schedule_since"] = qrcard_rec.get("schedule_since", "")
            video_rec["schedule_until"] = qrcard_rec.get("schedule_until", "")
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

    def get_qrcard(self, fk_user_id, qrcard_id, allow_draft=False):
        """Return video doc for edit; merge scan/schedule and QR shell fields from db_qrcard when both exist."""
        try:
            status_filter = {"$in": ["ACTIVE", "DRAFT"]} if allow_draft else "ACTIVE"
            doc = self.mgdDB.db_qrcard_video.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": status_filter}
            )
            base_doc = self.mgdDB.db_qrcard.find_one(
                {
                    "fk_user_id": fk_user_id,
                    "qrcard_id": qrcard_id,
                    "qr_type": "video",
                    "status": status_filter,
                }
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

            # Support welcome image fields from edit flow
            if "welcome_img_url" in params and params.get("welcome_img_url") is not None:
                update_data["welcome_img_url"] = params.get("welcome_img_url")
            ac_welcome = (params.get("video_welcome_img_autocomplete_url") or "").strip()
            if ac_welcome:
                update_data["welcome_img_url"] = ac_welcome

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
        if not _url_content_raw:
            _qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": new_qrcard_id}, {"short_code": 1}) or {}
            _sc = _qrcard.get("short_code", "")
            if _sc:
                _real_url = config.G_BASE_URL.rstrip("/") + "/video/" + _sc
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})
                self.mgdDB.db_qrcard_video.update_one({"qrcard_id": new_qrcard_id}, {"$set": {"url_content": _real_url}})

        video_title = (request.form.get("video_title") or "").strip()
        video_desc = (request.form.get("video_desc") or "").strip()

        about_update = {
            "video_title": video_title,
            "video_desc": video_desc,
        }

        # Design fields from form
        design_update = {}
        for key in request.form:
            if key.startswith("video_") and not key.endswith("[]") and key != "video_welcome_img_autocomplete_url":
                val = request.form.get(key)
                if val is not None and str(val).strip() != "":
                    design_update[key] = str(val).strip()
            elif key in ("welcome_time", "welcome_bg_color"):
                val = request.form.get(key)
                if val is not None and str(val).strip() != "":
                    design_update[key] = str(val).strip()

        if request.form.get("video_font_apply_all") in ("on", "true", "1", "yes"):
            design_update["video_font_apply_all"] = True
        else:
            design_update["video_font_apply_all"] = False

        r2 = r2_mod.r2_storage_proc()

        # ---- Move uploaded videos from tmp ----
        tmp_key = session.pop("video_tmp_key", None)
        tmp_gallery = session.pop("video_tmp_gallery", [])

        # ---- Welcome image: move from tmp to final ----
        welcome_img_url = ""
        w_tmp_key = session.pop("video_welcome_img_tmp_key", None)
        w_tmp_name = session.pop("video_welcome_img_tmp_name", None)
        if w_tmp_key and w_tmp_name:
            import os as _os
            _wext = _os.path.splitext(w_tmp_name)[1] or ".jpg"
            src_key = f"video/_tmp/{w_tmp_key}/welcome{_wext}"
            dst_key = f"video/{new_qrcard_id}/welcome{_wext}"
            _w_meta = {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "video", "file_name": f"welcome{_wext}"}
        else:
            _wext = None
            _w_meta = None

        # Build parallel move specs for welcome + all video tmp files
        move_specs = []
        if w_tmp_key and w_tmp_name:
            move_specs.append(("welcome", src_key, dst_key, _w_meta))
        upload_gallery = []
        if tmp_key and tmp_gallery:
            for f_info in tmp_gallery:
                if f_info.get("type") == "upload":
                    _s = f"videos/_tmp/{tmp_key}/{f_info['safe_name']}"
                    _d = f"videos/{new_qrcard_id}/{f_info['safe_name']}"
                    _m = {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "video", "file_name": f_info['safe_name']}
                    move_specs.append(("video", _s, _d, _m))
                    upload_gallery.append(f_info)

        video_links = []

        if move_specs:
            _move_results = r2.move_files_parallel(
                [(s[1], s[2], s[3]) for s in move_specs]
            )
            for idx, _mr in enumerate(_move_results):
                _tag = move_specs[idx][0]
                if _tag == "welcome" and _mr["status"] == "success":
                    welcome_img_url = _mr["url"]
                elif _tag == "video" and _mr["status"] == "success":
                    _fi = upload_gallery[idx - (1 if (w_tmp_key and w_tmp_name) else 0)]
                    video_links.append({
                        "url": _mr["url"],
                        "name": _fi.get("name", ""),
                        "desc": _fi.get("desc", ""),
                        "type": "upload"
                    })
            # Add link-type gallery entries that weren't moved
            for f_info in tmp_gallery:
                if f_info.get("type") != "upload":
                    video_links.append({
                        "url": f_info.get("url", ""),
                        "name": f_info.get("name", ""),
                        "desc": f_info.get("desc", ""),
                        "type": "link"
                    })
            try:
                r2.delete_prefix(f"video/_tmp/{w_tmp_key}/")
            except Exception:
                pass
            try:
                r2.delete_prefix(f"videos/_tmp/{tmp_key}/")
            except Exception:
                pass
        else:
            # No tmp move specs — handle autocomplete/static welcome + direct upload path
            if not (w_tmp_key and w_tmp_name):
                import os as _os
                ac_welcome = (request.form.get("video_welcome_img_autocomplete_url")
                              or session.pop("video_welcome_img_autocomplete_url", "")).strip()
                if ac_welcome and (ac_welcome.startswith("http://") or ac_welcome.startswith("https://")):
                    welcome_img_url = ac_welcome
                elif ac_welcome and ac_welcome.startswith("/static/"):
                    base = root_path or config.G_HOME_PATH
                    local_path = _os.path.join(base, ac_welcome.lstrip("/").replace("/", _os.sep))
                    _wext = _os.path.splitext(ac_welcome)[1] or ".jpg"
                    unique_welcome = f"welcome_{uuid.uuid4().hex[:12]}{_wext}"
                    dst_key = f"video/{new_qrcard_id}/{unique_welcome}"
                    try:
                        with open(local_path, "rb") as f_static:
                            welcome_img_url = r2.upload_file(
                                f_static,
                                dst_key,
                                track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "video", "file_name": unique_welcome},
                            )
                    except Exception:
                        pass

            # Direct upload path: save-draft called without prior session tmp setup
            import os as _os
            video_types = request.form.getlist("video_type[]")
            url_list = request.form.getlist("video_url[]")
            name_list = request.form.getlist("video_name[]")
            desc_list = request.form.getlist("video_desc[]")
            video_files = request.files.getlist("video_files")
            file_idx = 0
            from itertools import zip_longest

            # Collect upload specs for parallel execution
            _upload_specs = []
            _upload_meta = []
            for i, (vtype, u, n, d) in enumerate(zip_longest(video_types, url_list, name_list, desc_list, fillvalue="")):
                u = (u or "").strip()
                n = (n or "").strip()
                d = (d or "").strip()
                if vtype == "upload":
                    fobj = video_files[file_idx] if file_idx < len(video_files) else None
                    file_idx += 1
                    if fobj and fobj.filename:
                        fobj.seek(0, 2)
                        if fobj.tell() <= 50 * 1024 * 1024:
                            fobj.seek(0)
                            ext = _os.path.splitext(fobj.filename)[1].lower() or ".mp4"
                            safe_name = uuid.uuid4().hex + ext
                            r2_key = f"videos/{new_qrcard_id}/{safe_name}"
                            _meta = {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "video", "file_name": safe_name}
                            _upload_specs.append((fobj, r2_key, _meta))
                            _upload_meta.append({"name": n, "desc": d, "type": "upload"})
                    elif u.startswith("/static/"):
                        base = root_path or config.G_HOME_PATH
                        local_path = _os.path.join(base, u.lstrip("/").replace("/", _os.sep))
                        ext = _os.path.splitext(u)[1].lower() or ".mp4"
                        safe_name = uuid.uuid4().hex + ext
                        r2_key = f"videos/{new_qrcard_id}/{safe_name}"
                        _meta = {"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "video", "file_name": safe_name}
                        try:
                            with open(local_path, "rb") as f_static:
                                _upload_specs.append((f_static, r2_key, _meta))
                                _upload_meta.append({"name": n, "desc": d, "type": "upload"})
                        except Exception:
                            pass
                    elif u.startswith("http"):
                        video_links.append({"url": u, "name": n, "desc": d, "type": "upload"})
                else:
                    if u:
                        video_links.append({"url": u, "name": n, "desc": d, "type": "link"})

            if _upload_specs:
                _up_results = r2.upload_files_parallel(_upload_specs)
                for idx, _ur in enumerate(_up_results):
                    if _ur["status"] == "success":
                        _m = _upload_meta[idx]
                        video_links.append({"url": _ur["url"], "name": _m["name"], "desc": _m["desc"], "type": _m["type"]})

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

        return {"success": True, "qrcard_id": new_qrcard_id}

    def save_draft(self, request, session, root_path=None):
        """Create video QR as DRAFT: calls complete_video_save then downgrades status."""
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
                self.mgdDB.db_qrcard_video.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_video_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_video.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/video/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}
