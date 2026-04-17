import sys

sys.path.append("pytavia_core")

from flask import redirect, render_template
from pytavia_core import database, config

from .qr_public_visual_helper import enforce_scan_limit_and_increment


class qr_public_web_visual_proc:
    """Standalone public redirect handler for web-type QR cards."""

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
                    "qr_public_web_visual_proc.get_qrcard_by_short_code failed",
                    exc_info=True,
                )
            return None

    def handle(self, short_code):
        qrcard = self.get_qrcard_by_short_code(short_code)
        qrcard = enforce_scan_limit_and_increment(qrcard, self.mgdDB, self.webapp)
        if not qrcard or (qrcard.get("qr_type") or "web") != "web":
            return render_template("user/public_not_found.html"), 404
        dest = (qrcard.get("url_content") or "").strip()
        if not dest:
            return render_template("user/public_not_found.html"), 404
        if not dest.startswith("http://") and not dest.startswith("https://"):
            dest = "https://" + dest
        return redirect(dest, code=302)
