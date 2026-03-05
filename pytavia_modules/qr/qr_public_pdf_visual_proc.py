import sys

sys.path.append("pytavia_core")

from flask import abort, render_template
from pytavia_core import database, config

from .qr_public_visual_helper import enforce_scan_limit_and_increment


class qr_public_pdf_visual_proc:
    """Standalone public landing handler for PDF-type QR cards. Uses db_qrcard_pdf then db_qrcard; syncs scan count to db_qrcard_pdf."""

    def __init__(self, app):
        self.webapp = app
        self.mgdDB = database.get_db_conn(config.mainDB)

    def get_qrcard_by_short_code(self, short_code):
        try:
            doc = self.mgdDB.db_qrcard_pdf.find_one(
                {"short_code": short_code, "status": "ACTIVE"}
            )
            if doc:
                return doc
            return self.mgdDB.db_qrcard.find_one(
                {"short_code": short_code, "status": "ACTIVE"}
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(
                    "qr_public_pdf_visual_proc.get_qrcard_by_short_code failed",
                    exc_info=True,
                )
            return None

    def handle(self, short_code):
        qrcard = self.get_qrcard_by_short_code(short_code)
        qrcard = enforce_scan_limit_and_increment(qrcard, self.mgdDB, self.webapp)
        if not qrcard or (qrcard.get("qr_type") or "web") != "pdf":
            abort(404)
        try:
            self.mgdDB.db_qrcard_pdf.update_one(
                {"qrcard_id": qrcard.get("qrcard_id"), "status": "ACTIVE"},
                {"$inc": {"stats.scan_count": 1}},
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(
                    "qr_public_pdf_visual_proc increment db_qrcard_pdf failed",
                    exc_info=True,
                )
        return render_template("/user/public_pdf.html", qrcard=qrcard)
