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
                            qr_encode_url=None, msg=None, error_msg=None, links_data=None, qrcard_id=None, stats_carry=None):
        try:
            is_update = bool(qrcard_id)
            form_action = f"/qr/update/save/links/{qrcard_id}" if qrcard_id else "/qr/save/links"
            back_url = f"/qr/update/links/{qrcard_id}" if qrcard_id else "/qr/new/links"
            step1_url = "/qr/list" if qrcard_id else "/qr/new"
            step2_url = f"/qr/update/links/{qrcard_id}" if qrcard_id else "/qr/new/links"
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
                form_action=form_action,
                qrcard_id=qrcard_id or "",
                is_update=is_update,
                back_url=back_url,
                step1_url=step1_url,
                step2_url=step2_url,
                stats_carry=stats_carry,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Links)"
