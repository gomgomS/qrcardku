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
from pytavia_modules.view import view_update_pdf, view_update_web, view_update_ecard

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

@app.route("/web/<short_code>")
def qr_web_redirect(short_code):
    """Public endpoint for web-type short URLs. Lookup and logic in qr_public_web_visual_proc."""
    from pytavia_modules.qr.qr_public_web_visual_proc import qr_public_web_visual_proc
    return qr_public_web_visual_proc(app).handle(short_code)


@app.route("/ecard/<short_code>")
def qr_ecard_redirect(short_code):
    """Public endpoint for e-card short URLs. Lookup and logic in qr_public_ecard_visual_proc."""
    from pytavia_modules.qr.qr_public_ecard_visual_proc import qr_public_ecard_visual_proc
    return qr_public_ecard_visual_proc(app).handle(short_code)


@app.route("/pdf/<short_code>")
def qr_pdf_redirect(short_code):
    """Public endpoint for PDF short URLs."""
    from pytavia_modules.qr.qr_public_pdf_visual_proc import qr_public_pdf_visual_proc
    return qr_public_pdf_visual_proc(app).handle(short_code)

@app.route("/qr/new")
def user_new_qr():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).new_qr_html()

def _set_qrcard_deleted(mgdDB, fk_user_id, qrcard_id):
    """Mark one qrcard as DELETED in db_qrcard, db_qr_index, and db_qrcard_pdf (if present)."""
    q = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    mgdDB.db_qrcard.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qr_index.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qrcard_pdf.update_one(q, {"$set": {"status": "DELETED"}})


@app.route("/qr/delete/<qrcard_id>", methods=["POST"])
def qr_delete(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_del, config as _cfg_del
    _mgd_del = _db_del.get_db_conn(_cfg_del.mainDB)
    _set_qrcard_deleted(_mgd_del, session.get("fk_user_id"), qrcard_id)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/delete/bulk", methods=["POST"])
def qr_delete_bulk():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    qrcard_ids = request.form.getlist("qrcard_ids")
    if not qrcard_ids:
        return redirect(url_for("user_qr_list"))
    from pytavia_core import database as _db_bulk
    from pytavia_core import config as _cfg_bulk
    _mgd_bulk = _db_bulk.get_db_conn(_cfg_bulk.mainDB)
    fk_user_id = session.get("fk_user_id")
    for qrcard_id in qrcard_ids:
        _set_qrcard_deleted(_mgd_bulk, fk_user_id, qrcard_id)
    return redirect(url_for("user_qr_list"))
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

def _apply_pdf_draft_to_files(qrcard, draft_data):
    """Apply draft's pdf_existing_urls / pdf_display_names / pdf_item_descs into qrcard['pdf_files']."""
    existing_urls = draft_data.get("pdf_existing_urls")
    if not existing_urls:
        return
    display_names = draft_data.get("pdf_display_names", [])
    item_descs = draft_data.get("pdf_item_descs", [])
    db_files = list(qrcard.get("pdf_files") or [])
    db_map = {f.get("url"): dict(f) for f in db_files}
    rebuilt = []
    for i, url in enumerate(existing_urls):
        entry = dict(db_map.get(url, {"name": url.split("/")[-1], "url": url}))
        if i < len(display_names) and display_names[i].strip():
            entry["display_name"] = display_names[i].strip()
        if i < len(item_descs):
            entry["item_desc"] = item_descs[i].strip()
        rebuilt.append(entry)
    qrcard["pdf_files"] = rebuilt


# ─── Update: type-specific routes (pdf / web / ecard). No combined qr_type route. ───

@app.route("/qr/update/save/pdf/<qrcard_id>", methods=["POST"])
def qr_update_save_pdf(qrcard_id):
    """Save PDF update from design step (Complete). All logic in qr_pdf_proc.complete_pdf_update."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_pdf_proc
    proc = qr_pdf_proc.qr_pdf_proc(app)
    result = proc.complete_pdf_update(request, session, qrcard_id, app.root_path)
    if not result.get("success"):
        fk_user_id = session.get("fk_user_id")
        qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
        if qrcard:
            return view_update_pdf.view_update_pdf(app).update_qr_design_html(
                qrcard=qrcard, error_msg=result.get("error_msg", "Save failed.")
            )
        return redirect(url_for("user_qr_list"))
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/save/web/<qrcard_id>", methods=["POST"])
def qr_update_save_web(qrcard_id):
    """Save Web update from design step."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    draft = _get_qr_draft(session, qrcard_id) or {}
    url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
    short_code = (request.form.get("short_code") or "").strip().lower() or (draft.get("short_code") or "").strip().lower()
    from pytavia_modules.qr import qr_web_proc
    proc = qr_web_proc.qr_web_proc(app)
    params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "name": qr_name, "url_content": url_content}
    if short_code:
        params["short_code"] = short_code
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/save/ecard/<qrcard_id>", methods=["POST"])
def qr_update_save_ecard(qrcard_id):
    """Save E-card update from design step."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    draft = _get_qr_draft(session, qrcard_id) or {}
    url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
    short_code = (request.form.get("short_code") or "").strip().lower() or (draft.get("short_code") or "").strip().lower()
    from pytavia_modules.qr import qr_ecard_proc
    proc = qr_ecard_proc.qr_ecard_proc(app)
    params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "name": qr_name, "url_content": url_content}
    if short_code:
        params["short_code"] = short_code
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    
    for key in request.form:
        if key not in ["csrf_token", "url_content", "qr_name", "short_code", "scan_limit_enabled", "scan_limit_value"]:
            val_list = request.form.getlist(key)
            if len(val_list) > 1 or key.endswith("[]"):
                params[key] = val_list
            else:
                params[key] = val_list[0] if val_list else ""
                
    for key, val in draft.items():
        if key not in params and key not in ["url_content", "qr_name", "short_code"]:
            params[key] = val
            
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/pdf/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_pdf(qrcard_id):
    """Step 2 (design) for PDF. GET or POST from content -> design; save is POST to /qr/update/save/pdf/<id>."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_pdf_proc as _qrp
    qrcard = _qrp.qr_pdf_proc(app).get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "qrcardku.com"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color", "pdf_title_font", "pdf_title_color",
                      "pdf_text_font", "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc", "pdf_website",
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "scan_limit_enabled", "scan_limit_value", "pdf_font_apply_all"]
        ecard_data = {f: request.form.get(f, "") for f in pdf_fields if f in request.form}
        if qrcard.get("welcome_img_url"):
            ecard_data["welcome_img_url"] = qrcard["welcome_img_url"]
        if qrcard.get("welcome_bg_color"):
            ecard_data["welcome_bg_color"] = qrcard["welcome_bg_color"]
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), ecard_data)
        qrcard.update(ecard_data)
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
    if qrcard.get("short_code"):
        qr_encode_url = config.G_BASE_URL + "/pdf/" + qrcard["short_code"]
    return view_update_pdf.view_update_pdf(app).update_qr_design_html(
        qrcard=qrcard, url_content=url_content, qr_name=qr_name, qr_encode_url=qr_encode_url
    )


@app.route("/qr/update/web/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_web(qrcard_id):
    """Step 2 (design) for Web."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_core import database
    from pytavia_core import config as _cfg
    qrcard = database.get_db_conn(_cfg.mainDB).db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "qrcardku.com"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), None)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft:
            qrcard.update(draft)
            url_content = draft.get("url_content") or qrcard.get("url_content") or "qrcardku.com"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "qrcardku.com"
            qr_name = qrcard.get("name") or "Untitled QR"
    qr_encode_url = config.G_BASE_URL + "/web/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_web.view_update_web(app).update_qr_design_html(
        qrcard=qrcard, url_content=url_content, qr_name=qr_name, qr_encode_url=qr_encode_url
    )


@app.route("/qr/update/ecard/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_ecard(qrcard_id):
    """Step 2 (design) for E-card. Same pattern as PDF: proc.get_qrcard returns type-specific doc."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_ecard_proc as _qre
    proc = _qre.qr_ecard_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_ecard_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "qrcardku.com"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        extra_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    extra_data[key] = val_list
                else:
                    extra_data[key] = val_list[0] if val_list else ""
                    
        import os
        upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
        
        if request.form.get("E-card_welcome_img_delete") == "1":
            qrcard["welcome_img_url"] = ""
            extra_data["welcome_img_url"] = ""
            try:
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            except Exception: pass
        else:
            welcome_img = request.files.get("E-card_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    os.makedirs(upload_dir, exist_ok=True)
                    welcome_name = "welcome" + ext
                    welcome_img.save(os.path.join(upload_dir, welcome_name))
                    welcome_url = f"/static/uploads/pdf/{qrcard_id}/{welcome_name}"
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif qrcard.get("welcome_img_url"):
                extra_data["welcome_img_url"] = qrcard["welcome_img_url"]

        if request.form.get("E-card_profile_img_delete") == "1":
            for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                extra_data[f] = ""
                qrcard[f] = ""
            try:
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]}})
            except Exception: pass
        else:
            cover_img = request.files.get("E-card_profile_img")
            if cover_img and cover_img.filename:
                cover_img.seek(0, 2)
                if cover_img.tell() <= 2 * 1024 * 1024:
                    cover_img.seek(0)
                    ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    os.makedirs(upload_dir, exist_ok=True)
                    cover_name = "pdf_cover_img" + ext
                    cover_img.save(os.path.join(upload_dir, cover_name))
                    cover_url = f"/static/uploads/pdf/{qrcard_id}/{cover_name}"
                    for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            else:
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    if qrcard.get(f): extra_data[f] = qrcard[f]
                    
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), extra_data)
        qrcard.update(extra_data)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft:
            qrcard.update(draft)
            url_content = draft.get("url_content") or qrcard.get("url_content") or "qrcardku.com"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "qrcardku.com"
            qr_name = qrcard.get("name") or "Untitled QR"
    qr_encode_url = config.G_BASE_URL + "/ecard/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_ecard.view_update_ecard(app).update_qr_design_html(
        qrcard=qrcard, url_content=url_content, qr_name=qr_name, qr_encode_url=qr_encode_url
    )


@app.route("/qr/update/pdf/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_pdf(qrcard_id):
    """Step 1 (content) for PDF. POST -> design; POST back_from_design -> re-render content. GET uses draft."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_pdf_proc as _qrp
    qrcard = _qrp.qr_pdf_proc(app).get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        short_code = request.form.get("short_code", "").strip()
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color", "pdf_title_font", "pdf_title_color",
                      "pdf_text_font", "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc", "pdf_website",
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "scan_limit_enabled", "scan_limit_value", "pdf_font_apply_all"]
        ecard_data = {f: request.form.get(f, "") for f in pdf_fields if f in request.form}
        if request.form.get("welcome_img_delete") == "1":
            qrcard["welcome_img_url"] = ""
            ecard_data["welcome_img_url"] = ""
            try:
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": ""}}
                )
            except Exception:
                app.logger.exception("Failed to clear welcome_img_url for qrcard %s", qrcard_id)
        else:
            welcome_img = request.files.get("pdf_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                welcome_size = welcome_img.tell()
                welcome_img.seek(0)
                if welcome_size > 1024 * 1024:
                    return view_update_pdf.view_update_pdf(app).update_qr_content_html(
                        qrcard=qrcard, url_content=url_content, qr_name=qr_name, short_code=short_code or None,
                        error_msg="Welcome image must be 1 MB or smaller.", base_url=config.G_BASE_URL
                    )
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
                os.makedirs(upload_dir, exist_ok=True)
                welcome_name = "welcome" + ext
                welcome_img.save(os.path.join(upload_dir, welcome_name))
                welcome_url = f"/static/uploads/pdf/{qrcard_id}/{welcome_name}"
                ecard_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}},
                )
            elif qrcard.get("welcome_img_url"):
                ecard_data["welcome_img_url"] = qrcard["welcome_img_url"]
        _cover_img_fields = ["pdf_t1_header_img_url", "pdf_t3_circle_img_url", "pdf_t4_circle_img_url"]
        cover_img = request.files.get("pdf_t1_header_img")
        cover_delete = request.form.get("pdf_t1_header_img_delete") == "1"
        if cover_delete:
            for _f in _cover_img_fields:
                ecard_data[_f] = ""
                qrcard[_f] = ""
            from pytavia_core import database as _db_c, config as _cfg_c
            _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
            _mgd.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$set": {_f: "" for _f in _cover_img_fields}},
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
                    ecard_data[_f] = cover_url
                    qrcard[_f] = cover_url
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {_f: cover_url for _f in _cover_img_fields}},
                )
        else:
            existing_cover = (qrcard.get("pdf_t1_header_img_url") or qrcard.get("pdf_t3_circle_img_url") or qrcard.get("pdf_t4_circle_img_url") or "")
            for _f in _cover_img_fields:
                ecard_data[_f] = existing_cover
                qrcard[_f] = existing_cover
        if request.form.get("back_from_design"):
            existing_draft = _get_qr_draft(session, qrcard_id) or {}
            ecard_data["pdf_display_names"] = existing_draft.get("pdf_display_names", [])
            ecard_data["pdf_item_descs"] = existing_draft.get("pdf_item_descs", [])
            ecard_data["pdf_existing_urls"] = existing_draft.get("pdf_existing_urls", [])
            _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, ecard_data)
            qrcard.update(ecard_data)
            _apply_pdf_draft_to_files(qrcard, ecard_data)
            return view_update_pdf.view_update_pdf(app).update_qr_content_html(
                qrcard=qrcard, url_content=url_content, qr_name=qr_name, short_code=short_code or None, base_url=config.G_BASE_URL
            )
        ecard_data["pdf_display_names"] = request.form.getlist("pdf_display_names")
        ecard_data["pdf_item_descs"] = request.form.getlist("pdf_item_descs")
        ecard_data["pdf_existing_urls"] = request.form.getlist("existing_pdf_urls")
        proc = _qrp.qr_pdf_proc(app)
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_pdf.view_update_pdf(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists. Please choose a unique name.", base_url=config.G_BASE_URL
            )
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), ecard_data)
        qrcard.update(ecard_data)
        pdf_file_list = request.files.getlist("pdf_files")
        if pdf_file_list and any(f.filename for f in pdf_file_list):
            pdf_upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
            os.makedirs(pdf_upload_dir, exist_ok=True)
            qrcard_db = proc.get_qrcard(fk_user_id, qrcard_id)
            db_files = list(qrcard_db.get("pdf_files", [])) if qrcard_db else []
            _step_existing_urls = request.form.getlist("existing_pdf_urls")
            _step_display_names = request.form.getlist("pdf_display_names")
            _step_item_descs = request.form.getlist("pdf_item_descs")
            db_map = {f.get("url"): dict(f) for f in db_files}
            existing_files = []
            for i, url in enumerate(_step_existing_urls):
                entry = db_map.get(url, {"name": url.split("/")[-1], "url": url})
                if not isinstance(entry, dict):
                    entry = dict(entry)
                if i < len(_step_display_names) and _step_display_names[i].strip():
                    entry["display_name"] = _step_display_names[i].strip()
                if i < len(_step_item_descs):
                    entry["item_desc"] = _step_item_descs[i].strip()
                existing_files.append(entry)
            existing_names = set()
            existing_safe_names = set()
            for _f_entry in existing_files:
                if _f_entry.get("name"):
                    existing_names.add(_f_entry["name"])
                _url = (_f_entry.get("url") or "").strip()
                if _url:
                    existing_safe_names.add(os.path.basename(_url))
            _new_file_offset = len(_step_existing_urls)
            _new_file_idx = 0
            seen_upload_names = set()
            duplicate_name = None
            for f in pdf_file_list:
                if f and f.filename and f.filename.lower().endswith(".pdf"):
                    original_name = f.filename
                    safe_name = original_name.replace(" ", "_")
                    if original_name in existing_names or safe_name in existing_safe_names or original_name in seen_upload_names:
                        duplicate_name = original_name
                        break
                    seen_upload_names.add(original_name)
                    filepath = os.path.join(pdf_upload_dir, safe_name)
                    if not os.path.exists(filepath):
                        f.save(filepath)
                    file_entry = {"name": original_name, "url": f"/static/uploads/pdf/{qrcard_id}/{safe_name}"}
                    form_idx = _new_file_offset + _new_file_idx
                    if form_idx < len(_step_display_names) and _step_display_names[form_idx].strip():
                        file_entry["display_name"] = _step_display_names[form_idx].strip()
                    if form_idx < len(_step_item_descs) and _step_item_descs[form_idx].strip():
                        file_entry["item_desc"] = _step_item_descs[form_idx].strip()
                    _new_file_idx += 1
                    existing_files.append(file_entry)
                    existing_names.add(original_name)
                    existing_safe_names.add(safe_name)
            if duplicate_name:
                qrcard.update(ecard_data)
                return view_update_pdf.view_update_pdf(app).update_qr_content_html(
                    qrcard=qrcard, url_content=url_content, qr_name=qr_name, short_code=short_code or None,
                    error_msg=f"Oops, a PDF named '{duplicate_name}' is already attached to this QR card. Please rename the file or choose a different PDF.",
                    base_url=config.G_BASE_URL,
                )
            proc.update_pdf_files(fk_user_id, qrcard_id, existing_files)
            ecard_data["pdf_existing_urls"] = [f.get("url") for f in existing_files if f.get("url")]
            ecard_data["pdf_display_names"] = [f.get("display_name", f.get("name", "")) for f in existing_files]
            ecard_data["pdf_item_descs"] = [f.get("item_desc", "") for f in existing_files]
            _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), ecard_data)
    # GET or POST success -> design
    if request.method == "POST" and not request.form.get("back_from_design"):
        return view_update_pdf.view_update_pdf(app).update_qr_design_html(
            qrcard=qrcard, url_content=url_content, qr_name=qr_name
        )
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qrcard.update(draft)
        _apply_pdf_draft_to_files(qrcard, draft)
        return view_update_pdf.view_update_pdf(app).update_qr_content_html(
            qrcard=qrcard, url_content=draft.get("url_content"), qr_name=draft.get("qr_name"),
            short_code=draft.get("short_code") or None, base_url=config.G_BASE_URL
        )
    return view_update_pdf.view_update_pdf(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


@app.route("/qr/update/web/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_web(qrcard_id):
    """Step 1 (content) for Web. POST -> design."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_core import database
    from pytavia_core import config as _cfg
    qrcard = database.get_db_conn(_cfg.mainDB).db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        short_code = request.form.get("short_code", "").strip()
        from pytavia_modules.qr import qr_web_proc
        proc = qr_web_proc.qr_web_proc(app)
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_web.view_update_web(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists. Please choose a unique name.", base_url=config.G_BASE_URL
            )
        _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, None)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
        qrcard["short_code"] = short_code or qrcard.get("short_code")
        return view_update_web.view_update_web(app).update_qr_design_html(
            qrcard=qrcard, url_content=url_content, qr_name=qr_name,
            qr_encode_url=config.G_BASE_URL + "/web/" + short_code if short_code else None
        )
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qrcard.update(draft)
        return view_update_web.view_update_web(app).update_qr_content_html(
            qrcard=qrcard, url_content=draft.get("url_content"), qr_name=draft.get("qr_name"),
            short_code=draft.get("short_code") or None, base_url=config.G_BASE_URL
        )
    return view_update_web.view_update_web(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


def _merge_ecard_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Overlay db_qrcard_ecard document onto qrcard so edit pages get full E-card fields.
    If no ecard doc exists (e.g. old cards), create one from defaults so future saves persist."""
    if not qrcard:
        return qrcard
    ecard_doc = mgd_db.db_qrcard_ecard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    )
    if not ecard_doc:
        from pytavia_core import database
        ecard_doc = database.get_record("db_qrcard_ecard")
        ecard_doc["qrcard_id"] = qrcard_id
        ecard_doc["fk_user_id"] = fk_user_id
        ecard_doc["name"] = qrcard.get("name", "")
        ecard_doc["url_content"] = qrcard.get("url_content", "")
        ecard_doc["short_code"] = qrcard.get("short_code", "")
        ecard_doc["status"] = qrcard.get("status", "ACTIVE")
        try:
            mgd_db.db_qrcard_ecard.insert_one(ecard_doc)
        except Exception:
            pass
    out = dict(qrcard)
    for key, value in ecard_doc.items():
        if key != "_id":
            out[key] = value
    return out


@app.route("/qr/update/ecard/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_ecard(qrcard_id):
    """Step 1 (content) for E-card. POST -> design; POST back_from_design -> re-show content with data. Uses same pattern as PDF."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_ecard_proc as _qre
    proc = _qre.qr_ecard_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_ecard_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    if request.method == "POST":
        # Back from design: re-show content form with posted data (no file uploads, no DB writes)
        if request.form.get("back_from_design"):
            from itertools import zip_longest
            url_content = (request.form.get("url_content") or "").strip()
            if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
                url_content = "https://" + url_content
            qr_name = (request.form.get("qr_name") or "").strip()
            short_code = (request.form.get("short_code") or "").strip()
            # Rebuild qrcard from form (scalars + contact arrays)
            draft = dict(qrcard)
            draft["url_content"] = url_content or draft.get("url_content") or "qrcardku.com"
            draft["name"] = qr_name or draft.get("name") or "Untitled QR"
            draft["short_code"] = short_code or draft.get("short_code") or ""
            for key in request.form:
                if key in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                    continue
                if key.endswith("[]"):
                    continue
                val_list = request.form.getlist(key)
                if len(val_list) > 1:
                    draft[key] = val_list
                else:
                    draft[key] = val_list[0] if val_list else ""
            # Contact arrays from flat form fields (Back form sends E-card_phone_label[], etc.)
            pl = request.form.getlist("E-card_phone_label[]")
            pn = request.form.getlist("E-card_phone_number[]")
            draft["E-card_phones"] = [{"label": (a or "").strip(), "number": (b or "").strip()} for a, b in zip_longest(pl, pn, fillvalue="")]
            el = request.form.getlist("E-card_email_label[]")
            ev = request.form.getlist("E-card_email_value[]")
            draft["E-card_emails"] = [{"label": (a or "").strip(), "value": (b or "").strip()} for a, b in zip_longest(el, ev, fillvalue="")]
            wl = request.form.getlist("E-card_website_label[]")
            wv = request.form.getlist("E-card_website_value[]")
            draft["E-card_websites"] = [{"label": (a or "").strip(), "value": (b or "").strip()} for a, b in zip_longest(wl, wv, fillvalue="")]
            draft["E-card_website"] = (draft["E-card_websites"][0].get("value", "")) if draft.get("E-card_websites") else ""
            raw_url = (draft.get("url_content") or "").strip()
            url_content_display = raw_url[8:] if raw_url.startswith("https://") else (raw_url[7:] if raw_url.startswith("http://") else raw_url)
            return view_update_ecard.view_update_ecard(app).update_qr_content_html(
                qrcard=draft,
                url_content=url_content_display or "qrcardku.com",
                qr_name=draft.get("name") or "",
                short_code=draft.get("short_code") or "",
                base_url=config.G_BASE_URL,
            )
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        short_code = request.form.get("short_code", "").strip()
        extra_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"] and not key.endswith("[]"):
                val_list = request.form.getlist(key)
                extra_data[key] = val_list[0] if val_list else ""

        # Unchecked checkboxes are not in request.form; set explicitly so "off" is saved and preserved on Back
        extra_data["E-card_font_apply_all"] = "1" if request.form.get("E-card_font_apply_all") else ""

        # Build structured contact lists from form arrays
        phone_labels = request.form.getlist("E-card_phone_label[]")
        phone_numbers = request.form.getlist("E-card_phone_number[]")
        phones = [{"label": (l or "").strip(), "number": (n or "").strip()} for l, n in zip(phone_labels, phone_numbers) if (n or "").strip()]
        extra_data["E-card_phones"] = phones

        email_labels = request.form.getlist("E-card_email_label[]")
        email_values = request.form.getlist("E-card_email_value[]")
        emails = [{"label": (l or "").strip(), "value": (v or "").strip()} for l, v in zip(email_labels, email_values) if (v or "").strip()]
        extra_data["E-card_emails"] = emails

        website_labels = request.form.getlist("E-card_website_label[]")
        website_values = request.form.getlist("E-card_website_value[]")
        websites = [{"label": (l or "").strip(), "value": (v or "").strip()} for l, v in zip(website_labels, website_values) if (v or "").strip()]
        extra_data["E-card_websites"] = websites
        extra_data["E-card_website"] = websites[0]["value"] if websites else ""

        import os
        upload_dir = os.path.join(app.root_path, "static", "uploads", "pdf", qrcard_id)
        
        if request.form.get("E-card_welcome_img_delete") == "1":
            qrcard["welcome_img_url"] = ""
            extra_data["welcome_img_url"] = ""
            try:
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            except Exception: pass
        else:
            welcome_img = request.files.get("E-card_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    os.makedirs(upload_dir, exist_ok=True)
                    welcome_name = "welcome" + ext
                    welcome_img.save(os.path.join(upload_dir, welcome_name))
                    welcome_url = f"/static/uploads/pdf/{qrcard_id}/{welcome_name}"
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif qrcard.get("welcome_img_url"):
                extra_data["welcome_img_url"] = qrcard["welcome_img_url"]

        if request.form.get("E-card_profile_img_delete") == "1":
            for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                extra_data[f] = ""
                qrcard[f] = ""
            try:
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]}})
            except Exception: pass
        else:
            cover_img = request.files.get("E-card_profile_img")
            if cover_img and cover_img.filename:
                cover_img.seek(0, 2)
                if cover_img.tell() <= 2 * 1024 * 1024:
                    cover_img.seek(0)
                    ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    os.makedirs(upload_dir, exist_ok=True)
                    cover_name = "ecard_cover_img" + ext
                    cover_img.save(os.path.join(upload_dir, cover_name))
                    cover_url = f"/static/uploads/pdf/{qrcard_id}/{cover_name}"
                    for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            else:
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    if qrcard.get(f): extra_data[f] = qrcard[f]

        from pytavia_modules.qr import qr_ecard_proc
        proc = qr_ecard_proc.qr_ecard_proc(app)
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_ecard.view_update_ecard(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists. Please choose a unique name.", base_url=config.G_BASE_URL
            )
        _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, extra_data)
        # Save contact info, about, and design fields immediately so public page reflects changes
        contact_update = {
            "E-card_phones": phones,
            "E-card_emails": emails,
            "E-card_websites": websites,
            "E-card_website": extra_data.get("E-card_website", ""),
            "E-card_company": extra_data.get("E-card_company", ""),
            "E-card_title": extra_data.get("E-card_title", ""),
            "E-card_desc": extra_data.get("E-card_desc", ""),
            "E-card_btn_text": extra_data.get("E-card_btn_text", ""),
            "name": qr_name,
            "url_content": url_content,
        }
        # Include design/visual fields if provided
        for _dk in ["E-card_template", "E-card_primary_color", "E-card_secondary_color",
                    "E-card_title_font", "E-card_text_font", "E-card_title_color", "E-card_text_color",
                    "welcome_time", "welcome_bg_color"]:
            if _dk in extra_data and extra_data[_dk] != "":
                contact_update[_dk] = extra_data[_dk]
        # Checkbox: always persist so "off" clears the previous "on"
        contact_update["E-card_font_apply_all"] = extra_data.get("E-card_font_apply_all", "")
        database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": contact_update})
        database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": contact_update})
        qrcard.update(extra_data)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
        qrcard["short_code"] = short_code or qrcard.get("short_code")
        return view_update_ecard.view_update_ecard(app).update_qr_design_html(
            qrcard=qrcard, url_content=url_content, qr_name=qr_name
        )
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qrcard.update(draft)
        return view_update_ecard.view_update_ecard(app).update_qr_content_html(
            qrcard=qrcard, url_content=draft.get("url_content"), qr_name=draft.get("qr_name"),
            short_code=draft.get("short_code") or None, base_url=config.G_BASE_URL
        )
    return view_update_ecard.view_update_ecard(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)

# ─── New QR: type-specific routes (no qr_type param). Each uses its own view + proc. ───

@app.route("/qr/new/pdf")
def user_new_qr_pdf():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_pdf
    return view_pdf.view_pdf(app).new_qr_content_html(base_url=config.G_BASE_URL)

@app.route("/qr/new/pdf/qr-design", methods=["GET", "POST"])
def user_new_qr_design_pdf():
    from flask import request
    import os
    import re
    import uuid as _uuid
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_pdf
    from pytavia_modules.qr import qr_pdf_proc
    v = view_pdf.view_pdf(app)
    proc = qr_pdf_proc.qr_pdf_proc(app)
    url_content = "qrcardku.com"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    pdf_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "qrcardku.com")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color", "pdf_title_font", "pdf_title_color",
                      "pdf_text_font", "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc", "pdf_website",
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "pdf_font_apply_all"]
        pdf_data = {f: request.form.get(f, "") for f in pdf_fields}
        pdf_data["scan_limit_enabled"] = request.form.get("scan_limit_enabled", "")
        pdf_data["scan_limit_value"] = request.form.get("scan_limit_value", "")
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
        session["pdf_display_names"] = request.form.getlist("pdf_display_names")
        session["pdf_item_descs"] = request.form.getlist("pdf_item_descs")
        session.modified = True
        welcome_img = request.files.get("pdf_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                welcome_img.save(os.path.join(tmp_dir, "welcome" + ext))
                session["welcome_img_tmp_key"] = tmp_key
                session["welcome_img_tmp_name"] = "welcome" + ext
                session.modified = True
            else:
                error_msg = "Welcome image must be 1 MB or smaller."
        cover_img = request.files.get("pdf_t1_header_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                cover_img.save(os.path.join(tmp_dir, "pdf_cover_img" + ext))
                session["cover_img_tmp_key"] = tmp_key
                session["cover_img_tmp_name"] = "pdf_cover_img" + ext
                session.modified = True
        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/pdf/" + short_code
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, pdf_data=pdf_data)

@app.route("/qr/new/web")
def user_new_qr_web():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_web
    return view_web.view_web(app).new_qr_content_html(base_url=config.G_BASE_URL)

@app.route("/qr/new/web/qr-design", methods=["GET", "POST"])
def user_new_qr_design_web():
    from flask import request
    import re
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_web
    from pytavia_modules.qr import qr_web_proc
    v = view_web.view_web(app)
    proc = qr_web_proc.qr_web_proc(app)
    url_content = "qrcardku.com"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    if request.method == "POST":
        url_content = request.form.get("url_content", "qrcardku.com")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/web/" + short_code
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg)

@app.route("/qr/new/ecard", methods=["GET"])
@app.route("/qr/new/ecard/back", methods=["POST"])
def user_new_qr_ecard():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.view import view_ecard
    v = view_ecard.view_ecard(app)
    if request.method == "POST":
        # Back from design: re-show content form with saved data
        from itertools import zip_longest
        from flask import url_for
        url_content = request.form.get("url_content", "qrcardku.com")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        ecard_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    ecard_data[key] = val_list
                else:
                    ecard_data[key] = val_list[0] if val_list else ""
        # Restore profile/cover and welcome image URLs from session (files were saved on content->design POST)
        if session.get("cover_img_tmp_key") and session.get("cover_img_tmp_name"):
            cover_url = url_for(
                "static",
                filename="uploads/pdf/_tmp/{}/{}".format(
                    session["cover_img_tmp_key"], session["cover_img_tmp_name"]
                ),
            )
            ecard_data["E-card_t1_header_img_url"] = cover_url
            ecard_data["E-card_t3_circle_img_url"] = cover_url
            ecard_data["E-card_t4_circle_img_url"] = cover_url
        if session.get("welcome_img_tmp_key") and session.get("welcome_img_tmp_name"):
            ecard_data["welcome_img_url"] = url_for(
                "static",
                filename="uploads/pdf/_tmp/{}/{}".format(
                    session["welcome_img_tmp_key"], session["welcome_img_tmp_name"]
                ),
            )
        # Build contact row lists for template (normalize to list of {label, number/value})
        def _to_list(x):
            if x is None:
                return []
            return x if isinstance(x, (list, tuple)) else [x]
        labels = _to_list(ecard_data.get("E-card_phone_label[]"))
        numbers = _to_list(ecard_data.get("E-card_phone_number[]"))
        phone_list = [{"label": a or "", "number": b or ""} for a, b in zip_longest(labels, numbers, fillvalue="")]
        if not phone_list:
            phone_list = [{"label": "", "number": ""}]
        labels = _to_list(ecard_data.get("E-card_email_label[]"))
        values = _to_list(ecard_data.get("E-card_email_value[]"))
        email_list = [{"label": a or "", "value": b or ""} for a, b in zip_longest(labels, values, fillvalue="")]
        if not email_list:
            email_list = [{"label": "", "value": ""}]
        labels = _to_list(ecard_data.get("E-card_website_label[]"))
        values = _to_list(ecard_data.get("E-card_website_value[]"))
        website_list = [{"label": a or "", "value": b or ""} for a, b in zip_longest(labels, values, fillvalue="")]
        if not website_list:
            website_list = [{"label": "", "value": ""}]
        return v.new_qr_content_html(
            base_url=config.G_BASE_URL,
            url_content=url_content,
            qr_name=qr_name,
            short_code=short_code,
            ecard_data=ecard_data,
            phone_list=phone_list,
            email_list=email_list,
            website_list=website_list,
        )
    return v.new_qr_content_html(base_url=config.G_BASE_URL)

@app.route("/qr/new/ecard/qr-design", methods=["GET", "POST"])
def user_new_qr_design_ecard():
    from flask import request
    import os
    import re
    import uuid as _uuid
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_ecard
    from pytavia_modules.qr import qr_ecard_proc
    v = view_ecard.view_ecard(app)
    proc = qr_ecard_proc.qr_ecard_proc(app)
    url_content = "qrcardku.com"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    ecard_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "qrcardku.com")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    ecard_data[key] = val_list
                else:
                    ecard_data[key] = val_list[0] if val_list else ""

        tmp_key = session.get("pdf_tmp_key") or _uuid.uuid4().hex
        session["pdf_tmp_key"] = tmp_key
        tmp_dir = os.path.join(app.root_path, "static", "uploads", "pdf", "_tmp", tmp_key)
        os.makedirs(tmp_dir, exist_ok=True)
        
        session.modified = True
        welcome_img = request.files.get("E-card_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                welcome_img.save(os.path.join(tmp_dir, "welcome" + ext))
                session["welcome_img_tmp_key"] = tmp_key
                session["welcome_img_tmp_name"] = "welcome" + ext
                session.modified = True
            else:
                error_msg = "Welcome image must be 1 MB or smaller."
                
        cover_img = request.files.get("E-card_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                cover_img.save(os.path.join(tmp_dir, "pdf_cover_img" + ext))
                session["cover_img_tmp_key"] = tmp_key
                session["cover_img_tmp_name"] = "pdf_cover_img" + ext
                session.modified = True
        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/ecard/" + short_code
        # Put tmp image URLs into ecard_data so the Back form includes them and they survive when user clicks Back
        from flask import url_for as _url_for
        if session.get("cover_img_tmp_key") and session.get("cover_img_tmp_name"):
            _cover_url = _url_for(
                "static",
                filename="uploads/pdf/_tmp/{}/{}".format(
                    session["cover_img_tmp_key"], session["cover_img_tmp_name"]
                ),
            )
            ecard_data["E-card_t1_header_img_url"] = _cover_url
            ecard_data["E-card_t3_circle_img_url"] = _cover_url
            ecard_data["E-card_t4_circle_img_url"] = _cover_url
        if session.get("welcome_img_tmp_key") and session.get("welcome_img_tmp_name"):
            ecard_data["welcome_img_url"] = _url_for(
                "static",
                filename="uploads/pdf/_tmp/{}/{}".format(
                    session["welcome_img_tmp_key"], session["welcome_img_tmp_name"]
                ),
            )
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, ecard_data=ecard_data)

@app.route("/qr/save/pdf", methods=["POST"])
def qr_save_pdf():
    """Route only: PDF save is handled entirely in qr_pdf_proc."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_pdf_proc
    from pytavia_modules.view import view_pdf
    response = qr_pdf_proc.qr_pdf_proc(app).complete_pdf_save(request, session, app.root_path)
    if response.get("success"):
        return redirect(url_for("user_qr_list"))
    return view_pdf.view_pdf(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        ecard_data=response.get("ecard_data", {}),
    )


@app.route("/qr/save/web", methods=["POST"])
def qr_save_web():
    """Route only: Web save is handled entirely in qr_web_proc."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_web_proc
    from pytavia_modules.view import view_web
    response = qr_web_proc.qr_web_proc(app).complete_web_save(request, session)
    if response.get("success"):
        return redirect(url_for("user_qr_list"))
    return view_web.view_web(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
    )


@app.route("/qr/save/ecard", methods=["POST"])
def qr_save_ecard():
    """Route only: E-card save is handled entirely in qr_ecard_proc."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_ecard_proc
    from pytavia_modules.view import view_ecard
    response = qr_ecard_proc.qr_ecard_proc(app).complete_ecard_save(request, session, app.root_path)
    if response.get("success"):
        return redirect(url_for("user_qr_list"))
    return view_ecard.view_ecard(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        ecard_data=response.get("ecard_data", {}),
    )


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
    from pytavia_modules.qr import qr_pdf_proc as _qrproc_rm
    ok = _qrproc_rm.qr_pdf_proc(app).remove_pdf_file(fk_user_id, qrcard_id, file_url)
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
    from pytavia_modules.view import view_qr_list
    return view_qr_list.view_qr_list(app).my_qr_codes_html(fk_user_id=session.get("fk_user_id"))

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
