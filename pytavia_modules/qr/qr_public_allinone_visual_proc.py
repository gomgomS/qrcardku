import sys

sys.path.append("pytavia_core")

from flask import abort, render_template
from pytavia_core import database, config

from .qr_public_visual_helper import enforce_scan_limit_and_increment


class qr_public_allinone_visual_proc:
    """Standalone public landing handler for All-in-One QR cards."""

    def __init__(self, app):
        self.webapp = app
        self.mgdDB = database.get_db_conn(config.mainDB)

    def get_qrcard_by_short_code(self, short_code):
        try:
            return self.mgdDB.db_qrcard.find_one({"short_code": short_code, "status": "ACTIVE"})
        except Exception:
            if self.webapp:
                self.webapp.logger.debug("qr_public_allinone_visual_proc.get_qrcard_by_short_code failed", exc_info=True)
            return None

    def handle(self, short_code):
        qrcard = self.get_qrcard_by_short_code(short_code)
        if not qrcard or (qrcard.get("qr_type") or "") != "allinone":
            abort(404)
        try:
            allinone_doc = self.mgdDB.db_qrcard_allinone.find_one({"qrcard_id": qrcard.get("qrcard_id")})
            if allinone_doc:
                merged = dict(qrcard)
                for key, value in allinone_doc.items():
                    if key != "_id":
                        merged[key] = value
                qrcard = merged
        except Exception:
            pass
        qrcard = enforce_scan_limit_and_increment(qrcard, self.mgdDB, self.webapp)
        # Ensure Allinone_sections is a proper list
        sections = qrcard.get("Allinone_sections", [])
        if not isinstance(sections, list):
            sections = []
        qrcard["Allinone_sections"] = sections
        return render_template("/user/public_allinone.html", qrcard=qrcard)
