"""View and logic for the QR list page. All listing logic lives here so server routes stay thin."""
from flask import render_template
import traceback

from pytavia_core import database, config


class view_qr_list:
    def __init__(self, app=None):
        self.webapp = app

    def my_qr_codes_html(self, fk_user_id, msg=None, error_msg=None):
        """
        Build QR list from db_qr_index + type-specific collections, then render my_qr_codes.html.
        Each QR type has its own dedicated collection; db_qrcard is grouping only.
        """
        try:
            mgdDB = database.get_db_conn(config.mainDB)

            index_entries = list(
                mgdDB.db_qr_index.find(
                    {"fk_user_id": fk_user_id, "status": "ACTIVE"}
                ).sort("timestamp", -1)
            )

            # Collect IDs per type
            id_by_type = {
                "web": [], "ecard": [], "pdf": [],
                "web-static": [], "text": [],
                "wa-static": [], "email-static": [], "vcard-static": [],
            }
            for e in index_entries:
                t = e.get("qr_type") or "web"
                if t in id_by_type:
                    id_by_type[t].append(e["qrcard_id"])

            full_by_id = {}

            # web and ecard — still read from db_qrcard (legacy)
            _web_ecard_ids = id_by_type["web"] + id_by_type["ecard"]
            if _web_ecard_ids:
                for doc in mgdDB.db_qrcard.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": _web_ecard_ids},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # pdf — dedicated collection
            if id_by_type["pdf"]:
                for doc in mgdDB.db_qrcard_pdf.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["pdf"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # web-static — dedicated collection
            if id_by_type["web-static"]:
                for doc in mgdDB.db_qrcard_web_static.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["web-static"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # text — dedicated collection
            if id_by_type["text"]:
                for doc in mgdDB.db_qrcard_text.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["text"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # wa-static — dedicated collection
            if id_by_type["wa-static"]:
                for doc in mgdDB.db_qrcard_wa_static.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["wa-static"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # email-static — dedicated collection
            if id_by_type["email-static"]:
                for doc in mgdDB.db_qrcard_email_static.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["email-static"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            # vcard-static — dedicated collection
            if id_by_type["vcard-static"]:
                for doc in mgdDB.db_qrcard_vcard_static.find({
                    "fk_user_id": fk_user_id,
                    "qrcard_id": {"$in": id_by_type["vcard-static"]},
                    "status": "ACTIVE",
                }):
                    full_by_id[doc["qrcard_id"]] = doc

            qr_list = []
            for e in index_entries:
                qid = e.get("qrcard_id")
                full = full_by_id.get(qid)
                if full is not None:
                    qr_list.append(full)
                else:
                    # Fallback: use index row with minimal defaults so template does not break
                    row = dict(e)
                    if "stats" not in row:
                        row["stats"] = {"scan_count": 0}
                    if "url_content" not in row:
                        row["url_content"] = ""
                    if "scan_limit_enabled" not in row:
                        row["scan_limit_enabled"] = False
                    if "scan_limit_value" not in row:
                        row["scan_limit_value"] = 0
                    qr_list.append(row)

            return render_template(
                "/user/my_qr_codes.html",
                qr_list=qr_list,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load My QR Codes page"
