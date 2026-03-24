from flask import render_template
import traceback


class view_images:
    """View layer for Images (image gallery) QR flow."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None, qr_name=None, short_code=None, images_data=None):
        try:
            qrcard = images_data if images_data else None
            return render_template(
                "/user/new_qr_content_images.html",
                qr_type="images",
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
            return "Failed to load New QR Content (Images)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None, qr_encode_url=None, msg=None, error_msg=None, images_data=None, qrcard_id=None):
        try:
            form_action = f"/qr/update/save/images/{qrcard_id}" if qrcard_id else "/qr/save/images"
            return render_template(
                "/user/new_qr_design_images.html",
                qr_type="images",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                images_data=images_data,
                form_action=form_action,
                qrcard_id=qrcard_id or "",
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Images)"
