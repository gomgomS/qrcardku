from flask import render_template
import traceback


class view_ecard:
    """View layer for E-card QR flow. No qr_type branching."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None, qr_name=None, short_code=None, ecard_data=None, phone_list=None, email_list=None, website_list=None):
        try:
            # When returning from design (Back), ecard_data is passed as qrcard so the form pre-fills
            qrcard = ecard_data if ecard_data else None
            return render_template(
                "/user/new_qr_content_ecard.html",
                qr_type="ecard",
                msg=msg,
                error_msg=error_msg,
                base_url=base_url,
                url_content=url_content or "",
                qr_name=qr_name or "",
                short_code=short_code or "",
                qrcard=qrcard,
                phone_list=phone_list,
                email_list=email_list,
                website_list=website_list,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Content (E-card)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None, qr_encode_url=None, msg=None, error_msg=None, ecard_data=None):
        try:
            return render_template(
                "/user/new_qr_design_ecard.html",
                qr_type="ecard",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                ecard_data=ecard_data,
                form_action="/qr/save/ecard",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (E-card)"
