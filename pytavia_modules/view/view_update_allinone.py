from flask import render_template
import traceback


class view_update_allinone:
    """View layer for All-in-One QR update flow."""

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
            # Ensure sections list
            sections = qrcard.get("Allinone_sections", [])
            if not isinstance(sections, list):
                sections = []
            qrcard["Allinone_sections"] = sections
            return render_template(
                "/user/edit_qr_content_allinone.html",
                qr_type="allinone",
                qrcard_id=cid,
                qrcard=qrcard,
                sections=sections,
                url_content=url_content_display or "QRkartu",
                qr_name=(qr_name if qr_name is not None else qrcard.get("name")) or "",
                short_code=(short_code if short_code is not None else qrcard.get("short_code")) or "",
                form_action="/qr/update/allinone/{}".format(cid),
                back_url="/qr/list",
                step1_url="/qr/list",
                step3_url="/qr/update/allinone/qr-design/{}".format(cid),
                is_update=True,
                msg=msg,
                base_url=base_url,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Content (All-in-One)"

    def update_qr_design_html(self, qrcard, url_content=None, qr_name=None,
                               qr_encode_url=None, msg=None, error_msg=None):
        try:
            cid = qrcard.get("qrcard_id")
            url_content = url_content or qrcard.get("url_content") or "QRkartu"
            qr_name = qr_name or qrcard.get("name") or "Untitled QR"
            return render_template(
                "/user/edit_qr_design_allinone.html",
                qr_type="allinone",
                qrcard_id=cid,
                qrcard=qrcard,
                url_content=url_content,
                qr_name=qr_name,
                short_code=qrcard.get("short_code") or "",
                qr_encode_url=qr_encode_url,
                form_action="/qr/update/save/allinone/{}".format(cid),
                back_url="/qr/update/allinone/{}".format(cid),
                step1_url="/qr/list",
                step2_url="/qr/update/allinone/{}".format(cid),
                is_update=True,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return "Failed to load Update QR Design (All-in-One)"
