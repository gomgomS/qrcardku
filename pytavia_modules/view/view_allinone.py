from flask import render_template
import traceback


class view_allinone:
    """View layer for All-in-One QR flow."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None,
                             qr_name=None, short_code=None, allinone_data=None):
        try:
            qrcard = allinone_data if allinone_data else None
            return render_template(
                "/user/new_qr_content_allinone.html",
                qr_type="allinone",
                msg=msg,
                error_msg=error_msg,
                base_url=base_url,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=short_code or "",
                qrcard=qrcard,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Content (All-in-One)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None,
                            qr_encode_url=None, msg=None, error_msg=None, allinone_data=None,
                            qrcard_id=None):
        try:
            form_action = f"/qr/update/save/allinone/{qrcard_id}" if qrcard_id else "/qr/save/allinone"
            return render_template(
                "/user/new_qr_design_allinone.html",
                qr_type="allinone",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                allinone_data=allinone_data or {},
                form_action=form_action,
                qrcard_id=qrcard_id or "",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (All-in-One)"
