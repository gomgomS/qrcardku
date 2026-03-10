from flask import render_template
import traceback


class view_update_special:
    """View layer for editing Special QR cards."""

    def __init__(self, app=None):
        self.webapp = app

    def update_qr_content_html(self, qrcard=None, url_content=None, qr_name=None,
                               short_code=None, msg=None, error_msg=None,
                               base_url=None, special_sections=None):
        try:
            return render_template(
                "/user/edit_qr_content_special.html",
                qr_type="special",
                qrcard=qrcard,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=short_code or "",
                msg=msg,
                error_msg=error_msg,
                base_url=base_url,
                special_sections=special_sections or [],
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Edit QR Content (Special)"

    def update_qr_design_html(self, qrcard=None, url_content=None, qr_name=None,
                              qr_encode_url=None, msg=None, error_msg=None,
                              special_sections=None):
        try:
            return render_template(
                "/user/edit_qr_design_special.html",
                qr_type="special",
                qrcard=qrcard,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=qrcard.get("short_code", "") if qrcard else "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                is_update=True,
                special_sections=special_sections or [],
                form_action="/qr/update/save/special/" + (qrcard.get("qrcard_id", "") if qrcard else ""),
                back_url="/qr/update/special/" + (qrcard.get("qrcard_id", "") if qrcard else ""),
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Edit QR Design (Special)"
