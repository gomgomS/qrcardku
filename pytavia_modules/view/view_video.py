from flask import render_template
import traceback


class view_video:
    """View layer for Video QR flow."""

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_content_html(self, msg=None, error_msg=None, base_url=None, url_content=None, qr_name=None, short_code=None, video_data=None):
        try:
            qrcard = video_data if video_data else None
            return render_template(
                "/user/new_qr_content_video.html",
                qr_type="video",
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
            return "Failed to load New QR Content (Video)"

    def new_qr_design_html(self, url_content=None, qr_name=None, short_code=None, qr_encode_url=None, msg=None, error_msg=None, video_data=None, qrcard_id=None, stats_carry=None):
        try:
            is_update = bool(qrcard_id)
            form_action = f"/qr/update/save/video/{qrcard_id}" if qrcard_id else "/qr/save/video"
            back_url = f"/qr/update/video/{qrcard_id}" if qrcard_id else "/qr/new/video"
            step1_url = "/qr/list" if qrcard_id else "/qr/new"
            step2_url = f"/qr/update/video/{qrcard_id}" if qrcard_id else "/qr/new/video"
            return render_template(
                "/user/new_qr_design_video.html",
                qr_type="video",
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg,
                video_data=video_data,
                stats_carry=stats_carry,
                form_action=form_action,
                qrcard_id=qrcard_id or "",
                is_update=is_update,
                back_url=back_url,
                step1_url=step1_url,
                step2_url=step2_url,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load New QR Design (Video)"
