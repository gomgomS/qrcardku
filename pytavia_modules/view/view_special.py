from flask import render_template
import traceback


class view_special:
    """View layer for Special QR flow (new)."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None,
                            url_content=None, qr_name=None, short_code=None,
                            special_sections=None, content_stats_prefill=None):
        try:
            return render_template(
                "/user/new_qr_content_special.html",
                qr_type="special",
                msg=msg,
                error_msg=error_msg,
                base_url=base_url,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=short_code or "",
                special_sections=special_sections or [],
                content_stats_prefill=content_stats_prefill or {},
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Content (Special)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None,
                           qr_encode_url=None, msg=None, error_msg=None,
                           special_sections=None, qrcard_id=None, stats_carry=None):
        try:
            form_action = f"/qr/update/save/special/{qrcard_id}" if qrcard_id else "/qr/save/special"
            return render_template(
                "/user/new_qr_design_special.html",
                qr_type="special",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                special_sections=special_sections or [],
                form_action=form_action,
                qrcard_id=qrcard_id or "",
                stats_carry=stats_carry or {},
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Special)"
