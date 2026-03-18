"""Processor for WhatsApp static QR cards (wa.me URL encoded directly into QR)."""
import sys
import time
import uuid
import traceback
from datetime import datetime
from urllib.parse import quote

sys.path.append("pytavia_core")

from pytavia_core import database, config


class qr_wa_static_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def is_name_unique(self, fk_user_id, name, exclude_id=None):
        try:
            query = {"fk_user_id": fk_user_id, "name": name, "status": "ACTIVE"}
            if exclude_id:
                query["qrcard_id"] = {"$ne": exclude_id}
            return self.mgdDB.db_qrcard.find_one(query) is None
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return False

    def get_qrcard(self, fk_user_id, qrcard_id):
        try:
            return self.mgdDB.db_qrcard_wa_static.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def _build_wa_url(self, wa_phone, wa_message):
        url = "https://wa.me/" + wa_phone.replace(" ", "")
        if wa_message:
            url += "?text=" + quote(wa_message)
        return url

    def add_qrcard_wa_static(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            name = params.get("name", "Untitled QR")
            wa_phone = params.get("wa_phone", "").strip()
            wa_message = params.get("wa_message", "").strip()

            if not fk_user_id:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "User authentication required.", "message_data": {}}
            if not wa_phone:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "Phone number is required.", "message_data": {}}

            url_content = self._build_wa_url(wa_phone, wa_message)
            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Base record — grouping only
            base = database.get_record("db_qrcard")
            base["qrcard_id"] = qrcard_id
            base["fk_user_id"] = fk_user_id
            base["qr_type"] = "wa-static"
            base["name"] = name
            base["short_code"] = ""
            base["url_content"] = ""
            base["design_data"] = {}
            base["qr_image_url"] = ""
            base["stats"] = {"scan_count": 0}
            base["scan_limit_enabled"] = False
            base["scan_limit_value"] = 0
            base["status"] = "ACTIVE"
            base["created_at"] = created_at
            base["timestamp"] = current_time
            self.mgdDB.db_qrcard.insert_one(base)

            # Detail record
            detail = database.get_record("db_qrcard_wa_static")
            detail["qrcard_id"] = qrcard_id
            detail["fk_user_id"] = fk_user_id
            detail["qr_type"] = "wa-static"
            detail["name"] = name
            detail["wa_phone"] = wa_phone
            detail["wa_message"] = wa_message
            detail["url_content"] = url_content
            detail["short_code"] = ""
            detail["stats"] = {"scan_count": 0}
            detail["scan_limit_enabled"] = False
            detail["scan_limit_value"] = 0
            detail["status"] = "ACTIVE"
            detail["created_at"] = created_at
            detail["timestamp"] = current_time
            self.mgdDB.db_qrcard_wa_static.insert_one(detail)

            # Index
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "wa-static"
            idx["name"] = name
            idx["short_code"] = ""
            idx["status"] = "ACTIVE"
            idx["created_at"] = created_at
            idx["timestamp"] = current_time
            self.mgdDB.db_qr_index.insert_one(idx)

            return {"message_action": "ADD_QRCARD_SUCCESS", "message_desc": "WhatsApp QR card saved successfully.", "message_data": {"qrcard_id": qrcard_id}}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "An internal error occurred.", "message_data": {}}

    def edit_qrcard_wa_static(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            name = params.get("name")
            wa_phone = params.get("wa_phone", "").strip()
            wa_message = params.get("wa_message", "").strip()
            url_content = self._build_wa_url(wa_phone, wa_message)

            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"name": name}},
            )
            self.mgdDB.db_qrcard_wa_static.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"name": name, "wa_phone": wa_phone, "wa_message": wa_message, "url_content": url_content}},
                upsert=True,
            )
            self.mgdDB.db_qr_index.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"name": name}},
            )
            return {"status": "SUCCESS"}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"status": "FAILED"}
