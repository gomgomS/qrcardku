from flask import render_template
import traceback


class view_update_links:
    """View layer for Links QR update flow."""

    def __init__(self, app=None):
        self.webapp = app

    def update_qr_content_html(self, qrcard, url_content=None, qr_name=None, short_code=None,
                                msg=None, error_msg=None, base_url=None):
        try:
            cid = qrcard.get("qrcard_id")
            raw_url = (url_content if url_content is not None else (qrcard.get("url_content") or "")).strip()
            if raw_url.startswith("https://"):
                url_content_display = raw_url[8:]
            elif raw_url.startswith("http://"):
                url_content_display = raw_url[7:]
            else:
                url_content_display = raw_url
            # Ensure links list
            links_list = qrcard.get("Links_links", [])
            if not isinstance(links_list, list):
                links_list = []
            qrcard["Links_links"] = links_list
            return render_template(
                "/user/edit_qr_content_links.html",
                qr_type="links",
                qrcard_id=cid,
                qrcard=qrcard,
                links_list=links_list,
                url_content=url_content_display or "QRkartu",
                qr_name=(qr_name if qr_name is not None else qrcard.get("name")) or "",
                short_code=(short_code if short_code is not None else qrcard.get("short_code")) or "",
                form_action="/qr/update/links/{}".format(cid),
                back_url="/qr/list",
                step1_url="/qr/list",
                step3_url="/qr/update/links/qr-design/{}".format(cid),
                is_update=True,
                msg=msg,
                base_url=base_url,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Content (Links)"

    def update_qr_design_html(self, qrcard, url_content=None, qr_name=None,
                               qr_encode_url=None, msg=None, error_msg=None):
        try:
            cid = qrcard.get("qrcard_id")
            url_content = url_content or qrcard.get("url_content") or "QRkartu"
            qr_name = qr_name or qrcard.get("name") or "Untitled QR"
            return render_template(
                "/user/edit_qr_design_links.html",
                qr_type="links",
                qrcard_id=cid,
                qrcard=qrcard,
                url_content=url_content,
                qr_name=qr_name,
                short_code=qrcard.get("short_code") or "",
                qr_encode_url=qr_encode_url,
                form_action="/qr/update/save/links/{}".format(cid),
                back_url="/qr/update/links/{}".format(cid),
                step1_url="/qr/list",
                step2_url="/qr/update/links/{}".format(cid),
                is_update=True,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Design (Links)"
