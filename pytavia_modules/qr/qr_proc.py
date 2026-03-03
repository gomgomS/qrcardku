import time
import pymongo
import sys
import traceback
import uuid
import random
import string
from datetime import datetime

sys.path.append("pytavia_core")
from pytavia_core import database
from pytavia_core import config

SHORT_CODE_LENGTH = 8
SHORT_CODE_CHARS = string.ascii_lowercase + string.digits

class qr_proc:

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
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def get_qrcard_by_short_code(self, short_code):
        try:
            return self.mgdDB.db_qrcard.find_one({
                "short_code": short_code,
                "status": "ACTIVE"
            })
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def increment_scan_count(self, fk_user_id, qrcard_id):
        """Increment total scan count for a qrcard."""
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"},
                {"$inc": {"stats.scan_count": 1}}
            )
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())

    def add_qrcard(self, params):
        try:
            fk_user_id  = params.get("fk_user_id")
            qr_type     = params.get("qr_type", "web")
            name        = params.get("name", "Untitled QR")
            url_content = params.get("url_content", "")
            short_code  = (params.get("short_code") or "").strip().lower()

            # Simple validation
            if not fk_user_id:
               return {
                    "message_action": "ADD_QRCARD_FAILED",
                    "message_desc": "User authentication required.",
                    "message_data": {}
               }
            if not url_content:
                return {
                    "message_action": "ADD_QRCARD_FAILED",
                    "message_desc": "URL Content is required.",
                    "message_data": {}
               }

            # Dynamic types (web/pdf): require unique short_code (generate or validate custom)
            if qr_type in ("web", "pdf"):
                if short_code:
                    import re
                    if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                        return {
                            "message_action": "ADD_QRCARD_FAILED",
                            "message_desc": "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols.",
                            "message_data": {}
                        }
                    if not self.is_short_code_unique(short_code):
                        return {
                            "message_action": "ADD_QRCARD_FAILED",
                            "message_desc": "This address identifier is already in use. Please choose another.",
                            "message_data": {}
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
                            "message_data": {}
                        }
            else:
                short_code = ""

            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Prepare Record
            qrcard_rec = database.get_record("db_qrcard")
            qrcard_rec["qrcard_id"]   = qrcard_id
            qrcard_rec["fk_user_id"]  = fk_user_id
            qrcard_rec["qr_type"]     = qr_type
            qrcard_rec["name"]        = name
            qrcard_rec["url_content"] = url_content
            qrcard_rec["short_code"]  = short_code
            qrcard_rec["design_data"] = {}
            qrcard_rec["qr_image_url"]= ""
            
            if qr_type == "pdf":
                pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color",
                              "pdf_title_font", "pdf_title_color", "pdf_text_font",
                              "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                              "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                              "welcome_img_url", "pdf_font_apply_all",
                              "pdf_t1_header_img_url", "pdf_t3_circle_img_url", "pdf_t4_circle_img_url"]
                for f in pdf_fields:
                    qrcard_rec[f] = params.get(f, "")
            
            # Scan statistics and optional limit
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

            qrcard_rec["status"]      = "ACTIVE"
            qrcard_rec["created_at"]  = created_at
            qrcard_rec["timestamp"]   = current_time

            # Insert into database
            self.mgdDB.db_qrcard.insert_one(qrcard_rec)

            return {
                "message_action": "ADD_QRCARD_SUCCESS",
                "message_desc": "QR card generated and saved successfully.",
                "message_data": {"qrcard_id": qrcard_id}
            }

        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "ADD_QRCARD_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }

    def get_qrcard_by_user(self, fk_user_id):
        try:
            # Retrieve all QR codes for a user, sorted by most recent first
            qrcard_list = list(self.mgdDB.db_qrcard.find({"fk_user_id": fk_user_id, "status": "ACTIVE"}).sort("timestamp", -1))
            return qrcard_list
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def get_qrcard(self, fk_user_id, qrcard_id):
        try:
            return self.mgdDB.db_qrcard.find_one({
                "fk_user_id": fk_user_id, 
                "qrcard_id": qrcard_id, 
                "status": "ACTIVE"
            })
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def edit_qrcard(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id  = params.get("qrcard_id")
            name       = params.get("name")
            url_content= params.get("url_content")
            
            update_data = {
                "name": name,
                "url_content": url_content,
            }
            
            pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color",
                          "pdf_title_font", "pdf_title_color", "pdf_text_font",
                          "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                          "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                          "welcome_img_url", "pdf_font_apply_all",
                          "pdf_t1_header_img_url", "pdf_t3_circle_img_url", "pdf_t4_circle_img_url"]
            for f in pdf_fields:
                if f in params:
                    update_data[f] = params.get(f)

            # Scan limit fields
            if "scan_limit_enabled" in params:
                update_data["scan_limit_enabled"] = bool(params.get("scan_limit_enabled"))
            if "scan_limit_value" in params:
                try:
                    limit_raw = params.get("scan_limit_value", 0)
                    limit_val = int(limit_raw) if str(limit_raw).strip().isdigit() else 0
                    update_data["scan_limit_value"] = max(limit_val, 0)
                except Exception:
                    pass

            # Optionally update short_code for dynamic types (web/pdf) when a new, valid, unique code is provided
            try:
                doc = self.get_qrcard(fk_user_id, qrcard_id)
            except Exception:
                doc = None
            if doc and doc.get("qr_type") in ("web", "pdf"):
                new_short = (params.get("short_code") or "").strip().lower()
                current_short = (doc.get("short_code") or "").strip().lower()
                if new_short and new_short != current_short:
                    import re
                    if re.match(r"^[a-z0-9_-]{2,32}$", new_short) and self.is_short_code_unique(new_short, exclude_qrcard_id=qrcard_id):
                        update_data["short_code"] = new_short

            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": update_data}
            )
            return {"status": "SUCCESS", "message": "QR card updated."}
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return {"status": "FAILED", "message": "Error updating QR card."}

    def is_name_unique(self, fk_user_id, name, exclude_id=None):
        try:
            query = {"fk_user_id": fk_user_id, "name": name, "status": "ACTIVE"}
            if exclude_id:
                query["qrcard_id"] = {"$ne": exclude_id}
            
            existing = self.mgdDB.db_qrcard.find_one(query)
            return existing is None
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            # Default to false on error to prevent accidental duplicates
            return False

    def delete_qrcard(self, fk_user_id, qrcard_id):
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"status": "DELETED"}}
            )
            return True
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def update_pdf_files(self, fk_user_id, qrcard_id, pdf_files_list):
        """Store/replace the list of uploaded PDF file metadata for a qrcard."""
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"pdf_files": pdf_files_list}}
            )
            return True
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def remove_pdf_file(self, fk_user_id, qrcard_id, file_url):
        """Remove a single PDF file entry from the stored list by its URL."""
        try:
            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$pull": {"pdf_files": {"url": file_url}}}
            )
            return True
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return False
