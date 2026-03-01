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
    """Public redirect: scan goes to qrcardku.com/p/<short_code> -> redirect to current url_content (dynamic web)."""
    from pytavia_modules.qr import qr_proc
    qrcard = qr_proc.qr_proc(app).get_qrcard_by_short_code(short_code)
    if not qrcard or not qrcard.get("url_content"):
        abort(404)
    dest = qrcard["url_content"].strip()
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

def _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code=None):
    if "qr_draft" not in session:
        session["qr_draft"] = {}
    session["qr_draft"][qrcard_id] = {
        "url_content": url_content,
        "qr_name": qr_name,
        "short_code": short_code or "",
    }
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
        # Back from design: re-render content step with current values; update draft
        if request.form.get("back_from_design"):
            _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code)
            return view_user.view_user(app).update_qr_content_html(
                qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name,
                short_code=short_code or None
            )
        if not qr_proc.qr_proc(app).is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_user.view_user(app).update_qr_content_html(
                qr_type=qr_type, qrcard=qrcard, error_msg="A QR card with this name already exists. Please choose a unique name."
            )
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip())
        return view_user.view_user(app).update_qr_design_html(
            qr_type=qr_type, qrcard=qrcard, url_content=url_content, qr_name=qr_name
        )
    # GET: use session draft if available so Step 2 tab / Back preserves edits
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        return view_user.view_user(app).update_qr_content_html(
            qr_type=qr_type, qrcard=qrcard,
            url_content=draft.get("url_content"), qr_name=draft.get("qr_name"),
            short_code=draft.get("short_code") or None
        )
    return view_user.view_user(app).update_qr_content_html(qr_type=qr_type, qrcard=qrcard)

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
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip())
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft:
            url_content = draft.get("url_content") or qrcard.get("url_content") or "qrcardku.com"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "qrcardku.com"
            qr_name = qrcard.get("name") or "Untitled QR"
    qr_encode_url = None
    if qr_type == "web" and qrcard.get("short_code"):
        qr_encode_url = request.url_root.rstrip("/") + "/p/" + qrcard["short_code"]
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
    params = {
        "fk_user_id": fk_user_id,
        "qrcard_id": qrcard_id,
        "name": qr_name or "Untitled QR",
        "url_content": url_content or "",
    }
    qr_proc.qr_proc(app).edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/new/<qr_type>")
def user_new_qr_type(qr_type):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    # The view will handle mapping 'web', 'pdf', 'images', 'ecardname', 'video', 'links', 'sosmed'
    return view_user.view_user(app).new_qr_type_html(qr_type)

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
        
        if not qr_proc_inst.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return view_user.view_user(app).new_qr_content_html(qr_type, url_content=url_content, qr_name=qr_name, error_msg=error_msg)
        
        if qr_type == "web":
            if short_code:
                import re
                if not re.match(r"^[a-z0-9\-]{2,32}$", short_code):
                    error_msg = "Address identifier must be 2–32 characters: letters, numbers, or hyphens."
                    return view_user.view_user(app).new_qr_content_html(qr_type, url_content=url_content, qr_name=qr_name, short_code=short_code, error_msg=error_msg)
                if not qr_proc_inst.is_short_code_unique(short_code):
                    error_msg = "This address identifier is already in use. Please choose another."
                    return view_user.view_user(app).new_qr_content_html(qr_type, url_content=url_content, qr_name=qr_name, short_code=short_code, error_msg=error_msg)
            else:
                short_code = qr_proc_inst._generate_short_code()
                while not qr_proc_inst.is_short_code_unique(short_code):
                    short_code = qr_proc_inst._generate_short_code()
            base = request.url_root.rstrip("/")
            qr_encode_url = base + "/p/" + short_code
    
    return view_user.view_user(app).new_qr_design_html(
        qr_type, url_content=url_content, qr_name=qr_name,
        short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg
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
        "url_content": request.form.get("url_content", "")
    }
    if qr_type == "web":
        params["short_code"] = (request.form.get("short_code") or "").strip().lower()
    
    from pytavia_modules.qr import qr_proc
    result = qr_proc.qr_proc(app).add_qrcard(params)
    if result.get("message_action") == "ADD_QRCARD_FAILED":
        sc = params.get("short_code") or ""
        return view_user.view_user(app).new_qr_design_html(
            qr_type,
            url_content=request.form.get("url_content", ""),
            qr_name=request.form.get("qr_name", ""),
            short_code=sc,
            qr_encode_url=request.url_root.rstrip("/") + "/p/" + sc if sc else None,
            error_msg=result.get("message_desc", "Save failed.")
        )
    return redirect(url_for("user_qr_list"))

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
