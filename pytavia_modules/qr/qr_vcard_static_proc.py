"""Processor for vCard static QR cards (vCard 3.0 text encoded directly into QR)."""
import sys
import time
import uuid
import traceback
from datetime import datetime

sys.path.append("pytavia_core")

from pytavia_core import database, config

_TYPE_MAP = {"office": "WORK,VOICE", "mobile": "CELL,VOICE", "fax": "FAX", "others": "VOICE"}


def _escape_vcard(s):
    return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _build_vcard(first_name, surname, company, title, phones, email, website):
    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    lines.append("N:{};{};;;".format(_escape_vcard(surname), _escape_vcard(first_name)))
    fn = (first_name + " " + surname).strip()
    if fn:
        lines.append("FN:" + _escape_vcard(fn))
    if company:
        lines.append("ORG:" + _escape_vcard(company))
    if title:
        lines.append("TITLE:" + _escape_vcard(title))
    for p in phones:
        num = (p.get("number") or "").strip()
        if num:
            t = _TYPE_MAP.get(p.get("type", "mobile"), "VOICE")
            lines.append("TEL;TYPE={}:{}".format(t, num))
    if email:
        lines.append("EMAIL:" + email)
    if website:
        url = website if website.startswith("http") else "https://" + website
        lines.append("URL:" + url)
    lines.append("END:VCARD")
    return "\r\n".join(lines)


class qr_vcard_static_proc:

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
            return self.mgdDB.db_qrcard_vcard_static.find_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
            )
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def add_qrcard_vcard_static(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            name = params.get("name", "Untitled QR")
            first_name = params.get("vcard_first_name", "").strip()
            surname = params.get("vcard_surname", "").strip()
            company = params.get("vcard_company", "").strip()
            title = params.get("vcard_title", "").strip()
            phones = params.get("vcard_phones", [])
            email = params.get("vcard_email", "").strip()
            website = params.get("vcard_website", "").strip()

            if not fk_user_id:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "User authentication required.", "message_data": {}}
            if not first_name:
                return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "First name is required.", "message_data": {}}

            url_content = _build_vcard(first_name, surname, company, title, phones, email, website)
            qrcard_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Base record — grouping only
            base = database.get_record("db_qrcard")
            base["qrcard_id"] = qrcard_id
            base["fk_user_id"] = fk_user_id
            base["qr_type"] = "vcard-static"
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
            detail = database.get_record("db_qrcard_vcard_static")
            detail["qrcard_id"] = qrcard_id
            detail["fk_user_id"] = fk_user_id
            detail["qr_type"] = "vcard-static"
            detail["name"] = name
            detail["vcard_first_name"] = first_name
            detail["vcard_surname"] = surname
            detail["vcard_company"] = company
            detail["vcard_title"] = title
            detail["vcard_phones"] = phones
            detail["vcard_email"] = email
            detail["vcard_website"] = website
            detail["url_content"] = url_content
            detail["short_code"] = ""
            detail["stats"] = {"scan_count": 0}
            detail["scan_limit_enabled"] = False
            detail["scan_limit_value"] = 0
            detail["status"] = "ACTIVE"
            detail["created_at"] = created_at
            detail["timestamp"] = current_time
            self.mgdDB.db_qrcard_vcard_static.insert_one(detail)

            # Index
            idx = database.get_record("db_qr_index")
            idx["qrcard_id"] = qrcard_id
            idx["fk_user_id"] = fk_user_id
            idx["qr_type"] = "vcard-static"
            idx["name"] = name
            idx["short_code"] = ""
            idx["status"] = "ACTIVE"
            idx["created_at"] = created_at
            idx["timestamp"] = current_time
            self.mgdDB.db_qr_index.insert_one(idx)

            return {"message_action": "ADD_QRCARD_SUCCESS", "message_desc": "vCard QR saved successfully.", "message_data": {"qrcard_id": qrcard_id}}
        except Exception:
            self.webapp.logger.debug(traceback.format_exc())
            return {"message_action": "ADD_QRCARD_FAILED", "message_desc": "An internal error occurred.", "message_data": {}}

    def edit_qrcard_vcard_static(self, params):
        try:
            fk_user_id = params.get("fk_user_id")
            qrcard_id = params.get("qrcard_id")
            name = params.get("name")
            first_name = params.get("vcard_first_name", "").strip()
            surname = params.get("vcard_surname", "").strip()
            company = params.get("vcard_company", "").strip()
            title = params.get("vcard_title", "").strip()
            phones = params.get("vcard_phones", [])
            email = params.get("vcard_email", "").strip()
            website = params.get("vcard_website", "").strip()
            url_content = _build_vcard(first_name, surname, company, title, phones, email, website)

            self.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {"name": name}},
            )
            self.mgdDB.db_qrcard_vcard_static.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {
                    "name": name,
                    "vcard_first_name": first_name,
                    "vcard_surname": surname,
                    "vcard_company": company,
                    "vcard_title": title,
                    "vcard_phones": phones,
                    "vcard_email": email,
                    "vcard_website": website,
                    "url_content": url_content,
                }},
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
