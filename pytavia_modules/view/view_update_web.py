from flask import render_template
import traceback


class view_update_web:
    """View layer for Web QR update flow. Type-specific URLs (no qr_type param)."""

    def __init__(self, app=None):
        self.webapp = app

    def update_qr_content_html(self, qrcard, url_content=None, qr_name=None, short_code=None, msg=None, error_msg=None, base_url=None):
        """Step 1 (content): edit_qr_content_web.html with /qr/update/web/<id> and /qr/update/web/qr-design/<id>."""
        try:
            cid = qrcard.get("qrcard_id")
            raw_url = (url_content if url_content is not None else (qrcard.get("url_content") or "")).strip()
            if raw_url.startswith("https://"):
                url_content_display = raw_url[8:]
            elif raw_url.startswith("http://"):
                url_content_display = raw_url[7:]
            else:
                url_content_display = raw_url
            return render_template(
                "/user/edit_qr_content_web.html",
                qr_type="web",
                qrcard_id=cid,
                qrcard=qrcard,
                url_content=url_content_display or "qrcardku.com",
                qr_name=(qr_name if qr_name is not None else qrcard.get("name")) or "",
                short_code=(short_code if short_code is not None else qrcard.get("short_code")) or "",
                form_action="/qr/update/web/{}".format(cid),
                back_url="/qr/list",
                step1_url="/qr/list",
                step3_url="/qr/update/web/qr-design/{}".format(cid),
                is_update=True,
                msg=msg,
                base_url=base_url,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Content (Web)"

    def update_qr_design_html(self, qrcard, url_content=None, qr_name=None, qr_encode_url=None, msg=None, error_msg=None):
        """Step 2 (design): edit_qr_design_web.html with /qr/update/save/web/<id> and back to content."""
        try:
            cid = qrcard.get("qrcard_id")
            url_content = url_content or qrcard.get("url_content") or "qrcardku.com"
            qr_name = qr_name or qrcard.get("name") or "Untitled QR"
            return render_template(
                "/user/edit_qr_design_web.html",
                qr_type="web",
                qrcard_id=cid,
                qrcard=qrcard,
                url_content=url_content,
                qr_name=qr_name,
                short_code=qrcard.get("short_code") or "",
                qr_encode_url=qr_encode_url,
                form_action="/qr/update/save/web/{}".format(cid),
                back_url="/qr/update/web/{}".format(cid),
                step1_url="/qr/list",
                step2_url="/qr/update/web/{}".format(cid),
                is_update=True,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Design (Web)"
