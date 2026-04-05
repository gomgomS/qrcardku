import sys
import re as _re
import time
import uuid
import json
import random
import string
import traceback
from datetime import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config  # noqa: F401
from storage import r2_storage_proc as r2_mod

# ── Input sanitization helpers ─────────────────────────────────────────────

def _sanitize_text(val, max_len=200):
    """Strip all HTML tags from plain-text fields and truncate."""
    if not isinstance(val, str):
        return ''
    val = _re.sub(r'<[^>]+>', '', val).strip()
    return val[:max_len]


def _sanitize_html_content(html):
    """Remove <script>, <iframe>, on* event handlers, and javascript: URLs from HTML blocks."""
    if not isinstance(html, str):
        return html or ''
    # Remove script / iframe blocks entirely
    html = _re.sub(r'<script[\s\S]*?</script>', '', html, flags=_re.IGNORECASE)
    html = _re.sub(r'<iframe[\s\S]*?</iframe>', '', html, flags=_re.IGNORECASE)
    html = _re.sub(r'<iframe[^>]*/?>',          '', html, flags=_re.IGNORECASE)
    # Remove on* event handler attributes (quoted and unquoted)
    html = _re.sub(r'\s+on\w+\s*=\s*"[^"]*"',  '', html, flags=_re.IGNORECASE)
    html = _re.sub(r"\s+on\w+\s*=\s*'[^']*'",  '', html, flags=_re.IGNORECASE)
    html = _re.sub(r'\s+on\w+\s*=\s*[^\s>]+',  '', html, flags=_re.IGNORECASE)
    # Neutralise javascript: URLs in href / src / action
    html = _re.sub(r'(href|src|action)\s*=\s*"javascript:[^"]*"', r'\1=""', html, flags=_re.IGNORECASE)
    html = _re.sub(r"(href|src|action)\s*=\s*'javascript:[^']*'", r"\1=''", html, flags=_re.IGNORECASE)
    return html


def _sanitize_color(val, default='#2F6BFD'):
    """Return val if it is a valid 6-digit hex colour string, otherwise return default."""
    if isinstance(val, str) and _re.match(r'^#[0-9a-fA-F]{6}$', val.strip()):
        return val.strip()
    return default


def _sanitize_welcome_time(val, default='2.5'):
    """Clamp welcome_time to [2.5, 10.0] and return as string."""
    try:
        t = float(val)
        t = max(2.5, min(10.0, t))
        return str(round(t, 1))
    except (TypeError, ValueError):
        return default


def _sanitize_sections(sections):
    """Sanitize every section's data in a sections list."""
    if not isinstance(sections, list):
        return []
    result = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        stype = sec.get('type', '')
        if stype in ('content', 'html_editor'):
            sec['data'] = _sanitize_html_content(sec.get('data') or '')
        elif stype == 'maps':
            raw = sec.get('data') or {}
            if isinstance(raw, dict):
                try:
                    lat = float(raw.get('latitude') or 0)
                    lat = max(-90.0, min(90.0, lat))
                except (TypeError, ValueError):
                    lat = 0.0
                try:
                    lng = float(raw.get('longitude') or 0)
                    lng = max(-180.0, min(180.0, lng))
                except (TypeError, ValueError):
                    lng = 0.0
                sec['data'] = {'latitude': lat, 'longitude': lng}
        result.append(sec)
    return result

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


class qr_special_proc:
    """Standalone processor for special (custom HTML builder) QR cards."""

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
        """Create a new special qrcard."""
        try:
            fk_user_id = params.get("fk_user_id")
            name = params.get("name", "Untitled QR")
            url_content = params.get("url_content", "")
            short_code = (params.get("short_code") or "").strip().lower()
            special_sections = params.get("special_sections", [])

            if not fk_user_id:
                return {
                    "message_action": "ADD_QRCARD_FAILED",
                    "message_desc": "User authentication required.",
                    "message_data": {},
                }

            if short_code:
                if not _re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                    return {
                        "message_action": "ADD_QRCARD_FAILED",
                        "message_desc": "Address identifier must be 2-32 characters: letters, numbers, '-' or '_'.",
                        "message_data": {},
                    }
                if not self.is_short_code_unique(short_code):
                    return {
                        "message_action": "ADD_QRCARD_FAILED",
                        "message_desc": "This address identifier is already in use.",
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

            # Master qrcard record
            qrcard_rec = database.get_record("db_qrcard")
            qrcard_rec["qrcard_id"] = qrcard_id
            qrcard_rec["fk_user_id"] = fk_user_id
            qrcard_rec["qr_type"] = "special"
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
            qrcard_rec["schedule_enabled"] = bool(params.get("schedule_enabled", False))
            qrcard_rec["schedule_since"] = (params.get("schedule_since") or "").strip()
            qrcard_rec["schedule_until"] = (params.get("schedule_until") or "").strip()
            qrcard_rec["welcome_img_url"] = params.get("welcome_img_url", "")
            qrcard_rec["welcome_bg_color"] = params.get("welcome_bg_color", "#2F6BFD")
            qrcard_rec["welcome_time"] = params.get("welcome_time", "2.5")
            qrcard_rec["status"] = "ACTIVE"
            qrcard_rec["created_at"] = created_at
            qrcard_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            # Type-specific record
            special_rec = database.get_record("db_qrcard_special")
            special_rec["qrcard_id"] = qrcard_id
            special_rec["fk_user_id"] = fk_user_id
            special_rec["qr_type"] = "special"
            special_rec["name"] = name
            special_rec["url_content"] = url_content
            special_rec["short_code"] = short_code
            special_rec["special_sections"] = json.dumps(special_sections)
            special_rec["welcome_img_url"] = params.get("welcome_img_url", "")
            special_rec["welcome_bg_color"] = params.get("welcome_bg_color", "#2F6BFD")
            special_rec["welcome_time"] = params.get("welcome_time", "2.5")
            special_rec["stats"] = qrcard_rec.get("stats", {"scan_count": 0})
            special_rec["scan_limit_enabled"] = qrcard_rec.get("scan_limit_enabled", False)
            special_rec["scan_limit_value"] = qrcard_rec.get("scan_limit_value", 0)
            special_rec["schedule_enabled"] = qrcard_rec.get("schedule_enabled", False)
            special_rec["schedule_since"] = qrcard_rec.get("schedule_since", "")
            special_rec["schedule_until"] = qrcard_rec.get("schedule_until", "")
            special_rec["status"] = "ACTIVE"
            special_rec["created_at"] = created_at
            special_rec["timestamp"] = current_time
            self.mgdDB.db_qrcard_special.insert_one(special_rec)

            # Index entry
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "special"
            idx["name"] = name
            idx["short_code"] = short_code
            idx["status"] = "ACTIVE"
            idx["created_at"] = created_at
            idx["timestamp"] = current_time
            self.mgdDB.db_qr_index.insert_one(idx)

            return {
                "message_action": "ADD_QRCARD_SUCCESS",
                "message_desc": "Special QR card created successfully.",
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

    def get_qrcard(self, fk_user_id, qrcard_id):
        """Return special doc for edit."""
        try:
            doc = self.mgdDB.db_qrcard_special.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
            if not doc:
                doc = self.mgdDB.db_qrcard.find_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "special", "status": "ACTIVE"}
                )
            if doc:
                # special_sections is stored as a JSON string; parse it back to a list for templates
                raw = doc.get("special_sections", "[]")
                try:
                    doc["special_sections"] = json.loads(raw) if isinstance(raw, str) else (raw or [])
                except Exception:
                    doc["special_sections"] = []
                base = self.mgdDB.db_qrcard.find_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "special"}
                )
                if base:
                    for k in (
                        "schedule_enabled",
                        "schedule_since",
                        "schedule_until",
                        "scan_limit_enabled",
                        "scan_limit_value",
                        "qr_image_url",
                        "qr_composite_url",
                        "qr_dot_style",
                        "qr_corner_style",
                        "qr_dot_color",
                        "qr_bg_color",
                        "card_bg_color",
                        "frame_id",
                    ):
                        if k in base:
                            doc[k] = base[k]
                for dk in ("schedule_since", "schedule_until"):
                    if doc.get(dk) not in (None, ""):
                        doc[dk] = _schedule_date_for_html_input(doc[dk])
            return doc
        except Exception:
            self.webapp.logger.debug("qr_special_proc.get_qrcard failed", exc_info=True)
            return None

    def edit_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            name = _sanitize_text(params.get("name") or "", max_len=120) or "Untitled QR"
            url_content = _sanitize_text(params.get("url_content") or "", max_len=300)
            special_sections = _sanitize_sections(params.get("special_sections") or [])

            update_data = {
                "name": name,
                "url_content": url_content,
                "special_sections": json.dumps(special_sections),
            }

            # Welcome screen fields
            if "welcome_bg_color" in params:
                update_data["welcome_bg_color"] = _sanitize_color(params["welcome_bg_color"])
            if "welcome_time" in params:
                update_data["welcome_time"] = _sanitize_welcome_time(params["welcome_time"])
            if "welcome_img_url" in params:
                update_data["welcome_img_url"] = params["welcome_img_url"]

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
            if "schedule_since" in params:
                update_data["schedule_since"] = (params.get("schedule_since") or "").strip()
            if "schedule_until" in params:
                update_data["schedule_until"] = (params.get("schedule_until") or "").strip()

            doc = self.get_qrcard(fk_user_id, qrcard_id)
            if doc:
                new_short = (params.get("short_code") or "").strip().lower()
                current_short = (doc.get("short_code") or "").strip().lower()
                if new_short and new_short != current_short:
                    if _re.match(r"^[a-z0-9_-]{2,32}$", new_short) and self.is_short_code_unique(
                        new_short, exclude_qrcard_id=qrcard_id
                    ):
                        update_data["short_code"] = new_short

            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": update_data},
            )
            self.mgdDB.db_qrcard_special.update_one(
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
            return {"status": "SUCCESS", "message": "Special QR card updated."}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"status": "FAILED", "message": "Error updating QR card."}

    def complete_special_save(self, request, session, root_path):
        """
        Full special card save: parse sections JSON, add_qrcard, handle image uploads.
        Returns dict with success=True or success=False + form data for error re-render.
        """
        import os
        r2 = r2_mod.r2_storage_proc()
        fk_user_id = session.get("fk_user_id")
        if not fk_user_id:
            return {"success": False, "error_msg": "Not authenticated"}

        name = _sanitize_text(request.form.get("qr_name", ""), max_len=120) or "Untitled QR"
        url_content = _sanitize_text(request.form.get("url_content", ""), max_len=300)
        short_code = (request.form.get("short_code") or "").strip().lower()

        # Parse special_sections from hidden JSON field
        sections_json = request.form.get("special_sections", "[]")
        try:
            special_sections = json.loads(sections_json)
            if not isinstance(special_sections, list):
                special_sections = []
        except Exception:
            special_sections = []
        special_sections = _sanitize_sections(special_sections)

        params = {
            "fk_user_id": fk_user_id,
            "name": name,
            "url_content": url_content,
            "short_code": short_code,
            "special_sections": special_sections,
        }
        params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
        params["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
        params["schedule_since"] = (request.form.get("schedule_since") or "").strip()
        params["schedule_until"] = (request.form.get("schedule_until") or "").strip()

        params["welcome_bg_color"] = _sanitize_color(request.form.get("welcome_bg_color", "#2F6BFD"))
        params["welcome_time"] = _sanitize_welcome_time(request.form.get("welcome_time", "2.5"))
        params["welcome_img_url"] = request.form.get("welcome_img_url", "")

        result = self.add_qrcard(params)
        if result.get("message_action") == "ADD_QRCARD_FAILED":
            sc = params.get("short_code") or ""
            base = config.G_BASE_URL
            encode = (base + "/special/" + sc) if sc else None
            return {
                "success": False,
                "error_msg": result.get("message_desc", "Save failed."),
                "url_content": url_content,
                "qr_name": name,
                "short_code": sc,
                "qr_encode_url": encode,
                "special_sections": special_sections,
            }

        new_qrcard_id = result["message_data"]["qrcard_id"]

        # Handle welcome screen image upload
        welcome_file = request.files.get("special_welcome_img")
        welcome_asset_url = (request.form.get("special_welcome_img_autocomplete_url") or "").strip()
        if welcome_file and welcome_file.filename:
            safe_name = _re.sub(r"[^a-zA-Z0-9_.-]", "_", welcome_file.filename)
            welcome_fname = "welcome_" + safe_name
            r2_key = f"special/{new_qrcard_id}/{welcome_fname}"
            welcome_url = r2.upload_file(welcome_file, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": new_qrcard_id, "qr_type": "special", "file_name": welcome_fname})
            # Update both collections with the welcome image URL
            self.mgdDB.db_qrcard.update_one(
                {"qrcard_id": new_qrcard_id},
                {"$set": {"welcome_img_url": welcome_url}},
            )
            self.mgdDB.db_qrcard_special.update_one(
                {"qrcard_id": new_qrcard_id},
                {"$set": {"welcome_img_url": welcome_url}},
            )
        elif welcome_asset_url:
            welcome_url = ""
            lower = welcome_asset_url.lower()
            if lower.startswith("http://") or lower.startswith("https://"):
                welcome_url = welcome_asset_url
            elif welcome_asset_url.startswith("/static/"):
                static_file_path = os.path.join(root_path, welcome_asset_url.lstrip("/"))
                if os.path.exists(static_file_path):
                    ext = os.path.splitext(static_file_path)[1] or ".png"
                    filename = f"welcome_{uuid.uuid4().hex[:12]}{ext}"
                    r2_key = f"special/{new_qrcard_id}/{filename}"
                    with open(static_file_path, "rb") as _fh:
                        welcome_url = r2.upload(bytes_stream=_fh, key=r2_key)
            if welcome_url:
                self.mgdDB.db_qrcard.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}},
                )
                self.mgdDB.db_qrcard_special.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}},
                )

        # Handle uploaded images for special sections
        tmp_key = session.pop("special_tmp_key", None)
        if tmp_key:
            try:
                r2.delete_prefix(f"special/_tmp/{tmp_key}/")
            except Exception:
                pass
        session.modified = True

        return {"success": True, "qrcard_id": new_qrcard_id}

    def save_draft(self, request, session, root_path=None):
        """Create special QR as DRAFT: calls complete_special_save then downgrades status."""
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
                self.mgdDB.db_qrcard_special.delete_many({"qrcard_id": {"$in": old_ids}})
                self.mgdDB.db_qr_index.delete_many({"qrcard_id": {"$in": old_ids}})
        except Exception:
            pass
        result = self.complete_special_save(request, session, root_path)
        if not result.get("success"):
            return {"status": "error", "message_desc": result.get("error_msg", "Save failed.")}
        qrcard_id = result["qrcard_id"]
        self.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qrcard_special.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        self.mgdDB.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "DRAFT"}})
        qrcard = self.mgdDB.db_qrcard.find_one({"qrcard_id": qrcard_id}, {"short_code": 1}) or {}
        sc = qrcard.get("short_code", "")
        qr_encode_url = config.G_BASE_URL.rstrip("/") + "/special/" + sc if sc else ""
        return {"status": "ok", "qrcard_id": qrcard_id, "short_code": sc, "qr_encode_url": qr_encode_url}


# end class
