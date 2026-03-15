from flask import render_template
import traceback


class view_links:
    """View layer for Links QR flow."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None,
                             qr_name=None, short_code=None, links_data=None):
        try:
            qrcard = links_data if links_data else None
            return render_template(
                "/user/new_qr_content_links.html",
                qr_type="links",
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
            return "Failed to load New QR Content (Links)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None,
                            qr_encode_url=None, msg=None, error_msg=None, links_data=None):
        try:
            return render_template(
                "/user/new_qr_design_links.html",
                qr_type="links",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                links_data=links_data or {},
                form_action="/qr/save/links",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Links)"
