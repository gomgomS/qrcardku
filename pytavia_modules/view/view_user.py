from flask import render_template
import sys
import traceback

class view_user:

    def __init__(self, app=None):
        self.webapp = app

    def new_qr_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/new_qr.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load New QR page"

    def new_qr_type_html(self, qr_type, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/new_qr_content.html",
                qr_type=qr_type,
                msg=msg, 
                error_msg=error_msg
            )
        except:
            return "Failed to load New QR Content Form"

    def new_qr_design_html(self, qr_type, url_content=None, qr_name=None, short_code=None, qr_encode_url=None, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/new_qr_design.html",
                qr_type=qr_type,
                url_content=url_content,
                qr_name=qr_name,
                short_code=short_code or "",
                qr_encode_url=qr_encode_url,
                msg=msg,
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load New QR Design Form"

    def edit_qr_content_html(self, qrcard, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/edit_qr_content.html",
                qrcard=qrcard,
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Edit QR Form"

    def update_qr_content_html(self, qr_type, qrcard, url_content=None, qr_name=None, short_code=None, msg=None, error_msg=None):
        """Step-based update: content step (reuses new_qr_content layout with update URLs and prefills). url_content/qr_name optional when re-rendering from Back from design."""
        try:
            raw_url = (url_content if url_content is not None else (qrcard.get("url_content") or "")).strip()
            if raw_url.startswith("https://"):
                url_content_display = raw_url[8:]
            elif raw_url.startswith("http://"):
                url_content_display = raw_url[7:]
            else:
                url_content_display = raw_url
            return render_template(
                "/user/new_qr_content.html",
                qr_type=qr_type,
                qrcard_id=qrcard.get("qrcard_id"),
                url_content=url_content_display or "qrcardku.com",
                qr_name=(qr_name if qr_name is not None else qrcard.get("name")) or "",
                short_code=(short_code if short_code is not None else qrcard.get("short_code")) or "",
                form_action="/qr/update/{}/qr-design/{}".format(qr_type, qrcard.get("qrcard_id")),
                back_url="/qr/list",
                step1_url="/qr/list",
                step3_url="/qr/update/{}/qr-design/{}".format(qr_type, qrcard.get("qrcard_id")),
                is_update=True,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception as e:
            print(traceback.format_exc())
            return "Failed to load Update QR Content step"

    def update_qr_design_html(self, qr_type, qrcard, url_content=None, qr_name=None, qr_encode_url=None, msg=None, error_msg=None):
        """Step-based update: design step (reuses new_qr_design layout with update URLs)."""
        try:
            url_content = url_content or qrcard.get("url_content") or "qrcardku.com"
            qr_name = qr_name or qrcard.get("name") or "Untitled QR"
            cid = qrcard.get("qrcard_id")
            return render_template(
                "/user/new_qr_design.html",
                qr_type=qr_type,
                qrcard_id=cid,
                qrcard=qrcard,
                url_content=url_content,
                qr_name=qr_name,
                short_code=qrcard.get("short_code") or "",
                qr_encode_url=qr_encode_url,
                form_action="/qr/update/save/{}".format(cid),
                back_url="/qr/update/{}/{}".format(qr_type, cid),
                step1_url="/qr/list",
                step2_url="/qr/update/{}/{}".format(qr_type, cid),
                is_update=True,
                msg=msg,
                error_msg=error_msg,
            )
        except Exception as e:
            print(traceback.format_exc())
            return "Failed to load Update QR Design step"

    def my_qr_codes_html(self, qr_list=None, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/my_qr_codes.html",
                qr_list=qr_list,
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load My QR Codes page"

    def stats_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/stats.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Stats page"

    def templates_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/templates.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Templates page"

    def settings_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/settings.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Settings page"

    def users_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/users.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Users page"

    def security_history_html(self, msg=None, error_msg=None):
        try:
            return render_template(
                "/user/security_history.html",
                msg=msg, 
                error_msg=error_msg
            )
        except:
            print(traceback.format_exc())
            return "Failed to load Security History page"
