import sys

sys.path.append("pytavia_core")

from flask import render_template
from pytavia_core import database, config

from .qr_public_visual_helper import enforce_scan_limit_and_increment, normalize_ecard_contact_lists


class qr_public_ecard_visual_proc:
    """Standalone public landing handler for E-card QR cards."""

    def __init__(self, app):
        self.webapp = app
        self.mgdDB = database.get_db_conn(config.mainDB)

    def get_qrcard_by_short_code(self, short_code):
        try:
            return self.mgdDB.db_qrcard.find_one(
                {"short_code": short_code, "status": "ACTIVE"}
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(
                    "qr_public_ecard_visual_proc.get_qrcard_by_short_code failed",
                    exc_info=True,
                )
            return None

    def handle(self, short_code):
        qrcard = self.get_qrcard_by_short_code(short_code)
        qrcard = enforce_scan_limit_and_increment(qrcard, self.mgdDB, self.webapp)
        if not qrcard or (qrcard.get("qr_type") or "web") != "ecard":
            return render_template("user/public_not_found.html"), 404
        # Merge ecard-specific doc (has phones, emails, websites, design fields) over the base doc
        try:
            ecard_doc = self.mgdDB.db_qrcard_ecard.find_one({"qrcard_id": qrcard.get("qrcard_id")})
            if ecard_doc:
                merged = dict(qrcard)
                for key, value in ecard_doc.items():
                    if key != "_id":
                        merged[key] = value
                qrcard = merged
        except Exception:
            pass
        qrcard = normalize_ecard_contact_lists(qrcard)
        return render_template("/user/public_ecard.html", qrcard=qrcard)
