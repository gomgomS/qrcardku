import sys
import time
import uuid
import json
import random
import string
import os
import traceback
from datetime import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config  # noqa: F401
from storage import r2_storage_proc as r2_mod

SHORT_CODE_LENGTH = 8
SHORT_CODE_CHARS = string.ascii_lowercase + string.digits

ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_PDF_EXT = {".pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_COVER_SIZE = 2 * 1024 * 1024  # 2 MB


class qr_allinone_proc:
    """Standalone processor for All-in-One QR cards."""

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def _upload_static_to_r2(self, _r2, static_url, dest_key, root_path=None, track_meta=None):
        """Read a /static/... file from disk and upload it to R2. Returns R2 URL, or original URL on failure."""
        if not static_url or not static_url.startswith("/static/"):
            return static_url
        base = root_path or config.G_HOME_PATH
        local_path = os.path.join(base, static_url.lstrip("/").replace("/", os.sep))
        if not os.path.isfile(local_path):
            return static_url
        try:
            with open(local_path, "rb") as f:
                return _r2.upload_bytes(f.read(), dest_key, track_meta=track_meta)
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return static_url

    def generate_short_code(self):
        return "".join(random.choices(SHORT_CODE_CHARS, k=SHORT_CODE_LENGTH))

    # Keep private alias for compatibility
    _generate_short_code = generate_short_code

    def is_short_code_unique(self, short_code, exclude_qrcard_id=None):
        try:
            query = {"short_code": short_code, "status": {"$in": ["ACTIVE", "DRAFT"]}}
            if exclude_qrcard_id:
                query["qrcard_id"] = {"$ne": exclude_qrcard_id}
            return self.mgdDB.db_qrcard.find_one(query) is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def is_name_unique(self, fk_user_id, name, exclude_id=None, include_draft=True):
        try:
            status_filter = {"$in": ["ACTIVE", "DRAFT"]} if include_draft else "ACTIVE"
            query = {"fk_user_id": fk_user_id, "name": name, "status": status_filter}
            if exclude_id:
                query["qrcard_id"] = {"$ne": exclude_id}
            return self.mgdDB.db_qrcard.find_one(query) is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def _add_qrcard_base(self, params):
        """Create base db_qrcard + db_qrcard_allinone + db_qr_index records."""
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
                    short_code = self.generate_short_code()
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
                "qr_type": "allinone",
                "name": name,
                "url_content": url_content,
                "short_code": short_code,
                "design_data": {},
                "qr_image_url": "",
                "stats": {"scan_count": 0},
                "scan_limit_enabled": bool(params.get("scan_limit_enabled", False)),
                "scan_limit_value": max(int(params.get("scan_limit_value", 0)) if str(params.get("scan_limit_value", 0)).strip().isdigit() else 0, 0),
                "status": params.get("status", "ACTIVE"),
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            allinone_rec = dict(qrcard_rec)
            self.mgdDB.db_qrcard_allinone.insert_one(allinone_rec)

            idx = {
                "qrcard_id": qrcard_id,
                "fk_user_id": fk_user_id,
                "qr_type": "allinone",
                "name": name,
                "short_code": short_code,
                "status": params.get("status", "ACTIVE"),
                "created_at": created_at,
                "timestamp": current_time,
            }
            self.mgdDB.db_qr_index.insert_one(idx)

            return {"message_action": "ADD_QRCARD_SUCCESS", "message_desc": "QR card saved.", "message_data": {"qrcard_id": qrcard_id, "short_code": short_code}}
        except Exception:
            err = traceback.format_exc()
            self.webapp.logger.debug(err)
            return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "An internal error occurred.", "message_data": {}}

    def get_allinone_by_qrcard_id(self, qrcard_id, fk_user_id=None, allow_draft=False):
        """Fetch merged qrcard + allinone doc. If allow_draft=True, also returns DRAFT records."""
        try:
            status_filter = {"$in": ["ACTIVE", "DRAFT"]} if allow_draft else "ACTIVE"
            query = {"qrcard_id": qrcard_id, "status": status_filter}
            if fk_user_id:
                query["fk_user_id"] = fk_user_id
            doc = self.mgdDB.db_qrcard_allinone.find_one(query)
            if doc:
                return doc
            # Fallback: try db_qrcard
            q2 = {"qrcard_id": qrcard_id, "qr_type": "allinone", "status": status_filter}
            if fk_user_id:
                q2["fk_user_id"] = fk_user_id
            return self.mgdDB.db_qrcard.find_one(q2)
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def delete_allinone_by_qrcard_id(self, qrcard_id, fk_user_id=None):
        try:
            q = {"qrcard_id": qrcard_id}
            if fk_user_id:
                q["fk_user_id"] = fk_user_id
            self.mgdDB.db_qrcard.update_one(q, {"$set": {"status": "DELETED"}})
            self.mgdDB.db_qrcard_allinone.update_one(q, {"$set": {"status": "DELETED"}})
            self.mgdDB.db_qr_index.update_one(q, {"$set": {"status": "DELETED"}})
            return True
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def complete_allinone_save(self, request, session, root_path):
        """Full allinone save: build params, insert records, persist files, move uploads."""
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"status": "error", "message_desc": "Not authenticated"}

        url_content = request.form.get("url_content", "")
        if url_content and not url_content.startswith("http"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()

        # Validate name uniqueness — only block on ACTIVE records (DRAFTs are incomplete)
        if not self.is_name_unique(fk_user_id, qr_name, include_draft=False):
            return {"status": "error", "message_desc": "A QR card with this name already exists."}

        # Delete orphaned DRAFTs with the same name so the new ACTIVE doesn't create a duplicate row
        try:
            old_drafts = list(self.mgdDB.db_qrcard.find(
                {"fk_user_id": fk_user_id, "name": qr_name, "status": "DRAFT"},
                {"qrcard_id": 1}
            ))
            if old_drafts:
                old_ids = [d["qrcard_id"] for d in old_drafts]
                self.mgdDB.db_qrcard.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qrcard_allinone.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())

        params = {
            "fk_user_id": fk_user_id,
            "name": qr_name,
            "url_content": url_content,
            "short_code": short_code,
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(v) if (v := (request.form.get("scan_limit_value") or "").strip()).isdigit() else 0,
        }

        result = self._add_qrcard_base(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            return {"status": "error", "message_desc": result.get("message_desc", "Save failed.")}

        new_id = result["message_data"]["qrcard_id"]
        used_short_code = result["message_data"]["short_code"]
        _r2 = r2_mod.r2_storage_proc()

        # Read sections from allinone_sections_json (passed from design step)
        sections_json_str = request.form.get("allinone_sections_json", "")
        sections = []
        if sections_json_str:
            try:
                sections = json.loads(sections_json_str)
                if not isinstance(sections, list):
                    sections = []
            except Exception:
                sections = []

        # Build content_update
        _new_skip = {"Allinone_profile_img_delete", "Allinone_profile_img_autocomplete_url"}
        content_update = {}
        for key in request.form:
            if key.startswith("Allinone_") and not key.endswith("[]") and key not in _new_skip:
                val = request.form.get(key)
                if val is not None:
                    content_update[key] = val.strip() if isinstance(val, str) else val

        if request.form.get("Allinone_font_apply_all") in ("on", "true", "1", "yes"):
            content_update["Allinone_font_apply_all"] = True

        for key in ["welcome_time", "welcome_bg_color"]:
            v = request.form.get(key)
            if v:
                content_update[key] = v

        content_update["Allinone_sections"] = sections

        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": content_update})
        self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": content_update}, upsert=True)

        # Welcome image upload
        welcome_img = request.files.get("Allinone_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in ALLOWED_IMG_EXT:
                    ext = ".jpg"
                try:
                    welcome_url = _r2.upload_file(
                        welcome_img, f"allinone/{new_id}/welcome{ext}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"welcome{ext}"}
                    )
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                    self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                except Exception:
                    self.webapp.logger.debug(traceback.format_exc())

        # Move tmp cover image from R2 _tmp → R2 final
        cover_tmp_key  = session.pop("allinone_cover_tmp_key",  None)
        cover_tmp_name = session.pop("allinone_cover_tmp_name", None)
        session.pop("allinone_cover_r2_url", None)
        session.modified = True

        if cover_tmp_key and cover_tmp_name:
            ext = os.path.splitext(cover_tmp_name)[1] or ".jpg"
            src_key  = f"allinone/_tmp/{cover_tmp_key}/{cover_tmp_name}"
            dest_key = f"allinone/{new_id}/allinone_cover{ext}"
            try:
                cover_url = _r2.move_file(src_key, dest_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"})
                self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": cover_url}})
                self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": cover_url}}, upsert=True)
            except Exception:
                self.webapp.logger.debug(traceback.format_exc())
        else:
            ac_url = (request.form.get("Allinone_profile_img_autocomplete_url") or "").strip()
            if ac_url:
                if ac_url.startswith("/static/"):
                    ext = os.path.splitext(ac_url)[1] or ".jpg"
                    ac_url = self._upload_static_to_r2(_r2, ac_url, f"allinone/{new_id}/allinone_cover{ext}", root_path, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"})
                if ac_url:
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": ac_url}})
                    self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": ac_url}}, upsert=True)

        # Move tmp section files from R2 _tmp → R2 final
        updated_sections = []
        moved_tmp_keys = set()
        for i, s in enumerate(sections):
            s = dict(s)
            v1 = s.get("v1", "")
            stype = s.get("type", "")
            # Upload autocomplete static files to R2
            if stype in ("image", "video", "pdf") and v1 and v1.startswith("/static/"):
                ext = os.path.splitext(v1)[1] or (".mp4" if stype == "video" else ".jpg" if stype == "image" else ".pdf")
                dest_key = f"allinone/{new_id}/{stype}_{i}_{new_id[:8]}{ext}"
                s["v1"] = self._upload_static_to_r2(_r2, v1, dest_key, root_path, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"{stype}_{i}_{new_id[:8]}{ext}"})
                v1 = s["v1"]
            if stype in ("image", "pdf") and v1 and "/_tmp/" in v1:
                try:
                    # URL contains allinone/_tmp/{tmp_key}/{fname} somewhere
                    parts = v1.split("/_tmp/", 1)
                    if len(parts) == 2:
                        rest = parts[1]
                        tmp_key_part, fname_part = rest.split("/", 1)
                        ext = os.path.splitext(fname_part)[1] or (".jpg" if stype == "image" else ".pdf")
                        new_fname = f"{stype}_{i}_{new_id[:8]}{ext}"
                        src_key  = f"allinone/_tmp/{tmp_key_part}/{fname_part}"
                        dest_key = f"allinone/{new_id}/{new_fname}"
                        s["v1"] = _r2.move_file(src_key, dest_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": new_fname})
                        moved_tmp_keys.add(tmp_key_part)
                except Exception:
                    self.webapp.logger.debug(traceback.format_exc())
            updated_sections.append(s)

        # Clean up any remaining _tmp prefixes
        for tk in moved_tmp_keys:
            try:
                _r2.delete_prefix(f"allinone/_tmp/{tk}/")
            except Exception:
                pass

        if updated_sections != sections:
            self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_sections": updated_sections}})
            self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_sections": updated_sections}}, upsert=True)

        qr_encode_url = "{}allinone/{}".format(config.G_BASE_URL.rstrip("/") + "/", used_short_code)

        return {
            "status": "ok",
            "qrcard_id": new_id,
            "url_content": url_content,
            "short_code": used_short_code,
            "qr_encode_url": qr_encode_url,
        }

    def save_draft(self, request, session, root_path):
        """Create allinone QR as DRAFT: insert records with DRAFT status, upload files directly (no _tmp)."""
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"status": "error", "message_desc": "Not authenticated"}

        # For allinone, url_content is the allinone page URL (auto-generated from short_code).
        # The form does not send url_content, so we use a placeholder that will be updated below.
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http"):
            url_content = "https://" + url_content
        if not url_content:
            url_content = config.G_BASE_URL.rstrip("/")  # placeholder; replaced after short_code is known
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()

        if not self.is_name_unique(fk_user_id, qr_name, include_draft=False):
            return {"status": "error", "message_desc": "A QR card with this name already exists."}

        # Delete any orphaned DRAFTs with the same name before creating a new one,
        # so retrying "Save & Next" never accumulates ghost records.
        try:
            old_drafts = list(self.mgdDB.db_qrcard.find(
                {"fk_user_id": fk_user_id, "name": qr_name, "status": "DRAFT"},
                {"qrcard_id": 1}
            ))
            if old_drafts:
                old_ids = [d["qrcard_id"] for d in old_drafts]
                self.mgdDB.db_qrcard.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qrcard_allinone.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())

        params = {
            "fk_user_id": fk_user_id,
            "name": qr_name,
            "url_content": url_content,
            "short_code": short_code,
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(v) if (v := (request.form.get("scan_limit_value") or "").strip()).isdigit() else 0,
            "status": "DRAFT",
        }

        result = self._add_qrcard_base(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            return {"status": "error", "message_desc": result.get("message_desc", "Save failed.")}

        new_id = result["message_data"]["qrcard_id"]
        used_short_code = result["message_data"]["short_code"]
        # Set the real allinone URL now that we have the short_code
        real_url_content = config.G_BASE_URL.rstrip("/") + "/allinone/" + used_short_code
        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"url_content": real_url_content}})
        self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"url_content": real_url_content}}, upsert=True)
        _r2 = r2_mod.r2_storage_proc()

        sections_json_str = request.form.get("allinone_sections_json", "")
        sections = []
        if sections_json_str:
            try:
                sections = json.loads(sections_json_str)
                if not isinstance(sections, list):
                    sections = []
            except Exception:
                sections = []

        _skip = {"Allinone_profile_img_delete", "Allinone_profile_img_autocomplete_url"}
        content_update = {}
        for key in request.form:
            if key.startswith("Allinone_") and not key.endswith("[]") and key not in _skip:
                val = request.form.get(key)
                if val is not None:
                    content_update[key] = val.strip() if isinstance(val, str) else val

        if request.form.get("Allinone_font_apply_all") in ("on", "true", "1", "yes"):
            content_update["Allinone_font_apply_all"] = True

        for key in ["welcome_time", "welcome_bg_color"]:
            v = request.form.get(key)
            if v:
                content_update[key] = v

        content_update["Allinone_sections"] = sections

        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": content_update})
        self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": content_update}, upsert=True)

        # Welcome image
        welcome_img = request.files.get("Allinone_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in ALLOWED_IMG_EXT:
                    ext = ".jpg"
                try:
                    welcome_url = _r2.upload_file(
                        welcome_img, f"allinone/{new_id}/welcome{ext}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"welcome{ext}"}
                    )
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}})
                    self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"welcome_img_url": welcome_url}}, upsert=True)
                except Exception:
                    self.webapp.logger.debug(traceback.format_exc())

        # Cover image — direct upload (no _tmp)
        cover_img = request.files.get("Allinone_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= MAX_COVER_SIZE:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in ALLOWED_IMG_EXT:
                    ext = ".jpg"
                try:
                    cover_url = _r2.upload_file(
                        cover_img, f"allinone/{new_id}/allinone_cover{ext}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"}
                    )
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": cover_url}})
                    self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": cover_url}}, upsert=True)
                except Exception:
                    self.webapp.logger.debug(traceback.format_exc())
        else:
            ac_url = (request.form.get("Allinone_profile_img_autocomplete_url") or "").strip()
            if ac_url:
                if ac_url.startswith("/static/"):
                    ext = os.path.splitext(ac_url)[1] or ".jpg"
                    ac_url = self._upload_static_to_r2(_r2, ac_url, f"allinone/{new_id}/allinone_cover{ext}", root_path,
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"})
                if ac_url:
                    self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": ac_url}})
                    self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_cover_img_url": ac_url}}, upsert=True)

        # Section file uploads — directly to permanent paths
        updated_sections = []
        for i, s in enumerate(sections):
            s = dict(s)
            v1 = s.get("v1", "")
            stype = s.get("type", "")
            if stype in ("image", "video", "pdf"):
                fkey = f"allinone_file_{i}"
                fobj = request.files.get(fkey)
                if fobj and fobj.filename:
                    fobj.seek(0, 2)
                    if fobj.tell() <= MAX_FILE_SIZE:
                        fobj.seek(0)
                        ext = os.path.splitext(fobj.filename)[1].lower()
                        if stype == "image" and ext not in ALLOWED_IMG_EXT:
                            ext = ".jpg"
                        elif stype == "pdf" and ext not in ALLOWED_PDF_EXT:
                            ext = ".pdf"
                        fname = f"{stype}_{i}_{new_id[:8]}{ext}"
                        s["v1"] = _r2.upload_file(fobj, f"allinone/{new_id}/{fname}",
                            track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": fname})
                elif v1 and v1.startswith("/static/"):
                    ext = os.path.splitext(v1)[1] or (".mp4" if stype == "video" else ".jpg" if stype == "image" else ".pdf")
                    fname = f"{stype}_{i}_{new_id[:8]}{ext}"
                    s["v1"] = self._upload_static_to_r2(_r2, v1, f"allinone/{new_id}/{fname}", root_path,
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_id, "qr_type": "allinone", "file_name": fname})
            updated_sections.append(s)

        self.mgdDB.db_qrcard.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_sections": updated_sections}})
        self.mgdDB.db_qrcard_allinone.update_one({"qrcard_id": new_id}, {"$set": {"Allinone_sections": updated_sections}}, upsert=True)

        qr_encode_url = "{}allinone/{}".format(config.G_BASE_URL.rstrip("/") + "/", used_short_code)

        return {
            "status": "ok",
            "qrcard_id": new_id,
            "short_code": used_short_code,
            "qr_encode_url": qr_encode_url,
        }

    def update_allinone_content(self, request, session, root_path, qrcard_id):
        """Update existing allinone qrcard content and/or design."""
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"status": "error", "message_desc": "Not authenticated"}

        existing = self.get_allinone_by_qrcard_id(qrcard_id, fk_user_id)
        if not existing:
            return {"status": "error", "message_desc": "QR card not found."}

        _r2 = r2_mod.r2_storage_proc()
        update_data = {}

        # Basic fields
        qr_name = request.form.get("qr_name", "").strip()
        if qr_name:
            update_data["name"] = qr_name

        url_content = request.form.get("url_content", "").strip()
        if url_content:
            if not url_content.startswith("http"):
                url_content = "https://" + url_content
            update_data["url_content"] = url_content

        # Short code
        import re
        new_sc = (request.form.get("short_code") or "").strip().lower()
        cur_sc = (existing.get("short_code") or "").strip().lower()
        if new_sc and new_sc != cur_sc:
            if re.match(r"^[a-z0-9_-]{2,32}$", new_sc) and self.is_short_code_unique(new_sc, exclude_qrcard_id=qrcard_id):
                update_data["short_code"] = new_sc

        # Allinone_ fields
        _allinone_skip = {"Allinone_profile_img_delete", "Allinone_profile_img_autocomplete_url"}
        for key in request.form:
            if key.startswith("Allinone_") and not key.endswith("[]") and key not in _allinone_skip:
                val = request.form.get(key)
                if val is not None:
                    update_data[key] = val.strip() if isinstance(val, str) else val

        if request.form.get("Allinone_font_apply_all") in ("on", "true", "1", "yes"):
            update_data["Allinone_font_apply_all"] = True

        for key in ["welcome_time", "welcome_bg_color", "scan_limit_enabled", "scan_limit_value"]:
            v = request.form.get(key)
            if v is not None:
                update_data[key] = v

        # Welcome image
        welcome_delete = request.form.get("Allinone_welcome_img_delete", "0")
        if welcome_delete == "1":
            update_data["welcome_img_url"] = ""
        else:
            welcome_img = request.files.get("Allinone_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in ALLOWED_IMG_EXT:
                        ext = ".jpg"
                    try:
                        update_data["welcome_img_url"] = _r2.upload_file(
                            welcome_img, f"allinone/{qrcard_id}/welcome{ext}",
                            track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": f"welcome{ext}"}
                        )
                    except Exception:
                        self.webapp.logger.debug(traceback.format_exc())
            elif existing.get("welcome_img_url"):
                update_data["welcome_img_url"] = existing["welcome_img_url"]

        # Cover image
        cover_delete = request.form.get("Allinone_profile_img_delete", "0")
        if cover_delete == "1":
            update_data["Allinone_cover_img_url"] = ""
        else:
            cover_img = request.files.get("Allinone_profile_img")
            if cover_img and cover_img.filename:
                cover_img.seek(0, 2)
                if cover_img.tell() <= MAX_COVER_SIZE:
                    cover_img.seek(0)
                    ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                    if ext not in ALLOWED_IMG_EXT:
                        ext = ".jpg"
                    update_data["Allinone_cover_img_url"] = _r2.upload_file(
                        cover_img, f"allinone/{qrcard_id}/allinone_cover{ext}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"}
                    )
            else:
                ac_url = (request.form.get("Allinone_profile_img_autocomplete_url") or "").strip()
                if ac_url:
                    if ac_url.startswith("/static/"):
                        ext = os.path.splitext(ac_url)[1] or ".jpg"
                        ac_url = self._upload_static_to_r2(_r2, ac_url, f"allinone/{qrcard_id}/allinone_cover{ext}", root_path, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": f"allinone_cover{ext}"})
                    if ac_url:
                        update_data["Allinone_cover_img_url"] = ac_url

        # Prefer allinone_sections_json (rich format with block_style/color) over flat arrays
        sections_json_str = request.form.get("allinone_sections_json", "").strip()
        sections = []
        use_json = False
        if sections_json_str:
            try:
                parsed = json.loads(sections_json_str)
                if isinstance(parsed, list):
                    sections = parsed
                    use_json = True
            except Exception:
                pass

        if use_json:
            # Process file uploads for image/pdf sections by index
            for i, s in enumerate(sections):
                s = dict(s)
                stype = s.get("type", "")
                if stype in ("image", "video", "pdf"):
                    fkey = f"allinone_file_{i}"
                    fobj = request.files.get(fkey)
                    if fobj and fobj.filename:
                        fobj.seek(0, 2)
                        if fobj.tell() <= MAX_FILE_SIZE:
                            fobj.seek(0)
                            ext = os.path.splitext(fobj.filename)[1].lower()
                            if stype == "image" and ext not in ALLOWED_IMG_EXT:
                                ext = ".jpg"
                            elif stype == "pdf" and ext not in ALLOWED_PDF_EXT:
                                ext = ".pdf"
                            fname = f"{stype}_{i}_{qrcard_id[:8]}{ext}"
                            s["v1"] = _r2.upload_file(fobj, f"allinone/{qrcard_id}/{fname}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": fname})
                    elif s.get("v1", "").startswith("/static/"):
                        v1 = s["v1"]
                        ext = os.path.splitext(v1)[1] or (".mp4" if stype == "video" else ".jpg" if stype == "image" else ".pdf")
                        fname = f"{stype}_{i}_{qrcard_id[:8]}{ext}"
                        s["v1"] = self._upload_static_to_r2(_r2, v1, f"allinone/{qrcard_id}/{fname}", root_path, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": fname})
                sections[i] = s
        else:
            # Rebuild sections from parallel arrays (flat format)
            types = request.form.getlist("Allinone_section_type[]")
            v1s = request.form.getlist("Allinone_section_v1[]")
            v2s = request.form.getlist("Allinone_section_v2[]")
            v3s = request.form.getlist("Allinone_section_v3[]")
            v4s = request.form.getlist("Allinone_section_v4[]")
            file_existings = request.form.getlist("Allinone_section_file_existing[]")

            from itertools import zip_longest
            for i, (stype, a, b, c, d, fe) in enumerate(zip_longest(types, v1s, v2s, v3s, v4s, file_existings, fillvalue="")):
                s = {"type": stype or "", "v1": a or "", "v2": b or "", "v3": c or "", "v4": d or ""}
                if stype in ("image", "video", "pdf"):
                    fkey = f"allinone_file_{i}"
                    fobj = request.files.get(fkey)
                    if fobj and fobj.filename:
                        fobj.seek(0, 2)
                        if fobj.tell() <= MAX_FILE_SIZE:
                            fobj.seek(0)
                            ext = os.path.splitext(fobj.filename)[1].lower()
                            if stype == "image" and ext not in ALLOWED_IMG_EXT:
                                ext = ".jpg"
                            elif stype == "pdf" and ext not in ALLOWED_PDF_EXT:
                                ext = ".pdf"
                            fname = f"{stype}_{i}_{qrcard_id[:8]}{ext}"
                            s["v1"] = _r2.upload_file(fobj, f"allinone/{qrcard_id}/{fname}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": fname})
                    elif fe:
                        s["v1"] = fe
                    elif s["v1"].startswith("/static/"):
                        v1 = s["v1"]
                        ext = os.path.splitext(v1)[1] or (".mp4" if stype == "video" else ".jpg" if stype == "image" else ".pdf")
                        fname = f"{stype}_{i}_{qrcard_id[:8]}{ext}"
                        s["v1"] = self._upload_static_to_r2(_r2, v1, f"allinone/{qrcard_id}/{fname}", root_path, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "allinone", "file_name": fname})
                sections.append(s)

        update_data["Allinone_sections"] = sections

        self.mgdDB.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data})
        self.mgdDB.db_qrcard_allinone.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": update_data}, upsert=True)

        idx_update = {}
        if "name" in update_data:
            idx_update["name"] = update_data["name"]
        if "short_code" in update_data:
            idx_update["short_code"] = update_data["short_code"]
        if idx_update:
            self.mgdDB.db_qr_index.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": idx_update})

        return {"status": "ok"}
