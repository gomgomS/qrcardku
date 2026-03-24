from flask import render_template
import traceback


class view_web:
    """View layer for Web QR flow. No qr_type branching."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None, qr_name=None, short_code=None):
        try:
            return render_template(
                "/user/new_qr_content_web.html",
                qr_type="web",
                msg=msg,
                error_msg=error_msg,
                base_url=base_url,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=short_code or "",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Content (Web)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None, qr_encode_url=None, msg=None, error_msg=None, pdf_data=None, qrcard_id=None):
        try:
            form_action = f"/qr/update/save/web/{qrcard_id}" if qrcard_id else "/qr/save/web"
            return render_template(
                "/user/new_qr_design_web.html",
                qr_type="web",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                pdf_data=pdf_data,
                form_action=form_action,
                qrcard_id=qrcard_id or "",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Web)"
