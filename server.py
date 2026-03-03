import json
import time
import pymongo
import sys
import urllib.parse
import base64
import urllib
import ast
import pdfkit
import html as html_unescape

from urllib.parse import urlencode

sys.path.append("pytavia_core")
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib")
sys.path.append("pytavia_storage")
sys.path.append("pytavia_modules")
sys.path.append("pytavia_modules/auth")
sys.path.append("pytavia_modules/admin")
sys.path.append("pytavia_modules/landing")
sys.path.append("pytavia_modules/configuration")
sys.path.append("pytavia_modules/cookie")
sys.path.append("pytavia_modules/middleware")
sys.path.append("pytavia_modules/security")
sys.path.append("pytavia_modules/user")
sys.path.append("pytavia_modules/view")



##########################################################
from pytavia_core       import database
from pytavia_core       import config

from pytavia_stdlib     import utils
from pytavia_stdlib     import cfs_lib
from pytavia_stdlib     import idgen
from pytavia_stdlib     import sanitize
from pytavia_stdlib     import security_lib


##########################################################
from configuration      import config_all
from configuration      import config_setting_security_timeout


from cookie             import cookie_engine
from middleware         import browser_security
from security           import security_login
from user               import user_proc
from auth               import auth_proc
from admin              import admin_proc
from karyawan           import karyawan_proc
from landing            import landing_proc

from ecard              import ecard_proc

from view               import view_welcome
from view               import view_admin
from view               import view_landing
from view               import view_login
from view               import view_user

##########################################################
# LANDINGPAGE
##########################################################
from flask              import request
from flask              import render_template
from flask              import Flask
from flask              import session
from flask              import make_response
from flask              import redirect
from flask              import url_for
from flask              import flash, get_flashed_messages
from flask              import abort
from flask              import jsonify
from flask              import send_from_directory

from authlib.integrations.flask_client import OAuth
import os

from wtforms            import ValidationError

from flask_wtf.csrf     import CSRFProtect
from flask_wtf.csrf     import CSRFError

#
# Main app configurations
#
app                   = Flask( __name__, config.G_STATIC_URL_PATH )
app.secret_key        = config.G_FLASK_SECRET
app.session_interface = cookie_engine.MongoSessionInterface()
csrf                  = CSRFProtect(app)

app.config['WTF_CSRF_TIME_LIMIT'] = 86400

app.config['WTF_CSRF_TIME_LIMIT'] = 86400  # in seconds

#
# OAuth Initialization (Placeholders for credentials)
#
oauth = OAuth(app)

oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID', 'placeholder_google_id'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET', 'placeholder_google_secret'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

oauth.register(
    name='linkedin',
    client_id=os.getenv('LINKEDIN_CLIENT_ID', 'placeholder_linkedin_id'),
    client_secret=os.getenv('LINKEDIN_CLIENT_SECRET', 'placeholder_linkedin_secret'),
    access_token_url='https://www.linkedin.com/oauth/v2/accessToken',
    authorize_url='https://www.linkedin.com/oauth/v2/authorization',
    api_base_url='https://api.linkedin.com/v2/',
    client_kwargs={'scope': 'r_liteprofile r_emailaddress'}
)

oauth.register(
    name='facebook',
    client_id=os.getenv('FACEBOOK_CLIENT_ID', 'placeholder_facebook_id'),
    client_secret=os.getenv('FACEBOOK_CLIENT_SECRET', 'placeholder_facebook_secret'),
    access_token_url='https://graph.facebook.com/v11.0/oauth/access_token',
    authorize_url='https://www.facebook.com/v11.0/dialog/oauth',
    api_base_url='https://graph.facebook.com/v11.0/',
    client_kwargs={'scope': 'email public_profile'}
)


#
# Utility Function
#
# @app.errorhandler(CSRFError)
# def handle_csrf_error(e):
#     return redirect(url_for("login_html"))
# # end def


# @app.route("/")
# def landingpage():
#     fk_user_id  = session.get("fk_user_id")
#     params = request.form.to_dict()
#     # end if

#     html   = view_landing_page.view_landing_page().html( params )
#     return html

@app.route("/")
def index():
    return view_landing.view_landing().html()

@app.route("/admin")
def admin_redirect():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return redirect(url_for("admin_users"))

@app.route("/admin/requests")
def admin_dashboard():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).requests_html()

@app.route("/admin/users")
def admin_users():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).users_html()

@app.route("/admin/karyawan")
def admin_karyawan():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).karyawan_html()

@app.route("/landing/submit", methods=["POST"])
def landing_submit():
    params = request.form.to_dict()
    response = landing_proc.landing_proc(app).submit_request(params)
    if response["message_action"] == "SUBMIT_SUCCESS":
        return view_landing.view_landing().html(msg="Your request has been submitted successfully.")
    else:
        return view_landing.view_landing().html(error_msg=response["message_desc"])

@app.route("/admin/request/update", methods=["POST"])
def admin_request_update():
    params = request.form.to_dict()
    response = admin_proc.admin_proc(app).update_request_status(params)
    if response["message_action"] == "UPDATE_SUCCESS":
        return redirect(url_for("admin_dashboard"))
    else:
        return view_admin.view_admin(app).html(error_msg=response["message_desc"])

@app.route("/admin/request/delete", methods=["POST"])
def admin_request_delete():
    params = request.form.to_dict()
    response = admin_proc.admin_proc(app).delete_request(params)
    if response["message_action"] == "DELETE_SUCCESS":
        return redirect(url_for("admin_dashboard"))
    else:
        return view_admin.view_admin(app).html(error_msg=response["message_desc"])

@app.route("/admin/user/add", methods=["POST"])
def admin_user_add():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    params = request.form.to_dict()
    response = admin_proc.admin_proc(app).add_user(params)
    if response["message_action"] == "ADD_USER_SUCCESS":
        return redirect(url_for("admin_users"))
    else:
        return view_admin.view_admin(app).users_html(error_msg=response["message_desc"])

@app.route("/admin/karyawan/add", methods=["GET"])
def admin_karyawan_add_view():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).karyawan_add_html()

@app.route("/admin/karyawan/add", methods=["POST"])
def admin_karyawan_add():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    params = request.form.to_dict()
    # Handle array inputs directly from request.form.getlist() and files from request.files
    phones_labels = request.form.getlist("phone_label[]")
    phones_numbers = request.form.getlist("phone_number[]")
    emails_labels = request.form.getlist("email_label[]")
    emails_values = request.form.getlist("email_value[]")
    websites_labels = request.form.getlist("website_label[]")
    websites_values = request.form.getlist("website_value[]")
    
    # Process into param dict
    params["phones"] = [{"label": label, "number": num} for label, num in zip(phones_labels, phones_numbers) if num.strip()]
    params["emails"] = [{"label": label, "value": val} for label, val in zip(emails_labels, emails_values) if val.strip()]
    params["websites"] = [{"label": label, "value": val} for label, val in zip(websites_labels, websites_values) if val.strip()]
    
    # Pass files explicitly
    response = karyawan_proc.karyawan_proc(app).add_karyawan(params, request.files)
    if response["message_action"] == "ADD_KARYAWAN_SUCCESS":
        return redirect(url_for("admin_karyawan"))
    else:
        return view_admin.view_admin(app).karyawan_add_html(error_msg=response["message_desc"])

@app.route("/admin/karyawan/edit/<karyawan_id>", methods=["GET"])
def admin_karyawan_edit_view(karyawan_id):
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).karyawan_edit_html(karyawan_id)

@app.route("/admin/karyawan/edit/<karyawan_id>", methods=["POST"])
def admin_karyawan_edit(karyawan_id):
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    params = request.form.to_dict()
    # Handle array inputs directly from request.form.getlist() and files from request.files
    phones_labels = request.form.getlist("phone_label[]")
    phones_numbers = request.form.getlist("phone_number[]")
    emails_labels = request.form.getlist("email_label[]")
    emails_values = request.form.getlist("email_value[]")
    websites_labels = request.form.getlist("website_label[]")
    websites_values = request.form.getlist("website_value[]")
    
    # Process into param dict
    params["phones"] = [{"label": label, "number": num} for label, num in zip(phones_labels, phones_numbers) if num.strip()]
    params["emails"] = [{"label": label, "value": val} for label, val in zip(emails_labels, emails_values) if val.strip()]
    params["websites"] = [{"label": label, "value": val} for label, val in zip(websites_labels, websites_values) if val.strip()]
    
    # Pass files explicitly
    response = karyawan_proc.karyawan_proc(app).edit_karyawan(karyawan_id, params, request.files)
    if response["message_action"] == "EDIT_KARYAWAN_SUCCESS":
        return redirect(url_for("admin_karyawan"))
    else:
        return view_admin.view_admin(app).karyawan_edit_html(karyawan_id, error_msg=response["message_desc"])

@app.route("/api/admin/karyawan/<karyawan_id>", methods=["GET"])
def api_karyawan_get(karyawan_id):
    if "fk_user_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    karyawan = karyawan_proc.karyawan_proc(app).get_karyawan_by_id(karyawan_id)
    if karyawan:
        # Convert ObjectId and other non-serializable fields to string if necessary, 
        # but since we use string uuid for karyawan_id, we just clean _id
        if "_id" in karyawan:
            del karyawan["_id"]
        return jsonify({"status": "success", "data": karyawan})
    return jsonify({"status": "error", "message": "Not found"}), 404

@app.route("/admin/ecard", methods=["GET"])
def admin_ecard():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).ecard_html()

@app.route("/admin/ecard/add", methods=["GET"])
def admin_ecard_add_view():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).ecard_add_html()

@app.route("/admin/ecard/add", methods=["POST"])
def admin_ecard_add():
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    params = request.form.to_dict()
    response = ecard_proc.ecard_proc(app).add_ecard(params, request.files)
    if response["message_action"] == "ADD_ECARD_SUCCESS":
        return redirect(url_for("admin_ecard"))
    else:
        return view_admin.view_admin(app).ecard_add_html(error_msg=response["message_desc"])

@app.route("/admin/ecard/edit/<ecard_id>", methods=["GET"])
def admin_ecard_edit_view(ecard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).ecard_edit_html(ecard_id)

@app.route("/admin/ecard/edit/<ecard_id>", methods=["POST"])
def admin_ecard_edit(ecard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    params = request.form.to_dict()
    response = ecard_proc.ecard_proc(app).edit_ecard(ecard_id, params, request.files)
    if response["message_action"] == "EDIT_ECARD_SUCCESS":
        return redirect(url_for("admin_ecard"))
    else:
        return view_admin.view_admin(app).ecard_edit_html(ecard_id, error_msg=response["message_desc"])

@app.route("/admin/ecard/delete/<ecard_id>", methods=["POST"])
def admin_ecard_delete(ecard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("admin_login_view"))
    response = ecard_proc.ecard_proc(app).delete_ecard(ecard_id)
    return redirect(url_for("admin_ecard"))

@app.route("/login", methods=["GET"])
def login_view():
    return view_login.view_login().html()

@app.route("/admin/login", methods=["GET"])
def admin_login_view():
    return view_login.view_login().admin_html()

@app.route("/auth/login", methods=["POST"])
def auth_login():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).login(params)
    if response["message_action"] == "LOGIN_SUCCESS":
        session["fk_user_id"] = response["message_data"]["fk_user_id"]
        session["username"]   = response["message_data"]["username"]
        return redirect(url_for("user_dashboard"))
    else:
        return view_login.view_login().html(error_msg=response["message_desc"])

@app.route("/auth/admin_login", methods=["POST"])
def auth_admin_login():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).admin_login(params)
    if response["message_action"] == "LOGIN_SUCCESS":
        session["fk_user_id"] = response["message_data"]["fk_user_id"]
        session["username"]   = response["message_data"]["username"]
        return redirect(url_for("admin_redirect"))
    else:
        return view_login.view_login().admin_html(error_msg=response["message_desc"])

@app.route("/auth/logout")
def auth_logout():
    session.clear()
    return redirect(url_for("login_view"))

@app.route("/user/dashboard")
def user_dashboard():
    # Redirect base dashboard load to "New QR" view as default
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return redirect(url_for("user_new_qr"))

@app.route("/p/<short_code>")
def qr_redirect(short_code):
    """Public endpoint: /p/<short_code>.

    - For web type: redirect to current url_content.
    - For pdf type: render a public landing page using stored PDF settings/files.
    """
    from pytavia_modules.qr import qr_proc
    proc = qr_proc.qr_proc(app)
    qrcard = proc.get_qrcard_by_short_code(short_code)
    if not qrcard:
        abort(404)
    # Enforce optional scan limit before serving content
    stats = (qrcard.get("stats") or {})
    current_scans = int(stats.get("scan_count", 0) or 0)
    limit_enabled = bool(qrcard.get("scan_limit_enabled"))
    limit_value = int(qrcard.get("scan_limit_value", 0) or 0)
    if limit_enabled and limit_value > 0 and current_scans >= limit_value:
        # When limit reached, behave as if content no longer exists
        abort(404)

    # Increment scan counter (only for successful hits)
    try:
        proc.increment_scan_count(qrcard.get("fk_user_id"), qrcard.get("qrcard_id"))
    except Exception:
        pass
    qr_type = qrcard.get("qr_type") or "web"
    if qr_type == "pdf":
        return render_template("/user/public_pdf.html", qrcard=qrcard)
    # default: web-like behavior
    dest = (qrcard.get("url_content") or "").strip()
    if not dest:
        abort(404)
    if not dest.startswith("http://") and not dest.startswith("https://"):
        dest = "https://" + dest
    return redirect(dest, code=302)

@app.route("/qr/new")
def user_new_qr():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).new_qr_html()

@app.route("/qr/delete/<qrcard_id>", methods=["POST"])
def qr_delete(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_proc
    qr_proc.qr_proc(app).delete_qrcard(session.get("fk_user_id"), qrcard_id)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/delete/bulk", methods=["POST"])
def qr_delete_bulk():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    qrcard_ids = request.form.getlist("qrcard_ids")
    if not qrcard_ids:
        return redirect(url_for("user_qr_list"))
    from pytavia_modules.qr import qr_proc
    proc = qr_proc.qr_proc(app)
    for qrcard_id in qrcard_ids:
        proc.delete_qrcard(session.get("fk_user_id"), qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/edit/<qrcard_id>", methods=["GET", "POST"])
def qr_edit(qrcard_id):
    """Legacy single-page edit; redirect to step-based update flow."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return redirect(url_for("qr_update_content", qr_type="web", qrcard_id=qrcard_id))

@app.route("/qr/update/<qrcard_id>")
def qr_update_start(qrcard_id):
    """First step: redirect to type-specific content step (e.g. /qr/update/web/<id>)."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_proc
    qrcard = qr_proc.qr_proc(app).get_qrcard(session.get("fk_user_id"), qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qr_type = qrcard.get("qr_type") or "web"
    return redirect(url_for("qr_update_content", qr_type=qr_type, qrcard_id=qrcard_id))

def _get_qr_draft(session, qrcard_id):
    return (session.get("qr_draft") or {}).get(qrcard_id)

def _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code=None, extra_data=None):
    if "qr_draft" not in session:
        session["qr_draft"] = {}
    # Merge into existing draft so values set in earlier steps (e.g. content step)
    # are not lost when the design step calls this with only its own fields.
    existing = dict(session["qr_draft"].get(qrcard_id) or {})
    existing.update({
        "url_content": url_content,
        "qr_name": qr_name,
        "short_code": short_code or "",
    })
    if extra_data:
        existing.update(extra_data)
    session["qr_draft"][qrcard_id] = existing
    session.modified = True

def _clear_qr_draft(session, qrcard_id):
    if session.get("qr_draft") and qrcard_id in session["qr_draft"]:
        del session["qr_draft"][qrcard_id]
        session.modified = True

@app.route("/qr/update/<qr_type>/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content(qr_type, qrcard_id):
    """Step 1 (content): same as /qr/new/<qr_type> but for existing card. POST -> design step; POST with back_from_design -> re-render content with current values. GET uses session draft if set."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_proc
    qrcard = qr_proc.qr_proc(app).get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        short_code = request.form.get("short_code", "").strip()
        
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color",
                      "pdf_title_font", "pdf_title_color", "pdf_text_font",
                      "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                      "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                      "scan_limit_enabled", "scan_limit_value", "pdf_font_apply_all"]
        pdf_data = {f: request.form.get(f, "") for f in pdf_fields if f in request.form}

        # Delete existing welcome image if requested
        if request.form.get("welcome_img_delete") == "1":
            from pytavia_modules.qr import qr_proc as _qrp_del
            # Clear in-memory and DB URL; we keep file cleanup best-effort and non-fatal
            qrcard["welcome_img_url"] = ""
            pdf_data["welcome_img_url"] = ""
            try:
                _qrp_del.qr_proc(app).mgdDB.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": ""}}
                )
            except Exception:
                app.logger.exception("Failed to clear welcome_img_url for qrcard %s", qrcard_id)
        else:
            # Save welcome screen image when uploaded (update flow: content step has the file), max 1 MB
            welcome_img = request.files.get("pdf_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                welcome_size = welcome_img.tell()
                welcome_img.seek(0)
                if welcome_size > 1024 * 1024:
                    return view_user.view_user(app).update_qr_content_html(
                        qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name,
                        short_code=short_code or None,
                        error_msg="Welcome image must be 1 MB or smaller.",
                        base_url=config.G_BASE_URL
                    )
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
                os.makedirs(upload_dir, exist_ok=True)
                welcome_name = "welcome" + ext
                welcome_path = os.path.join(upload_dir, welcome_name)
                welcome_img.save(welcome_path)
                welcome_url = f"/static/uploads/pdf/{qrcard_id}/{welcome_name}"
                pdf_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                proc = qr_proc.qr_proc(app)
                proc.mgdDB.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}}
                )
            elif qrcard.get("welcome_img_url"):
                pdf_data["welcome_img_url"] = qrcard["welcome_img_url"]

        # One unified cover image shared by all templates:
        #   T1 → displayed as full-width header
        #   T3/T4 → displayed as circle at top
        # All three DB fields always stay in sync.
        _cover_img_fields = ["pdf_t1_header_img_url", "pdf_t3_circle_img_url", "pdf_t4_circle_img_url"]
        cover_img = request.files.get("pdf_t1_header_img")
        cover_delete = request.form.get("pdf_t1_header_img_delete") == "1"
        if cover_delete:
            for _f in _cover_img_fields:
                pdf_data[_f] = ""
                qrcard[_f] = ""
            proc = qr_proc.qr_proc(app)
            proc.mgdDB.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {_f: "" for _f in _cover_img_fields}}
            )
        elif cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            cover_size = cover_img.tell()
            cover_img.seek(0)
            if cover_size <= 2 * 1024 * 1024:
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, "pdf_cover_img" + ext)
                cover_img.save(save_path)
                cover_url = f"/static/uploads/pdf/{qrcard_id}/pdf_cover_img{ext}"
                for _f in _cover_img_fields:
                    pdf_data[_f] = cover_url
                    qrcard[_f] = cover_url
                proc = qr_proc.qr_proc(app)
                proc.mgdDB.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {_f: cover_url for _f in _cover_img_fields}}
                )
        else:
            # No new upload – carry forward whichever field already has a URL
            existing_cover = (qrcard.get("pdf_t1_header_img_url") or
                              qrcard.get("pdf_t3_circle_img_url") or
                              qrcard.get("pdf_t4_circle_img_url") or "")
            for _f in _cover_img_fields:
                pdf_data[_f] = existing_cover
                qrcard[_f] = existing_cover

        # Save per-PDF metadata to draft so qr_update_save can access them
        pdf_data["pdf_display_names"] = request.form.getlist("pdf_display_names")
        pdf_data["pdf_item_descs"]    = request.form.getlist("pdf_item_descs")
        pdf_data["pdf_existing_urls"] = request.form.getlist("existing_pdf_urls")

        # Back from design: re-render content step with current values; update draft
        if request.form.get("back_from_design"):
            _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, pdf_data)
            qrcard.update(pdf_data)
            return view_user.view_user(app).update_qr_content_html(
                qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name,
                short_code=short_code or None,
                base_url=config.G_BASE_URL
            )
        if not qr_proc.qr_proc(app).is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_user.view_user(app).update_qr_content_html(
                qr_type=qr_type, qrcard=qrcard,
                error_msg="A QR card with this name already exists. Please choose a unique name.",
                base_url=config.G_BASE_URL
            )
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), pdf_data)
        qrcard.update(pdf_data)

        # For PDF type: immediately persist any newly uploaded PDF files so they are not lost between steps
        if qr_type == "pdf":
            from pytavia_modules.qr import qr_proc as _qr_proc_for_update
            pdf_file_list = request.files.getlist("pdf_files")
            if pdf_file_list and any(f.filename for f in pdf_file_list):
                pdf_upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
                os.makedirs(pdf_upload_dir, exist_ok=True)
                qrcard_db = _qr_proc_for_update.qr_proc(app).get_qrcard(fk_user_id, qrcard_id)
                existing_files = qrcard_db.get("pdf_files", []) if qrcard_db else []
                for f in pdf_file_list:
                    if f and f.filename and f.filename.lower().endswith(".pdf"):
                        safe_name = f.filename.replace(" ", "_")
                        filepath = os.path.join(pdf_upload_dir, safe_name)
                        if not os.path.exists(filepath):
                            f.save(filepath)
                        file_entry = {"name": f.filename, "url": f"/static/uploads/pdf/{qrcard_id}/{safe_name}"}
                        if not any(x.get("name") == f.filename for x in existing_files):
                            existing_files.append(file_entry)
                _qr_proc_for_update.qr_proc(app).update_pdf_files(fk_user_id, qrcard_id, existing_files)

        return view_user.view_user(app).update_qr_design_html(
            qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name
        )
    # GET: use session draft if available so Step 2 tab / Back preserves edits
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qrcard.update(draft)
        return view_user.view_user(app).update_qr_content_html(
            qr_type=qr_type, qrcard=qrcard,
            url_content=draft.get("url_content"), qr_name=draft.get("qr_name"),
            short_code=draft.get("short_code") or None,
            base_url=config.G_BASE_URL
        )
    return view_user.view_user(app).update_qr_content_html(
        qr_type=qr_type, qrcard=qrcard, base_url=config.G_BASE_URL
    )

@app.route("/qr/update/<qr_type>/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design(qr_type, qrcard_id):
    """Step 2 (design): same as /qr/new/<qr_type>/qr-design but for existing card. GET or POST from content -> show design; save is POST to /qr/update/save/<id>."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_proc
    qrcard = qr_proc.qr_proc(app).get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "qrcardku.com"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color",
                      "pdf_title_font", "pdf_title_color", "pdf_text_font",
                      "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                      "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                      "scan_limit_enabled", "scan_limit_value", "pdf_font_apply_all"]
        pdf_data = {f: request.form.get(f, "") for f in pdf_fields if f in request.form}
        if qrcard.get("welcome_img_url"):
            pdf_data["welcome_img_url"] = qrcard["welcome_img_url"]
        if qrcard.get("welcome_bg_color"):
            pdf_data["welcome_bg_color"] = qrcard["welcome_bg_color"]
        
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), pdf_data)
        qrcard.update(pdf_data)
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft:
            qrcard.update(draft)
            url_content = draft.get("url_content") or qrcard.get("url_content") or "qrcardku.com"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "qrcardku.com"
            qr_name = qrcard.get("name") or "Untitled QR"
    qr_encode_url = None
    if qr_type == "web" and qrcard.get("short_code"):
        qr_encode_url = config.G_BASE_URL + "/p/" + qrcard["short_code"]
    return view_user.view_user(app).update_qr_design_html(
        qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name,
        qr_encode_url=qr_encode_url
    )

@app.route("/qr/update/save/<qrcard_id>", methods=["POST"])
def qr_update_save(qrcard_id):
    """Save update from design step (Complete button)."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    url_content = (request.form.get("url_content") or "").strip()
    qr_name = (request.form.get("qr_name") or "").strip()
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    from pytavia_modules.qr import qr_proc
    
    # Use session draft as fallback for any missing PDF values in the form
    draft = _get_qr_draft(session, qrcard_id) or {}
    
    def _get_field(field, default=""):
        """Get from form first, then session draft, then default."""
        val = request.form.get(field, "").strip()
        if not val:
            val = draft.get(field, default)
        return val
    
    # Preserve image URLs from draft or existing qrcard (files are uploaded on content step only).
    # All three cover-image fields always hold the same URL (unified cover image).
    qrcard_for_save = qr_proc.qr_proc(app).get_qrcard(fk_user_id, qrcard_id)
    welcome_url = draft.get("welcome_img_url") or (qrcard_for_save.get("welcome_img_url") if qrcard_for_save else "") or ""
    cover_url = (
        draft.get("pdf_t1_header_img_url") or
        draft.get("pdf_t3_circle_img_url") or
        draft.get("pdf_t4_circle_img_url") or
        (qrcard_for_save.get("pdf_t1_header_img_url") if qrcard_for_save else "") or
        (qrcard_for_save.get("pdf_t3_circle_img_url") if qrcard_for_save else "") or
        (qrcard_for_save.get("pdf_t4_circle_img_url") if qrcard_for_save else "") or ""
    )
    t1_header_url = cover_url
    t3_circle_url = cover_url
    t4_circle_url = cover_url

    params = {
        "fk_user_id": fk_user_id,
        "qrcard_id": qrcard_id,
        "name": qr_name or draft.get("qr_name") or "Untitled QR",
        "url_content": url_content or draft.get("url_content") or "",
        "welcome_img_url": welcome_url,
        "pdf_t1_header_img_url": t1_header_url,
        "pdf_t3_circle_img_url": t3_circle_url,
        "pdf_t4_circle_img_url": t4_circle_url,
        "pdf_template": _get_field("pdf_template", "default"),
        "pdf_primary_color": _get_field("pdf_primary_color", "#2F6BFD"),
        "pdf_secondary_color": _get_field("pdf_secondary_color", "#0E379A"),
        "pdf_title_font": _get_field("pdf_title_font", "Lato"),
        "pdf_title_color": _get_field("pdf_title_color", "#000000"),
        "pdf_text_font": _get_field("pdf_text_font", "Lato"),
        "pdf_text_color": _get_field("pdf_text_color", "#000000"),
        "pdf_company": _get_field("pdf_company"),
        "pdf_title": _get_field("pdf_title"),
        "pdf_desc": _get_field("pdf_desc"),
        "pdf_website": _get_field("pdf_website"),
        "pdf_btn_text": _get_field("pdf_btn_text", "See PDF"),
        "welcome_time": _get_field("welcome_time", "5.0"),
        "welcome_bg_color": _get_field("welcome_bg_color", "#2F6BFD"),
        "pdf_font_apply_all": _get_field("pdf_font_apply_all", ""),
    }

    # Scan limit fields (from form or draft)
    enabled_raw = request.form.get("scan_limit_enabled")
    params["scan_limit_enabled"] = bool(enabled_raw or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip()
    if not raw_limit and "scan_limit_value" in draft:
        raw_limit = str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else int(draft.get("scan_limit_value", 0) or 0)

    # Optional custom short_code updates for dynamic types (web/pdf)
    short_code_form = (request.form.get("short_code") or "").strip().lower()
    short_code_draft = (draft.get("short_code") or "").strip().lower()
    if short_code_form or short_code_draft:
        params["short_code"] = short_code_form or short_code_draft

    qr_proc.qr_proc(app).edit_qrcard(params)
    
    # Save any newly uploaded PDF files and append to existing (still-kept) list
    if True:  # always run to handle new uploads even for non-pdf edits gracefully
        from pytavia_modules.qr import qr_proc as _qr_proc_for_files
        pdf_file_list = request.files.getlist("pdf_files")
        # Start from existing files that are still present in the form (not removed).
        # Fall back to the session draft because these fields are submitted on the content
        # step (not the design step) and the design form doesn't carry them forward.
        existing_urls = request.form.getlist("existing_pdf_urls") or draft.get("pdf_existing_urls", [])
        display_names = request.form.getlist("pdf_display_names") or draft.get("pdf_display_names", [])
        item_descs    = request.form.getlist("pdf_item_descs")    or draft.get("pdf_item_descs", [])
        qrcard_db = _qr_proc_for_files.qr_proc(app).get_qrcard(fk_user_id, qrcard_id)
        db_files = qrcard_db.get("pdf_files", []) if qrcard_db else []
        if existing_urls:
            db_map = {f.get("url"): f for f in db_files}
            existing_files = []
            for i, url in enumerate(existing_urls):
                entry = dict(db_map.get(url, {"name": url.split("/")[-1], "url": url}))
                if i < len(display_names) and display_names[i].strip():
                    entry["display_name"] = display_names[i].strip()
                if i < len(item_descs):
                    entry["item_desc"] = item_descs[i].strip()
                existing_files.append(entry)
        else:
            existing_files = []
        if pdf_file_list and any(f.filename for f in pdf_file_list):
            pdf_upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
            os.makedirs(pdf_upload_dir, exist_ok=True)
            for f in pdf_file_list:
                if f and f.filename and f.filename.lower().endswith(".pdf"):
                    safe_name = f.filename.replace(" ", "_")
                    filepath = os.path.join(pdf_upload_dir, safe_name)
                    f.save(filepath)
                    file_entry = {"name": f.filename, "url": f"/static/uploads/pdf/{qrcard_id}/{safe_name}"}
                    # Avoid duplicates by name
                    if not any(x.get("name") == f.filename for x in existing_files):
                        existing_files.append(file_entry)
        if existing_files:
            _qr_proc_for_files.qr_proc(app).update_pdf_files(fk_user_id, qrcard_id, existing_files)
    
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/new/<qr_type>")
def user_new_qr_type(qr_type):
    from flask import request as _req
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    base_url = config.G_BASE_URL
    return view_user.view_user(app).new_qr_type_html(qr_type, base_url=base_url)

@app.route("/qr/new/<qr_type>/qr-design", methods=["GET", "POST"])
def user_new_qr_design(qr_type):
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
        
    url_content = "qrcardku.com"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    from pytavia_modules.qr import qr_proc
    qr_proc_inst = qr_proc.qr_proc(app)
    
    if request.method == "POST":
        url_content = request.form.get("url_content", "qrcardku.com")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color",
                      "pdf_title_font", "pdf_title_color", "pdf_text_font",
                      "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc",
                      "pdf_website", "pdf_btn_text", "welcome_time", "welcome_bg_color",
                      "pdf_font_apply_all"]
        pdf_data = {f: request.form.get(f, "") for f in pdf_fields}
        
        # Save uploaded PDFs to a temp folder keyed by session
        if qr_type == "pdf":
            import os, uuid as _uuid
            tmp_key = session.get("pdf_tmp_key") or _uuid.uuid4().hex
            session["pdf_tmp_key"] = tmp_key
            tmp_dir = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", tmp_key)
            os.makedirs(tmp_dir, exist_ok=True)
            pdf_file_list = request.files.getlist("pdf_files")
            existing_tmp = session.get("pdf_tmp_files", [])
            existing_names = {x["name"] for x in existing_tmp}
            for f in pdf_file_list:
                if f and f.filename and f.filename.lower().endswith(".pdf"):
                    safe_name = f.filename.replace(" ", "_")
                    if f.filename not in existing_names:
                        f.save(os.path.join(tmp_dir, safe_name))
                        existing_tmp.append({"name": f.filename, "safe_name": safe_name})
                        existing_names.add(f.filename)
            session["pdf_tmp_files"] = existing_tmp
            session.modified = True
            # Save welcome screen image to same temp folder for move on final save, max 1 MB
            welcome_img = request.files.get("pdf_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                welcome_size = welcome_img.tell()
                welcome_img.seek(0)
                if welcome_size <= 1024 * 1024:
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    welcome_name = "welcome" + ext
                    welcome_img.save(os.path.join(tmp_dir, welcome_name))
                    session["welcome_img_tmp_key"] = tmp_key
                    session["welcome_img_tmp_name"] = welcome_name
                    session.modified = True
                else:
                    error_msg = "Welcome image must be 1 MB or smaller."
        
        if not qr_proc_inst.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return view_user.view_user(app).new_qr_type_html(qr_type, error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        
        if qr_type == "web":
            if short_code:
                import re
                if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                    error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                    return view_user.view_user(app).new_qr_type_html(qr_type, error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
                if not qr_proc_inst.is_short_code_unique(short_code):
                    error_msg = "This address identifier is already in use. Please choose another."
                    return view_user.view_user(app).new_qr_type_html(qr_type, error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            else:
                short_code = qr_proc_inst._generate_short_code()
                while not qr_proc_inst.is_short_code_unique(short_code):
                    short_code = qr_proc_inst._generate_short_code()
            base = config.G_BASE_URL
            qr_encode_url = base + "/p/" + short_code
        elif qr_type == "pdf":
            # Auto-generate a unique short_code for PDF type
            short_code = qr_proc_inst._generate_short_code()
            while not qr_proc_inst.is_short_code_unique(short_code):
                short_code = qr_proc_inst._generate_short_code()
            base = config.G_BASE_URL
            qr_encode_url = base + "/p/" + short_code
    else:
        pdf_data = {}
    
    return view_user.view_user(app).new_qr_design_html(
        qr_type, url_content=url_content, qr_name=qr_name,
        short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg,
        pdf_data=pdf_data
    )

@app.route("/qr/save", methods=["POST"])
def qr_save():
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
        
    qr_type = request.form.get("qr_type", "web")
    params = {
        "fk_user_id": session.get("fk_user_id"),
        "qr_type": qr_type,
        "name": request.form.get("qr_name", "Untitled QR"),
        "url_content": request.form.get("url_content", ""),
        "pdf_template": request.form.get("pdf_template", "default"),
        "pdf_primary_color": request.form.get("pdf_primary_color", "#2F6BFD"),
        "pdf_secondary_color": request.form.get("pdf_secondary_color", "#0E379A"),
        "pdf_title_font": request.form.get("pdf_title_font", "Lato"),
        "pdf_title_color": request.form.get("pdf_title_color", "#000000"),
        "pdf_text_font": request.form.get("pdf_text_font", "Lato"),
        "pdf_text_color": request.form.get("pdf_text_color", "#000000"),
        "pdf_company": request.form.get("pdf_company", ""),
        "pdf_title": request.form.get("pdf_title", ""),
        "pdf_desc": request.form.get("pdf_desc", ""),
        "pdf_website": request.form.get("pdf_website", ""),
        "pdf_btn_text": request.form.get("pdf_btn_text", "See PDF"),
        "welcome_time": request.form.get("welcome_time", "5.0"),
        "welcome_bg_color": request.form.get("welcome_bg_color", "#2F6BFD"),
        "pdf_font_apply_all": request.form.get("pdf_font_apply_all", "")
    }
    # Scan limit fields from content step
    enabled_raw = request.form.get("scan_limit_enabled")
    params["scan_limit_enabled"] = bool(enabled_raw)
    raw_limit = (request.form.get("scan_limit_value") or "").strip()
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    if qr_type in ("web", "pdf"):
        params["short_code"] = (request.form.get("short_code") or "").strip().lower()
    
    print(f"[qr_save DEBUG] company={params.get('pdf_company')!r} primary={params.get('pdf_primary_color')!r} template={params.get('pdf_template')!r}")
    
    from pytavia_modules.qr import qr_proc
    result = qr_proc.qr_proc(app).add_qrcard(params)
    if result.get("message_action") == "ADD_QRCARD_FAILED":
        sc = params.get("short_code") or ""
        return view_user.view_user(app).new_qr_design_html(
            qr_type,
            url_content=request.form.get("url_content", ""),
            qr_name=request.form.get("qr_name", ""),
            short_code=sc,
            qr_encode_url=(config.G_BASE_URL + "/p/" + sc) if sc else None,
            error_msg=result.get("message_desc", "Save failed.")
        )
    
    # Move uploaded PDF files from temp session folder to final qrcard folder
    if qr_type == "pdf" and result.get("message_action") == "ADD_QRCARD_SUCCESS":
        import os, shutil
        new_qrcard_id = result["message_data"]["qrcard_id"]
        tmp_key = session.pop("pdf_tmp_key", None)
        tmp_files = session.pop("pdf_tmp_files", [])
        welcome_tmp_key = session.pop("welcome_img_tmp_key", None)
        welcome_tmp_name = session.pop("welcome_img_tmp_name", "welcome.jpg")
        session.modified = True
        dest_dir = os.path.join(app.root_path, "static", "uploads", "pdf", new_qrcard_id)
        tmp_dir = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", tmp_key) if tmp_key else None
        if welcome_tmp_key:
            tmp_dir_w = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", welcome_tmp_key)
            src_welcome = os.path.join(tmp_dir_w, welcome_tmp_name)
            ext = os.path.splitext(welcome_tmp_name)[1] or ".jpg"
            if os.path.exists(src_welcome):
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src_welcome, os.path.join(dest_dir, "welcome" + ext))
                welcome_url = f"/static/uploads/pdf/{new_qrcard_id}/welcome{ext}"
                from pytavia_modules.qr import qr_proc as _qrproc
                _qrproc.qr_proc(app).mgdDB.db_qrcard.update_one(
                    {"qrcard_id": new_qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}}
                )
        saved_files = []
        if tmp_key and tmp_files:
            if not tmp_dir:
                tmp_dir = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", tmp_key)
            os.makedirs(dest_dir, exist_ok=True)
            for f_info in tmp_files:
                src = os.path.join(tmp_dir, f_info["safe_name"])
                dst = os.path.join(dest_dir, f_info["safe_name"])
                if os.path.exists(src):
                    shutil.move(src, dst)
                    saved_files.append({
                        "name": f_info["name"],
                        "url": f"/static/uploads/pdf/{new_qrcard_id}/{f_info['safe_name']}"
                    })
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        elif tmp_key:
            tmp_dir = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", tmp_key)
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        if welcome_tmp_key and (not tmp_key or welcome_tmp_key != tmp_key):
            try:
                shutil.rmtree(os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", welcome_tmp_key), ignore_errors=True)
            except Exception:
                pass
        if saved_files:
            from pytavia_modules.qr import qr_proc as _qrproc
            _qrproc.qr_proc(app).update_pdf_files(session.get("fk_user_id"), new_qrcard_id, saved_files)
    
    return redirect(url_for("user_qr_list"))

@app.route("/api/qr/remove_pdf_file", methods=["POST"])
def api_remove_pdf_file():
    """Remove a single saved PDF file from a QR card's pdf_files list."""
    from flask import request, jsonify
    if "fk_user_id" not in session:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    fk_user_id = session.get("fk_user_id")
    data = request.get_json()
    qrcard_id = data.get("qrcard_id", "")
    file_url = data.get("url", "")
    if not qrcard_id or not file_url:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    from pytavia_modules.qr import qr_proc
    ok = qr_proc.qr_proc(app).remove_pdf_file(fk_user_id, qrcard_id, file_url)
    # Also delete the file from disk
    if ok:
        import os
        disk_path = os.path.join(app.root_path, file_url.lstrip("/").replace("/", os.sep))
        try:
            if os.path.exists(disk_path):
                os.remove(disk_path)
        except Exception:
            pass
    return jsonify({"success": ok})

@app.route("/qr/list")
def user_qr_list():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_proc
    qr_list = qr_proc.qr_proc(app).get_qrcard_by_user(session.get("fk_user_id"))
    return view_user.view_user(app).my_qr_codes_html(qr_list=qr_list)

@app.route("/user/stats")
def user_stats():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).stats_html()

@app.route("/user/templates")
def user_templates():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).templates_html()

@app.route("/user/settings")
def user_settings():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).settings_html()

@app.route("/user/users")
def user_users():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).users_html()

@app.route("/user/security-history")
def user_security_history():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).security_history_html()

@app.route("/register", methods=["GET"])
def register_view():
    return view_login.view_login().register_html()

@app.route("/auth/register", methods=["POST"])
def auth_register():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).register(params)
    if response["message_action"] == "REGISTER_SUCCESS":
        # Usually redirect to login page with a success flash message or auto-login
        return redirect(url_for("login_view"))
    else:
        return view_login.view_login().register_html(error_msg=response["message_desc"])

@app.route('/auth/login/<provider>')
def social_login(provider):
    client = oauth.create_client(provider)
    if not client:
        abort(404)
    redirect_uri = url_for('social_authorize', provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)

@app.route('/auth/callback/<provider>')
def social_authorize(provider):
    client = oauth.create_client(provider)
    if not client:
        abort(404)
    
    try:
        token = client.authorize_access_token()
        if provider == 'google':
            user_info = client.parse_id_token(token)
        elif provider == 'linkedin':
            resp = client.get('me?projection=(id,localizedFirstName,localizedLastName)')
            user_info = resp.json()
            email_resp = client.get('emailAddress?q=members&projection=(elements*(handle~))')
            email_info = email_resp.json()
            user_info['email'] = email_info['elements'][0]['handle~']['emailAddress'] if email_info.get('elements') else ''
        elif provider == 'facebook':
            resp = client.get('me?fields=id,name,email')
            user_info = resp.json()
        else:
            user_info = {}
            
        # Process the social login logic here via auth_proc
        response = auth_proc.auth_proc(app).social_login(provider, user_info)
        
        if response.get("message_action") == "LOGIN_SUCCESS":
            session["fk_user_id"] = response["message_data"]["fk_user_id"]
            session["username"]   = response["message_data"]["username"]
            return redirect(url_for("user_dashboard"))
        else:
            return view_login.view_login().html(error_msg=response.get("message_desc", "Social login failed."))
            
    except Exception as e:
        app.logger.error(f"OAuth callback error: {e}")
        return view_login.view_login().html(error_msg="Failed to authenticate with social provider.")
