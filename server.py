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
sys.path.append("pytavia_modules/configuration")
sys.path.append("pytavia_modules/cookie")
sys.path.append("pytavia_modules/middleware")
sys.path.append("pytavia_modules/security")
sys.path.append("pytavia_modules/user")
sys.path.append("pytavia_modules/view")
sys.path.append("pytavia_modules/storage")


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
from admin              import admin_frame_proc


from view               import view_welcome
from view               import view_admin
from view               import view_landing
from view               import view_login
from view               import view_user
from pytavia_modules.view import view_update_pdf, view_update_web, view_update_ecard
from pytavia_modules.view import view_update_links, view_update_sosmed
from pytavia_modules.view import view_update_allinone
from storage import r2_storage_proc as r2_mod

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
from flask              import Response

from authlib.integrations.flask_client import OAuth
import os
import uuid

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

# Seed first superadmin on startup (no-op if db_admin already has records)
try:
    admin_proc.admin_proc(app).seed_first_admin()
except Exception:
    pass

# Inject admin session info into all admin templates
@app.context_processor
def inject_admin_session():
    return dict(
        admin_name = session.get("admin_name", ""),
        admin_email= session.get("admin_email", ""),
        admin_role = session.get("admin_role", ""),
    )


def _update_frame_id(fk_user_id, qrcard_id, form_frame_id):
    """Persist the chosen custom frame against the QR base record."""
    if not qrcard_id:
        return
    try:
        from pytavia_core import database, config as _cfg
        _db = database.get_db_conn(_cfg.mainDB)
        _db.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {"$set": {"frame_id": form_frame_id or ""}},
        )
    except Exception:
        pass


def _save_custom_qr_image(fk_user_id, qrcard_id, qr_image_data, style_fields):
    """Decode base64 PNG from client, upload to R2, store as qr_image_url in db_qrcard."""
    if not qrcard_id or not qr_image_data:
        return
    try:
        import io, base64
        from pytavia_core import database as _db_mod, config as _cfg
        from pytavia_modules.storage import r2_storage_proc as _r2_mod

        # Strip data URI prefix if present
        if "," in qr_image_data:
            qr_image_data = qr_image_data.split(",", 1)[1]

        img_bytes = base64.b64decode(qr_image_data)
        buf = io.BytesIO(img_bytes)
        buf.seek(0)

        import time as _time
        key = f"qr-images/{fk_user_id}/{qrcard_id}.png"
        file_size = len(img_bytes)
        url = _r2_mod.r2_storage_proc().upload_bytes(buf, key, content_type="image/png")
        url = url + "?v=" + str(int(_time.time()))

        # Track asset
        try:
            from pytavia_modules.user import asset_tracker_proc as _atp
            _tracker = _atp.asset_tracker_proc()
            _tracker.untrack_key(key)
            _tracker.track(
                fk_user_id=fk_user_id,
                r2_key=key,
                file_size=file_size,
                qrcard_id=qrcard_id,
                qr_type="qr_image",
                file_name=f"{qrcard_id}.png",
            )
        except Exception:
            pass

        _db = _db_mod.get_db_conn(_cfg.mainDB)
        update_fields = {"qr_image_url": url}
        update_fields.update(style_fields or {})
        _db.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {
                "$set": update_fields,
                "$unset": {"qr_composite_url": ""},  # cleared; _save_qr_composite will rebuild if frame exists
            },
        )
    except Exception:
        import traceback
        traceback.print_exc()


def _save_qr_composite(app, fk_user_id, qrcard_id, qr_encode_url, frame_id):
    """Generate QR+frame composite image, upload to R2, store URL in db_qrcard.
    Runs synchronously so the composite is guaranteed ready on the next page load."""
    if not frame_id or not qrcard_id or not qr_encode_url:
        return
    try:
        import io
        import urllib.request as _ureq
        import qrcode
        from PIL import Image
        from pytavia_core import database as _db_mod, config as _cfg
        from pytavia_modules.storage import r2_storage_proc as _r2_mod

        _db = _db_mod.get_db_conn(_cfg.mainDB)

        # Locate frame (user frame first, then admin frame)
        frame = _db.db_qr_frame.find_one(
            {"frame_id": frame_id, "fk_user_id": fk_user_id, "status": "ACTIVE"}
        )
        if not frame:
            frame = _db.db_admin_frame.find_one({"frame_id": frame_id, "status": "ACTIVE"})
        if not frame or not frame.get("image_url"):
            return

        qr_x = float(frame.get("qr_x", 0))
        qr_y = float(frame.get("qr_y", 0))
        qr_w = float(frame.get("qr_w", 0))
        qr_h = float(frame.get("qr_h", 0))
        if qr_w <= 0 or qr_h <= 0:
            return

        # Use custom styled QR if user saved one, otherwise generate plain QR
        qr_record = _db.db_qrcard.find_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {"qr_image_url": 1},
        )
        custom_qr_url = qr_record.get("qr_image_url", "") if qr_record else ""
        if custom_qr_url:
            req_qr = _ureq.Request(custom_qr_url, headers={"User-Agent": "Mozilla/5.0"})
            with _ureq.urlopen(req_qr, timeout=15) as resp_qr:
                qr_pil = Image.open(io.BytesIO(resp_qr.read())).convert("RGBA")
        else:
            qr_obj = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10, border=2,
            )
            qr_obj.add_data(qr_encode_url)
            qr_obj.make(fit=True)
            qr_pil = qr_obj.make_image(fill_color="black", back_color="white").convert("RGBA")

        # Load frame image from R2
        req = _ureq.Request(frame["image_url"], headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=15) as resp:
            frame_bytes = resp.read()
        frame_pil = Image.open(io.BytesIO(frame_bytes)).convert("RGBA")

        # Composite: paste QR at the marked area using object-fit:contain semantics
        # (matches the design preview which uses object-fit:contain on the QR image)
        fw, fh = frame_pil.size
        x = int(qr_x * fw)
        y = int(qr_y * fh)
        w = int(qr_w * fw)
        h = int(qr_h * fh)
        # Keep QR square (1:1), centered in the marked area
        side = min(w, h)
        cx = x + (w - side) // 2
        cy = y + (h - side) // 2
        qr_resized = qr_pil.resize((side, side), Image.LANCZOS)
        result = frame_pil.copy()
        result.paste(qr_resized, (cx, cy))

        # Encode to PNG bytes
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)

        # Upload to R2
        import time as _time
        key = f"qr-composites/{fk_user_id}/{qrcard_id}.png"
        file_size = buf.getbuffer().nbytes
        url = _r2_mod.r2_storage_proc().upload_bytes(
            buf, key, content_type="image/png",
        )
        url = url + "?v=" + str(int(_time.time()))

        # Track composite in db_qr_assets (replace old entry for same key)
        try:
            from pytavia_modules.user import asset_tracker_proc as _atp
            _tracker = _atp.asset_tracker_proc()
            _tracker.untrack_key(key)
            _tracker.track(
                fk_user_id=fk_user_id,
                r2_key=key,
                file_size=file_size,
                qrcard_id=qrcard_id,
                qr_type="composite",
                file_name=f"{qrcard_id}.png",
            )
        except Exception:
            pass

        # Persist URL on the QR record
        _db.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {"$set": {"qr_composite_url": url}},
        )
    except Exception:
        app.logger.debug(traceback.format_exc())


@app.route("/")
def index():
    return view_landing.view_landing().html()

@app.route("/admin")
def admin_redirect():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    return redirect(url_for("admin_admins"))

@app.route("/login", methods=["GET"])
def login_view():
    return view_login.view_login().html()

@app.route('/auth/login/<provider>')
def auth_social_login(provider):
    if provider == 'google':
        redirect_uri = url_for('auth_social_callback', provider='google', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)
    elif provider == 'linkedin':
        redirect_uri = url_for('auth_social_callback', provider='linkedin', _external=True)
        return oauth.linkedin.authorize_redirect(redirect_uri)
    return abort(404)

import traceback
@app.route('/auth/callback/<provider>')
def auth_social_callback(provider):
    try:
        if provider == 'google':
            token = oauth.google.authorize_access_token()
            user_info = oauth.google.parse_id_token(token, nonce=None)
            if not user_info:
                user_info = oauth.google.userinfo()
        elif provider == 'linkedin':
            token = oauth.linkedin.authorize_access_token()
            resp = oauth.linkedin.get('me?projection=(id,localizedFirstName,localizedLastName)')
            user_info = resp.json()
            email_resp = oauth.linkedin.get('emailAddress?q=members&projection=(elements*(handle~))')
            email_info = email_resp.json()
            if email_info.get('elements'):
                user_info['email'] = email_info['elements'][0]['handle~']['emailAddress']
        else:
            return abort(404)
            
        response = auth_proc.auth_proc(app).social_login(provider, user_info)
        if response.get("message_action") == "LOGIN_SUCCESS":
            session["fk_user_id"] = response["message_data"]["fk_user_id"]
            session["username"]   = response["message_data"]["username"]
            return redirect(url_for("user_dashboard"))
        else:
            return view_login.view_login().html(error_msg=response.get("message_desc", "Error"))
    except Exception as e:
        app.logger.debug(traceback.format_exc())
        return view_login.view_login().html(error_msg=f"Social login failed: {str(e)}")

@app.route('/email-verification')
def email_verification():
    token = request.args.get('token')
    response = auth_proc.auth_proc(app).verify_email(token)
    return view_login.view_login().html(error_msg=response["message_desc"])

@app.route('/forgot-password', methods=["GET"])
def forgot_password_view():
    return view_login.view_login().forgot_password_html()

@app.route('/forgot-password', methods=["POST"])
def forgot_password_post():
    email = request.form.get("email")
    response = auth_proc.auth_proc(app).forgot_password_request(email)
    msg = response.get("message_desc", "")
    return view_login.view_login().forgot_password_html(msg=msg)

@app.route('/password-reset', methods=["GET"])
def reset_password_view():
    token = request.args.get("token")
    if not token:
        return redirect(url_for('login_view'))
    return view_login.view_login().reset_password_html(token=token)

@app.route('/password-reset', methods=["POST"])
def reset_password_post():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).reset_password(params)
    if response["message_action"] == "RESET_PASSWORD_SUCCESS":
        return view_login.view_login().html(error_msg="Password reset successful. Please log in.")
    else:
        return view_login.view_login().reset_password_html(token=params.get("token"), error_msg=response["message_desc"])

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
    elif response["message_action"] == "LOGIN_UNVERIFIED":
        session["unverified_user_id"] = response["message_data"]["fk_user_id"]
        session["unverified_email"] = response["message_data"]["email"]
        return redirect(url_for("verify_otp_view"))
    else:
        return view_login.view_login().html(error_msg=response["message_desc"])

@app.route("/verify-otp", methods=["GET"])
def verify_otp_view():
    if "unverified_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_login.view_login().verify_otp_html(email=session.get("unverified_email"))

@app.route("/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    if "unverified_user_id" not in session:
        return redirect(url_for("login_view"))
    
    params = request.form.to_dict()
    params["fk_user_id"] = session["unverified_user_id"]
    response = auth_proc.auth_proc(app).verify_otp(params)
    
    if response["message_action"] == "VERIFY_SUCCESS":
        session.pop("unverified_user_id", None)
        session.pop("unverified_email", None)
        session["fk_user_id"] = response["message_data"]["fk_user_id"]
        session["username"]   = response["message_data"]["username"]
        return redirect(url_for("user_dashboard"))
    else:
        return view_login.view_login().verify_otp_html(
            email=session.get("unverified_email"), 
            error_msg=response["message_desc"]
        )

@app.route("/auth/resend-otp", methods=["POST"])
def auth_resend_otp():
    if "unverified_user_id" not in session:
        return jsonify({"message_action": "RESEND_FAILED", "message_desc": "Session expired."})
    
    response = auth_proc.auth_proc(app).resend_otp({"fk_user_id": session["unverified_user_id"]})
    return jsonify(response)

@app.route("/auth/admin_login", methods=["POST"])
def auth_admin_login():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).admin_login(params)
    if response["message_action"] == "LOGIN_SUCCESS":
        session["fk_admin_id"]  = response["message_data"]["fk_admin_id"]
        session["admin_email"]  = response["message_data"]["email"]
        session["admin_name"]   = response["message_data"]["name"]
        session["admin_role"]   = response["message_data"]["role"]
        return redirect(url_for("admin_redirect"))
    else:
        return view_login.view_login().admin_html(error_msg=response["message_desc"])

@app.route("/auth/admin_logout")
def auth_admin_logout():
    session.pop("fk_admin_id", None)
    session.pop("admin_email", None)
    session.pop("admin_name", None)
    session.pop("admin_role", None)
    return redirect(url_for("admin_login_view"))

@app.route("/admin/admins")
def admin_admins():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    if session.get("admin_role") != "superadmin":
        return redirect(url_for("admin_admins"))
    return view_admin.view_admin(app).admins_html()

@app.route("/admin/users")
def admin_users():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    msg = request.args.get("msg")
    error_msg = request.args.get("error_msg")
    return view_admin.view_admin(app).users_html(msg=msg, error_msg=error_msg)

@app.route("/admin/user/delete", methods=["POST"])
def admin_user_delete():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    if session.get("admin_role") != "superadmin":
        return redirect(url_for("admin_users"))
    
    params = request.form.to_dict()
    response = admin_proc.admin_proc(app).delete_user(params)
    if response["message_action"] == "DELETE_USER_SUCCESS":
        return redirect(url_for("admin_users", msg="User deleted successfully."))
    else:
        return redirect(url_for("admin_users", error_msg=response["message_desc"]))

@app.route("/admin/admin/add", methods=["POST"])
def admin_admin_add():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    if session.get("admin_role") != "superadmin":
        return redirect(url_for("admin_admins"))
    params = request.form.to_dict()
    response = admin_proc.admin_proc(app).add_admin(params)
    if response["message_action"] == "ADD_ADMIN_SUCCESS":
        return redirect(url_for("admin_admins"))
    else:
        return view_admin.view_admin(app).admins_html(error_msg=response["message_desc"])

@app.route("/admin/admin/toggle", methods=["POST"])
def admin_admin_toggle():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    if session.get("admin_role") != "superadmin":
        return redirect(url_for("admin_admins"))
    params = request.form.to_dict()
    admin_proc.admin_proc(app).toggle_admin_status(params)
    return redirect(url_for("admin_admins"))

@app.route("/admin/frames")
def admin_frames():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    return view_admin.view_admin(app).frames_html()

@app.route("/admin/frames/save", methods=["POST"])
def admin_frames_save():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    image_file = request.files.get("frame_image")
    name = (request.form.get("frame_name") or "").strip()
    try:
        qr_x = float(request.form.get("qr_x", 0))
        qr_y = float(request.form.get("qr_y", 0))
        qr_w = float(request.form.get("qr_w", 0))
        qr_h = float(request.form.get("qr_h", 0))
    except (ValueError, TypeError):
        return view_admin.view_admin(app).frames_html(error_msg="Invalid QR area coordinates.")
    if not image_file or not image_file.filename:
        return view_admin.view_admin(app).frames_html(error_msg="Please upload an image.")
    result = admin_frame_proc.admin_frame_proc(app).add_frame(
        name, image_file, qr_x, qr_y, qr_w, qr_h, app.root_path
    )
    if not result.get("ok"):
        return view_admin.view_admin(app).frames_html(error_msg=result.get("error", "Save failed."))
    return view_admin.view_admin(app).frames_html(msg="Frame saved successfully.")

@app.route("/admin/frames/delete/<frame_id>", methods=["POST"])
def admin_frames_delete(frame_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    admin_frame_proc.admin_frame_proc(app).delete_frame(frame_id)
    return redirect(url_for("admin_frames"))


@app.route("/admin/storage")
def admin_storage():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_adm
    from pytavia_core import database as _db_adm, config as _cfg_adm
    _atp = _atp_adm()
    assets = _atp.get_soft_deleted_assets(limit=2000)
    total_size = sum(a.get("file_size", 0) for a in assets)
    # Attach user email to each asset for display
    _db_adm_conn = _db_adm.get_db_conn(_cfg_adm.mainDB)
    user_ids = list({a["fk_user_id"] for a in assets if a.get("fk_user_id")})
    user_map = {}
    for u in _db_adm_conn.db_user.find({"fk_user_id": {"$in": user_ids}}, {"fk_user_id": 1, "email": 1, "_id": 0}):
        user_map[u["fk_user_id"]] = u.get("email", u["fk_user_id"])
    for a in assets:
        a["user_email"] = user_map.get(a.get("fk_user_id", ""), a.get("fk_user_id", "—"))
    from pytavia_modules.user.user_storage_proc import _fmt_size
    return render_template(
        "admin/storage.html",
        assets=assets,
        total_count=len(assets),
        total_size_fmt=_fmt_size(total_size),
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )


@app.route("/admin/storage/hard_delete", methods=["POST"])
def admin_storage_hard_delete():
    """Bulk hard-delete selected soft-deleted assets from Cloudflare R2."""
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    import json as _json_adm
    data = request.get_json(force=True) or {}
    asset_ids = data.get("asset_ids", "all")  # list of asset_id strings, or "all"
    from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_hd
    from pytavia_modules.storage import r2_storage_proc as _r2_mod_hd
    _atp = _atp_hd()
    # Fetch the target assets
    if asset_ids == "all":
        assets = _atp.get_soft_deleted_assets(limit=5000)
    else:
        if not isinstance(asset_ids, list) or not asset_ids:
            return jsonify({"ok": False, "error": "No assets selected"}), 400
        from pytavia_core import database as _db_hd, config as _cfg_hd
        assets = list(_db_hd.get_db_conn(_cfg_hd.mainDB).db_qr_assets.find(
            {"asset_id": {"$in": asset_ids}, "status": "SOFT_DELETED"},
            {"_id": 0},
        ))
    if not assets:
        return jsonify({"ok": True, "deleted": 0, "freed_bytes": 0, "freed_fmt": "0 B"})
    # Batch delete from R2
    r2_keys = [a["r2_key"] for a in assets if a.get("r2_key")]
    _r2 = _r2_mod_hd.r2_storage_proc()
    deleted_r2 = _r2.delete_keys_batch(r2_keys)
    # Mark all as HARD_DELETED in MongoDB
    ids_to_mark = [a["asset_id"] for a in assets if a.get("asset_id")]
    _atp.mark_hard_deleted_batch(ids_to_mark)
    freed_bytes = sum(a.get("file_size", 0) for a in assets)
    from pytavia_modules.user.user_storage_proc import _fmt_size
    return jsonify({
        "ok": True,
        "deleted": len(ids_to_mark),
        "deleted_r2": deleted_r2,
        "freed_bytes": freed_bytes,
        "freed_fmt": _fmt_size(freed_bytes),
    })


@app.route("/api/frames/default")
def api_frames_default():
    """Public API: returns all active admin default frames as JSON."""
    frames = admin_frame_proc.admin_frame_proc(app).get_all_frames()
    result = []
    for f in frames:
        result.append({
            "frame_id" : f.get("frame_id"),
            "name"     : f.get("name"),
            "image_url": f.get("image_url"),
            "qr_x"     : f.get("qr_x"),
            "qr_y"     : f.get("qr_y"),
            "qr_w"     : f.get("qr_w"),
            "qr_h"     : f.get("qr_h"),
        })
    return jsonify(result)

@app.route("/api/frames/svg-standard")
def api_frames_svg_standard():
    """Public API: returns SVG standard frames with QR-area coords extracted from svg-qr-frame.json."""
    import os, re as _re, json as _json
    json_path = os.path.join(os.path.dirname(__file__), "static", "json_file", "svg-qr-frame.json")
    try:
        with open(json_path, "r", encoding="utf-8") as _f:
            raw_frames = _json.load(_f).get("frames", [])
    except Exception:
        return jsonify([])
    result = []
    for fr in raw_frames:
        if fr.get("id") == "frame0":
            continue
        svg = fr.get("svg", "")
        vb = _re.search(r'viewBox=["\']([^"\']+)["\']', svg)
        if not vb:
            continue
        vb_vals = [float(x) for x in vb.group(1).split()]
        vW, vH = vb_vals[2], vb_vals[3]
        # Find the QR placeholder rect (fill: rgb(229,231,239) or #e5e7ef)
        qr_rect = _re.search(
            r'<rect([^>]*)(?:fill=["\']#e5e7ef["\']|style=["\'][^"\']*rgb\(229[^)]+\)[^"\']*["\'])([^>]*)>',
            svg, _re.I
        )
        if not qr_rect:
            continue
        full = qr_rect.group(0)
        x_m = _re.search(r'\bx=["\']?([0-9.]+)', full)
        y_m = _re.search(r'\by=["\']?([0-9.]+)', full)
        w_m = _re.search(r'\bwidth=["\']?([0-9.]+)', full)
        h_m = _re.search(r'\bheight=["\']?([0-9.]+)', full)
        if not all([x_m, y_m, w_m, h_m]):
            continue
        result.append({
            "id"   : fr["id"],
            "name" : fr["name"],
            "svg"  : svg,
            "qr_x" : round(float(x_m.group(1)) / vW, 4),
            "qr_y" : round(float(y_m.group(1)) / vH, 4),
            "qr_w" : round(float(w_m.group(1)) / vW, 4),
            "qr_h" : round(float(h_m.group(1)) / vH, 4),
            "vW"   : vW,
            "vH"   : vH,
        })
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

@app.route("/api/proxy-image")
def api_proxy_image():
    """Serve an R2 image via boto3 for canvas CORS use. Supports ?download=1&name=file.png."""
    import re, os
    from pytavia_modules.storage import r2_storage_proc as _r2_mod
    url = request.args.get("url", "").strip()
    allowed_base = config.R2_PUBLIC_BASE_URL.rstrip("/")
    if not url.startswith(allowed_base + "/"):
        return "Forbidden", 403
    key = url[len(allowed_base) + 1:].split("?")[0]
    if not key:
        return "Bad Request", 400
    try:
        r2 = _r2_mod.r2_storage_proc()
        obj = r2._client.get_object(Bucket=r2._bucket, Key=key)
        data = obj["Body"].read()
        content_type = obj.get("ContentType", "image/png")
        resp = Response(data, content_type=content_type)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "public, max-age=3600"
        if request.args.get("download"):
            fname = request.args.get("name", "") or os.path.basename(key) or "image.png"
            fname = re.sub(r'[^\w\-. ]', '_', fname)
            resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp
    except Exception:
        app.logger.debug("api_proxy_image failed", exc_info=True)
        return "Could not fetch image", 502

@app.route("/api/qr/download/<qrcard_id>")
def api_qr_download(qrcard_id):
    """Download the composite QR image for a QR card directly via R2 boto3."""
    if "fk_user_id" not in session:
        return "Unauthorized", 401
    import re, os, io
    from pytavia_core import database as _db_mod, config as _cfg
    from pytavia_modules.storage import r2_storage_proc as _r2_mod
    try:
        fk_user_id = session["fk_user_id"]
        _db  = _db_mod.get_db_conn(_cfg.mainDB)
        doc  = _db.db_qrcard.find_one(
            {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id},
            {"qr_composite_url": 1, "qr_image_url": 1, "name": 1, "_id": 0},
        )
        if not doc:
            return "Not found", 404
        image_url = doc.get("qr_composite_url") or doc.get("qr_image_url")
        if not image_url:
            return "Not found", 404
        allowed_base  = _cfg.R2_PUBLIC_BASE_URL.rstrip("/")
        if not image_url.startswith(allowed_base + "/"):
            return "Forbidden", 403
        key = image_url[len(allowed_base) + 1:].split("?")[0]
        r2  = _r2_mod.r2_storage_proc()
        obj = r2._client.get_object(Bucket=r2._bucket, Key=key)
        data = obj["Body"].read()
        fname = re.sub(r'[^\w\-. ]', '-', doc.get("name", "qr-code")) + ".png"
        resp = Response(data, content_type="image/png")
        resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception:
        app.logger.debug("api_qr_download failed", exc_info=True)
        return "Download failed", 500

@app.route("/api/qr/preview/<qrcard_id>")
def api_qr_preview(qrcard_id):
    """Serve composite QR image inline (for scan modal preview) — always fresh, no browser cache."""
    if "fk_user_id" not in session:
        return "Unauthorized", 401
    import re, io
    from pytavia_core import database as _db_mod, config as _cfg
    from pytavia_modules.storage import r2_storage_proc as _r2_mod
    try:
        fk_user_id = session["fk_user_id"]
        _db  = _db_mod.get_db_conn(_cfg.mainDB)
        doc  = _db.db_qrcard.find_one(
            {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id},
            {"qr_composite_url": 1, "qr_image_url": 1, "_id": 0},
        )
        if not doc:
            return "Not found", 404
        image_url = doc.get("qr_composite_url") or doc.get("qr_image_url")
        if not image_url:
            return "Not found", 404
        allowed_base  = _cfg.R2_PUBLIC_BASE_URL.rstrip("/")
        if not image_url.startswith(allowed_base + "/"):
            return "Forbidden", 403
        key = image_url[len(allowed_base) + 1:].split("?")[0]
        r2  = _r2_mod.r2_storage_proc()
        obj = r2._client.get_object(Bucket=r2._bucket, Key=key)
        data = obj["Body"].read()
        resp = Response(data, content_type="image/png")
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception:
        app.logger.debug("api_qr_preview failed", exc_info=True)
        return "Preview failed", 500


@app.route("/api/qr/composite-url/<qrcard_id>")
def api_qr_composite_url(qrcard_id):
    """Return the stored qr_composite_url. If missing but frame_id is set, generate on demand."""
    if "fk_user_id" not in session:
        return jsonify({"url": ""}), 401
    try:
        from pytavia_core import database as _db_mod, config as _cfg
        _db = _db_mod.get_db_conn(_cfg.mainDB)
        fk_user_id = session["fk_user_id"]
        doc = _db.db_qrcard.find_one(
            {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id},
            {"qr_composite_url": 1, "frame_id": 1, "qr_type": 1, "short_code": 1, "url_content": 1, "_id": 0},
        )
        if not doc:
            return jsonify({"url": ""})
        composite_url = doc.get("qr_composite_url", "")
        if not composite_url:
            frame_id = doc.get("frame_id", "")
            if frame_id:
                # Construct qr_encode_url from qr_type + short_code
                qr_type   = doc.get("qr_type", "")
                short_code = doc.get("short_code", "")
                _static_types = {"web-static", "wa-static", "email-static", "vcard-static", "text"}
                if qr_type in _static_types:
                    qr_encode_url = doc.get("url_content", "")
                elif short_code and qr_type:
                    qr_encode_url = _cfg.G_BASE_URL.rstrip("/") + "/" + qr_type + "/" + short_code
                else:
                    qr_encode_url = ""
                if qr_encode_url:
                    _save_qr_composite(app, fk_user_id, qrcard_id, qr_encode_url, frame_id)
                    # Re-fetch the URL that was just saved
                    updated = _db.db_qrcard.find_one(
                        {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id},
                        {"qr_composite_url": 1, "_id": 0},
                    )
                    composite_url = (updated or {}).get("qr_composite_url", "")
        return jsonify({"url": composite_url})
    except Exception:
        return jsonify({"url": ""}), 500

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


@app.route("/links/<short_code>")
def qr_links_redirect(short_code):
    """Public endpoint for Links QR short URLs."""
    from pytavia_modules.qr.qr_public_links_visual_proc import qr_public_links_visual_proc
    return qr_public_links_visual_proc(app).handle(short_code)


@app.route("/sosmed/<short_code>")
def qr_sosmed_redirect(short_code):
    """Public endpoint for Sosmed QR short URLs."""
    from pytavia_modules.qr.qr_public_sosmed_visual_proc import qr_public_sosmed_visual_proc
    return qr_public_sosmed_visual_proc(app).handle(short_code)


@app.route("/allinone/<short_code>")
def qr_allinone_redirect(short_code):
    """Public endpoint for All-in-One QR short URLs."""
    from pytavia_modules.qr.qr_public_allinone_visual_proc import qr_public_allinone_visual_proc
    return qr_public_allinone_visual_proc(app).handle(short_code)


@app.route("/pdf/<short_code>")
def qr_pdf_redirect(short_code):
    """Public endpoint for PDF short URLs."""
    from pytavia_modules.qr.qr_public_pdf_visual_proc import qr_public_pdf_visual_proc
    return qr_public_pdf_visual_proc(app).handle(short_code)

@app.route("/images/<short_code>")
def qr_images_redirect(short_code):
    """Public endpoint for image-gallery short URLs."""
    from pytavia_core import database as _db_img, config as _cfg_img
    _mgd = _db_img.get_db_conn(_cfg_img.mainDB)
    qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "images", "status": "ACTIVE"})
    if not qrcard:
        abort(404)
    # Merge images-specific doc
    qrcard = _merge_images_into_qrcard(_mgd, qrcard.get("fk_user_id"), qrcard["qrcard_id"], qrcard)
    # Bump scan count
    _mgd.db_qrcard.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    _mgd.db_qrcard_images.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    return render_template("user/public_images.html", qrcard=qrcard)


@app.route("/video/<short_code>")
def qr_video_redirect(short_code):
    """Public endpoint for video-gallery short URLs."""
    from pytavia_core import database as _db_vid, config as _cfg_vid
    _mgd = _db_vid.get_db_conn(_cfg_vid.mainDB)
    qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "video", "status": "ACTIVE"})
    if not qrcard:
        abort(404)
    qrcard = _merge_video_into_qrcard(_mgd, qrcard.get("fk_user_id"), qrcard["qrcard_id"], qrcard)
    _mgd.db_qrcard.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    _mgd.db_qrcard_video.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    return render_template("user/public_video.html", qrcard=qrcard)


@app.route("/special/<short_code>")
def qr_special_redirect(short_code):
    """Public endpoint for special-page short URLs."""
    from pytavia_core import database as _db_sp, config as _cfg_sp
    _mgd = _db_sp.get_db_conn(_cfg_sp.mainDB)
    qrcard = _mgd.db_qrcard_special.find_one({"short_code": short_code, "status": "ACTIVE"})
    if not qrcard:
        qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "special", "status": "ACTIVE"})
    if not qrcard:
        abort(404)
    # Bump scan count
    _mgd.db_qrcard.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    _mgd.db_qrcard_special.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    # special_sections is stored as a JSON string; parse it back to a list
    import json as _json_sp
    raw_sections = qrcard.get("special_sections", "[]")
    try:
        sections = _json_sp.loads(raw_sections) if isinstance(raw_sections, str) else (raw_sections or [])
    except Exception:
        sections = []
    return render_template("user/public_special.html", qrcard=qrcard, sections=sections)


@app.route("/qr/new")
def user_new_qr():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).new_qr_html()

def _set_qrcard_deleted(mgdDB, fk_user_id, qrcard_id):
    """Mark one qrcard as DELETED in db_qrcard, db_qr_index, and type-specific collections.
    Returns dict with qr_name and qr_type for activity logging."""
    q = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    # Look up name/type before deleting
    idx = mgdDB.db_qr_index.find_one(q) or {}
    qr_name = idx.get("name", "")
    qr_type = idx.get("qr_type", "")
    mgdDB.db_qrcard.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qr_index.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qrcard_pdf.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qrcard_images.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qrcard_video.update_one(q, {"$set": {"status": "DELETED"}})
    mgdDB.db_qrcard_special.update_one(q, {"$set": {"status": "DELETED"}})
    # Soft-delete tracked assets — actual R2 deletion is deferred to admin bulk cleanup
    from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_del
    _atp_del().soft_delete_qr(qrcard_id)
    return {"qr_name": qr_name, "qr_type": qr_type}


def _delete_r2_assets_for_qr(qrcard_id, qr_type):
    """Delete all R2 objects under the QR's folder prefix.
    Returns dict {freed_bytes, deleted_count}. Silent on error."""
    try:
        from pytavia_modules.user.user_storage_proc import _QR_TYPE_PREFIX
        from storage import r2_storage_proc as _r2_mod
        folder = _QR_TYPE_PREFIX.get(qr_type, qr_type)
        if folder and qrcard_id:
            _r2 = _r2_mod.r2_storage_proc()
            objs = _r2.list_prefix(f"{folder}/{qrcard_id}/")
            freed_bytes   = sum(o["size"] for o in objs)
            deleted_count = len(objs)
            _r2.delete_prefix(f"{folder}/{qrcard_id}/")
            return {"freed_bytes": freed_bytes, "deleted_count": deleted_count}
    except Exception:
        pass
    return {"freed_bytes": 0, "deleted_count": 0}


@app.route("/api/qr/size/<qrcard_id>")
def api_qr_size(qrcard_id):
    """Return storage size for one QR card — reads from db_qr_assets (no R2 call).
    Falls back to R2 listing for legacy QRs with no tracked assets yet."""
    if "fk_user_id" not in session:
        return jsonify({"ok": False}), 401
    try:
        from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp
        result = _atp().get_qr_size(qrcard_id)
        if result["bytes"] > 0:
            return jsonify({"ok": True, **result})
        # Fallback: legacy QR not yet tracked — list R2 once
        from pytavia_core import database as _db_sz, config as _cfg_sz
        from pytavia_modules.user.user_storage_proc import _QR_TYPE_PREFIX, _fmt_size
        from storage import r2_storage_proc as _r2_mod
        _mgd = _db_sz.get_db_conn(_cfg_sz.mainDB)
        idx = _mgd.db_qr_index.find_one({"qrcard_id": qrcard_id, "fk_user_id": session["fk_user_id"]}) or {}
        folder = _QR_TYPE_PREFIX.get(idx.get("qr_type", ""), idx.get("qr_type", ""))
        total, count = 0, 0
        if folder:
            objs  = _r2_mod.r2_storage_proc().list_prefix(f"{folder}/{qrcard_id}/")
            total = sum(o["size"] for o in objs)
            count = len(objs)
        return jsonify({"ok": True, "bytes": total, "files": count, "size_fmt": _fmt_size(total)})
    except Exception:
        return jsonify({"ok": True, "bytes": 0, "files": 0, "size_fmt": "0 B"})


@app.route("/qr/delete/<qrcard_id>", methods=["POST"])
def qr_delete(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_del, config as _cfg_del
    from pytavia_modules.user import user_activity_proc as _uap_del
    _mgd_del = _db_del.get_db_conn(_cfg_del.mainDB)
    fk_user_id = session.get("fk_user_id")
    info = _set_qrcard_deleted(_mgd_del, fk_user_id, qrcard_id)
    _uap_del.user_activity_proc(app).log(
        fk_user_id=fk_user_id, action="DELETE_QR",
        qrcard_id=qrcard_id, qr_name=info["qr_name"],
        qr_type=info["qr_type"], source="my_qr_codes",
        detail={"note": "soft_deleted_assets_pending_r2_cleanup"},
    )
    return redirect(url_for("user_qr_list") + "?deleted=1")


@app.route("/qr/delete/bulk", methods=["POST"])
def qr_delete_bulk():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    qrcard_ids = request.form.getlist("qrcard_ids")
    if not qrcard_ids:
        return redirect(url_for("user_qr_list"))
    from pytavia_core import database as _db_bulk
    from pytavia_core import config as _cfg_bulk
    from pytavia_modules.user import user_activity_proc as _uap_bulk
    _mgd_bulk = _db_bulk.get_db_conn(_cfg_bulk.mainDB)
    fk_user_id = session.get("fk_user_id")
    for qrcard_id in qrcard_ids:
        info = _set_qrcard_deleted(_mgd_bulk, fk_user_id, qrcard_id)
        _uap_bulk.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="DELETE_QR",
            qrcard_id=qrcard_id, qr_name=info["qr_name"],
            qr_type=info["qr_type"], source="bulk",
            detail={"note": "soft_deleted_assets_pending_r2_cleanup", "bulk_total_qrs": len(qrcard_ids)},
        )
    return redirect(url_for("user_qr_list") + "?deleted=" + str(len(qrcard_ids)))
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
    _frame_id_pdf = request.form.get("frame_id", "")
    _fk_pdf = session.get("fk_user_id")
    # Activate DRAFT if needed before update (so complete_pdf_update can find the record)
    _enc_url_pdf = _activate_draft_qrcard(_fk_pdf, qrcard_id, "db_qrcard_pdf", "/pdf/")
    result = proc.complete_pdf_update(request, session, qrcard_id, app.root_path)
    if not result.get("success"):
        qrcard = proc.get_qrcard(_fk_pdf, qrcard_id)
        if qrcard:
            return view_update_pdf.view_update_pdf(app).update_qr_design_html(
                qrcard=qrcard, error_msg=result.get("error_msg", "Save failed.")
            )
        return redirect(url_for("user_qr_list"))
    _update_frame_id(_fk_pdf, qrcard_id, _frame_id_pdf)
    _save_custom_qr_image(_fk_pdf, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, _fk_pdf, qrcard_id, _enc_url_pdf, _frame_id_pdf)
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
    _frame_id_web = request.form.get("frame_id", "")
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_web)
    _enc_url_web = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_web", "/web/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_web, _frame_id_web)
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

    # Handle gallery image uploads
    gallery_files = request.files.getlist("ecard_gallery_images[]")
    if gallery_files and any(f and f.filename for f in gallery_files):
        import os, uuid as _uuid
        from pytavia_modules.storage import r2_storage_proc as _r2m
        r2 = _r2m.r2_storage_proc()
        existing_doc = proc.mgdDB.db_qrcard_ecard.find_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"ecard_gallery_files": 1}) or {}
        saved_gallery = list(existing_doc.get("ecard_gallery_files") or [])
        for gfile in gallery_files:
            if not gfile or not gfile.filename:
                continue
            ext = os.path.splitext(gfile.filename)[1].lower() or ".jpg"
            safe_name = _uuid.uuid4().hex + ext
            try:
                data = gfile.read()
                file_url = r2.upload_bytes(data, f"ecard/{qrcard_id}/gallery/{safe_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": safe_name})
                saved_gallery.append({"url": file_url})
            except Exception:
                pass
        if saved_gallery:
            proc.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}})
            proc.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}}, upsert=True)

    _frame_id_ecard = request.form.get("frame_id", "")
    _clear_qr_draft(session, qrcard_id)
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_ecard)
    _enc_url_ecard = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_ecard", "/ecard/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_ecard, _frame_id_ecard)
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
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
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
            url_content = draft.get("url_content") or qrcard.get("url_content") or "QRkartu"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "QRkartu"
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
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
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
            url_content = draft.get("url_content") or qrcard.get("url_content") or "QRkartu"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "QRkartu"
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
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
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
        _r2 = r2_mod.r2_storage_proc()

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
                    welcome_url = _r2.upload_file(welcome_img, f"ecard/{qrcard_id}/welcome_{int(time.time())}{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    _mgd_ew = database.get_db_conn(config.mainDB)
                    _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif request.form.get("ecard_welcome_img_autocomplete_url", "").strip():
                welcome_url = request.form.get("ecard_welcome_img_autocomplete_url").strip()
                extra_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                _mgd_ew = database.get_db_conn(config.mainDB)
                _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
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
                    cover_url = _r2.upload_file(cover_img, f"ecard/{qrcard_id}/pdf_cover_img{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
                    for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            elif request.form.get("ecard_cover_img_autocomplete_url", "").strip():
                cover_url = request.form.get("ecard_cover_img_autocomplete_url").strip()
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    extra_data[f] = cover_url
                    qrcard[f] = cover_url
                database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            else:
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    if qrcard.get(f): extra_data[f] = qrcard[f]

        # Gallery images update from existing + uploads + autocomplete assets
        existing_gallery = request.form.getlist("ecard_gallery_existing_urls[]")
        autocomplete_gallery = request.form.getlist("ecard_gallery_autocomplete_url[]")
        uploaded_gallery = request.files.getlist("ecard_gallery_images[]")
        touched_gallery = bool(existing_gallery or autocomplete_gallery) or any(
            g and getattr(g, "filename", "") for g in uploaded_gallery
        )
        if touched_gallery:
            gallery_items = []
            seen_urls = set()
            for url in existing_gallery:
                url = (url or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                gallery_items.append({"url": url})
            for gf in uploaded_gallery:
                if not gf or not gf.filename:
                    continue
                try:
                    ext = os.path.splitext(gf.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                    g_url = _r2.upload_file(
                        gf,
                        f"ecard/{qrcard_id}/gallery/{unique_name}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name},
                    )
                    if g_url and g_url not in seen_urls:
                        seen_urls.add(g_url)
                        gallery_items.append({"url": g_url})
                except Exception:
                    pass
            for ac_url in autocomplete_gallery:
                ac_url = (ac_url or "").strip()
                if not ac_url:
                    continue
                final_url = ac_url
                if ac_url.startswith("/static/"):
                    try:
                        ext = os.path.splitext(ac_url)[1] or ".jpg"
                        local_path = os.path.join(config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                        if os.path.isfile(local_path):
                            unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as fp:
                                final_url = _r2.upload_bytes(
                                    fp.read(),
                                    f"ecard/{qrcard_id}/gallery/{unique_name}",
                                    track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name},
                                )
                    except Exception:
                        final_url = ""
                if final_url and final_url not in seen_urls and (
                    final_url.startswith("http://") or final_url.startswith("https://")
                ):
                    seen_urls.add(final_url)
                    gallery_items.append({"url": final_url})
            extra_data["ecard_gallery_files"] = gallery_items
            _mgd_g = database.get_db_conn(config.mainDB)
            _mgd_g.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": gallery_items}})
            _mgd_g.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": gallery_items}})

        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), extra_data)
        qrcard.update(extra_data)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft:
            qrcard.update(draft)
            url_content = draft.get("url_content") or qrcard.get("url_content") or "QRkartu"
            qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        else:
            url_content = qrcard.get("url_content") or "QRkartu"
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
                _mgd.db_qrcard_pdf.update_one(
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
                _r2 = r2_mod.r2_storage_proc()
                _wts = int(time.time())
                welcome_url = _r2.upload_file(welcome_img, f"pdf/{qrcard_id}/welcome_{_wts}{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf"})
                ecard_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}},
                )
                _mgd.db_qrcard_pdf.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": welcome_url}},
                )
            else:
                # Check if user picked an existing asset URL instead of uploading
                _asset_welcome_url = request.form.get("welcome_img_autocomplete_url", "").strip()
                if _asset_welcome_url:
                    ecard_data["welcome_img_url"] = _asset_welcome_url
                    qrcard["welcome_img_url"] = _asset_welcome_url
                    from pytavia_core import database as _db_w, config as _cfg_w
                    _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                    _mgd.db_qrcard.update_one(
                        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                        {"$set": {"welcome_img_url": _asset_welcome_url}},
                    )
                    _mgd.db_qrcard_pdf.update_one(
                        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                        {"$set": {"welcome_img_url": _asset_welcome_url}},
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
                _r2 = r2_mod.r2_storage_proc()
                unique_cover_name = f"pdf_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                cover_url = _r2.upload_file(cover_img, f"pdf/{qrcard_id}/{unique_cover_name}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf"})
                for _f in _cover_img_fields:
                    ecard_data[_f] = cover_url
                    qrcard[_f] = cover_url
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {_f: cover_url for _f in _cover_img_fields}},
                )
                _mgd.db_qrcard_pdf.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {_f: cover_url for _f in _cover_img_fields}},
                )
        else:
            # Check if user picked an existing asset URL instead of uploading
            _asset_cover_url = request.form.get("pdf_t1_header_img_autocomplete_url", "").strip()
            if _asset_cover_url:
                cover_url = _asset_cover_url
                for _f in _cover_img_fields:
                    ecard_data[_f] = cover_url
                    qrcard[_f] = cover_url
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {_f: cover_url for _f in _cover_img_fields}},
                )
                _mgd.db_qrcard_pdf.update_one(
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
        # If user confirmed URL change, wipe saved custom QR so design page starts fresh
        if request.form.get("reset_qr_style") == "1":
            from pytavia_core import database as _db_rs, config as _cfg_rs
            _db_rs.get_db_conn(_cfg_rs.mainDB).db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": {"qr_image_url": "", "qr_composite_url": "",
                            "qr_dot_style": "", "qr_corner_style": "",
                            "qr_dot_color": "", "qr_bg_color": ""}},
            )
            _db_rs.get_db_conn(_cfg_rs.mainDB).db_qrcard_pdf.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": {"qr_image_url": "", "qr_composite_url": ""}},
            )
            qrcard.pop("qr_image_url", None)
            qrcard.pop("qr_composite_url", None)
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), ecard_data)
        qrcard.update(ecard_data)
        pdf_file_list = request.files.getlist("pdf_files")
        if pdf_file_list and any(f.filename for f in pdf_file_list):
            _r2_pdf = r2_mod.r2_storage_proc()
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
                    r2_key = f"pdf/{qrcard_id}/{safe_name}"
                    file_url = _r2_pdf.upload_file(f, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf", "file_name": original_name})
                    file_entry = {"name": original_name, "url": file_url}
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
        return redirect(url_for("qr_update_design_pdf", qrcard_id=qrcard_id))
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
        # If user confirmed URL change, wipe saved custom QR so design page starts fresh
        if request.form.get("reset_qr_style") == "1":
            database.get_db_conn(_cfg.mainDB).db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": {"qr_image_url": "", "qr_composite_url": "",
                            "qr_dot_style": "", "qr_corner_style": "",
                            "qr_dot_color": "", "qr_bg_color": ""}},
            )
            qrcard.pop("qr_image_url", None)
            qrcard.pop("qr_composite_url", None)
        _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, None)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
        qrcard["short_code"] = short_code or qrcard.get("short_code")
        return redirect(url_for("qr_update_design_web", qrcard_id=qrcard_id))
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


def _merge_web_static_qrcard_with_base(fk_user_id, qrcard_id, detail_doc):
    """db_qrcard holds qr_image_url, qr_composite_url, frame_id, and style fields; db_qrcard_web_static holds URL/name detail."""
    if not detail_doc:
        return None
    mgd = database.get_db_conn(config.mainDB)
    base = mgd.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    out = {k: v for k, v in (base or {}).items() if k != "_id"}
    for key, value in detail_doc.items():
        if key != "_id":
            out[key] = value
    return out


def _merge_text_qrcard_with_base(fk_user_id, qrcard_id, detail_doc):
    """Same as web-static: image/composite/frame live on db_qrcard; text payload on db_qrcard_text."""
    if not detail_doc:
        return None
    mgd = database.get_db_conn(config.mainDB)
    base = mgd.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    out = {k: v for k, v in (base or {}).items() if k != "_id"}
    for key, value in detail_doc.items():
        if key != "_id":
            out[key] = value
    return out


def _merge_wa_static_qrcard_with_base(fk_user_id, qrcard_id, detail_doc):
    """db_qrcard holds qr_image_url / qr_composite_url / styles; db_qrcard_wa_static holds WA fields."""
    if not detail_doc:
        return None
    mgd = database.get_db_conn(config.mainDB)
    base = mgd.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    out = {k: v for k, v in (base or {}).items() if k != "_id"}
    for key, value in detail_doc.items():
        if key != "_id":
            out[key] = value
    return out


def _merge_email_static_qrcard_with_base(fk_user_id, qrcard_id, detail_doc):
    """db_qrcard holds image/composite/styles; db_qrcard_email_static holds mail fields."""
    if not detail_doc:
        return None
    mgd = database.get_db_conn(config.mainDB)
    base = mgd.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    out = {k: v for k, v in (base or {}).items() if k != "_id"}
    for key, value in detail_doc.items():
        if key != "_id":
            out[key] = value
    return out


def _merge_vcard_static_qrcard_with_base(fk_user_id, qrcard_id, detail_doc):
    """db_qrcard holds image/composite/styles; db_qrcard_vcard_static holds vCard fields."""
    if not detail_doc:
        return None
    mgd = database.get_db_conn(config.mainDB)
    base = mgd.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "status": "ACTIVE"}
    )
    out = {k: v for k, v in (base or {}).items() if k != "_id"}
    for key, value in detail_doc.items():
        if key != "_id":
            out[key] = value
    return out


def _merge_images_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Combine db_qrcard (authoritative base) with images-specific fields from db_qrcard_images."""
    if not qrcard:
        return qrcard
    images_doc = mgd_db.db_qrcard_images.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    )
    if not images_doc:
        from pytavia_core import database
        images_doc = database.get_record("db_qrcard_images")
        images_doc["qrcard_id"] = qrcard_id
        images_doc["fk_user_id"] = fk_user_id
        images_doc["name"] = qrcard.get("name", "")
        images_doc["url_content"] = qrcard.get("url_content", "")
        images_doc["short_code"] = qrcard.get("short_code", "")
        images_doc["status"] = qrcard.get("status", "ACTIVE")
        try:
            mgd_db.db_qrcard_images.insert_one(images_doc)
        except Exception:
            pass
    # Always start from db_qrcard so base fields (qr_image_url, qr_composite_url,
    # name, short_code, etc.) are authoritative. db_qrcard_images never stores these.
    base_doc = mgd_db.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    )
    out = {k: v for k, v in (base_doc or qrcard).items() if k != "_id"}
    # Overlay images-specific fields from db_qrcard_images (skip base fields)
    _BASE_KEYS = {"_id", "name", "url_content", "short_code", "status", "qrcard_id", "fk_user_id"}
    for key, value in images_doc.items():
        if key not in _BASE_KEYS:
            out[key] = value
    return out


def _merge_video_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Overlay db_qrcard_video document onto qrcard so edit pages get full Video fields."""
    if not qrcard:
        return qrcard
    video_doc = mgd_db.db_qrcard_video.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    )
    if not video_doc:
        from pytavia_core import database
        video_doc = database.get_record("db_qrcard_video")
        video_doc["qrcard_id"] = qrcard_id
        video_doc["fk_user_id"] = fk_user_id
        video_doc["name"] = qrcard.get("name", "")
        video_doc["url_content"] = qrcard.get("url_content", "")
        video_doc["short_code"] = qrcard.get("short_code", "")
        video_doc["status"] = qrcard.get("status", "ACTIVE")
        try:
            mgd_db.db_qrcard_video.insert_one(video_doc)
        except Exception:
            pass
    base_doc = mgd_db.db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}
    )
    out = {k: v for k, v in (base_doc or qrcard).items() if k != "_id"}
    _BASE_KEYS = {"_id", "name", "url_content", "short_code", "status", "qrcard_id", "fk_user_id"}
    for key, value in video_doc.items():
        if key not in _BASE_KEYS:
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
            draft["url_content"] = url_content or draft.get("url_content") or "QRkartu"
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
                url_content=url_content_display or "QRkartu",
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
        _r2 = r2_mod.r2_storage_proc()

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
                    welcome_url = _r2.upload_file(welcome_img, f"ecard/{qrcard_id}/welcome_{int(time.time())}{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    _mgd_ew = database.get_db_conn(config.mainDB)
                    _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif request.form.get("ecard_welcome_img_autocomplete_url", "").strip():
                welcome_url = request.form.get("ecard_welcome_img_autocomplete_url").strip()
                extra_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                _mgd_ew = database.get_db_conn(config.mainDB)
                _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
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
                    cover_url = _r2.upload_file(cover_img, f"ecard/{qrcard_id}/ecard_cover_img{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
                    for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            elif request.form.get("ecard_cover_img_autocomplete_url", "").strip():
                cover_url = request.form.get("ecard_cover_img_autocomplete_url").strip()
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    extra_data[f] = cover_url
                    qrcard[f] = cover_url
                database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
            else:
                for f in ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]:
                    if qrcard.get(f): extra_data[f] = qrcard[f]

        # Gallery images update from existing + uploads + autocomplete assets
        existing_gallery = request.form.getlist("ecard_gallery_existing_urls[]")
        autocomplete_gallery = request.form.getlist("ecard_gallery_autocomplete_url[]")
        uploaded_gallery = request.files.getlist("ecard_gallery_images[]")
        touched_gallery = bool(existing_gallery or autocomplete_gallery) or any(
            g and getattr(g, "filename", "") for g in uploaded_gallery
        )
        if touched_gallery:
            gallery_items = []
            seen_urls = set()
            for url in existing_gallery:
                url = (url or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                gallery_items.append({"url": url})
            for gf in uploaded_gallery:
                if not gf or not gf.filename:
                    continue
                try:
                    ext = os.path.splitext(gf.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                    g_url = _r2.upload_file(
                        gf,
                        f"ecard/{qrcard_id}/gallery/{unique_name}",
                        track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name},
                    )
                    if g_url and g_url not in seen_urls:
                        seen_urls.add(g_url)
                        gallery_items.append({"url": g_url})
                except Exception:
                    pass
            for ac_url in autocomplete_gallery:
                ac_url = (ac_url or "").strip()
                if not ac_url:
                    continue
                final_url = ac_url
                if ac_url.startswith("/static/"):
                    try:
                        ext = os.path.splitext(ac_url)[1] or ".jpg"
                        local_path = os.path.join(config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                        if os.path.isfile(local_path):
                            unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as fp:
                                final_url = _r2.upload_bytes(
                                    fp.read(),
                                    f"ecard/{qrcard_id}/gallery/{unique_name}",
                                    track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name},
                                )
                    except Exception:
                        final_url = ""
                if final_url and final_url not in seen_urls and (
                    final_url.startswith("http://") or final_url.startswith("https://")
                ):
                    seen_urls.add(final_url)
                    gallery_items.append({"url": final_url})
            extra_data["ecard_gallery_files"] = gallery_items
            _mgd_g = database.get_db_conn(config.mainDB)
            _mgd_g.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": gallery_items}})
            _mgd_g.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": gallery_items}})

        from pytavia_modules.qr import qr_ecard_proc
        proc = qr_ecard_proc.qr_ecard_proc(app)
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_ecard.view_update_ecard(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists. Please choose a unique name.", base_url=config.G_BASE_URL
            )
        # If user confirmed URL change, wipe saved custom QR so design page starts fresh
        if request.form.get("reset_qr_style") == "1":
            _unset_fields = {
                "qr_composite_url": "",
                "qr_image_url": "",
                "qr_dot_style": "",
                "qr_corner_style": "",
                "qr_dot_color": "",
                "qr_bg_color": "",
                "card_bg_color": "",
            }
            database.get_db_conn(config.mainDB).db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _unset_fields},
            )
            database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": {"qr_composite_url": "", "qr_image_url": ""}},
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
        return redirect(url_for("qr_update_design_ecard", qrcard_id=qrcard_id))
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
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    pdf_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
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
        _r2 = r2_mod.r2_storage_proc()
        pdf_file_list = request.files.getlist("pdf_files")
        existing_tmp = session.get("pdf_tmp_files", [])
        existing_names = {x["name"] for x in existing_tmp}
        for f in pdf_file_list:
            if f and f.filename and f.filename.lower().endswith(".pdf"):
                safe_name = f.filename.replace(" ", "_")
                if f.filename not in existing_names:
                    _r2.upload_file(f, f"pdf/_tmp/{tmp_key}/{safe_name}")
                    existing_tmp.append({"name": f.filename, "safe_name": safe_name})
                    existing_names.add(f.filename)
        session["pdf_tmp_files"] = existing_tmp
        session["pdf_display_names"] = request.form.getlist("pdf_display_names")
        session["pdf_item_descs"] = request.form.getlist("pdf_item_descs")
        session["pdf_autocomplete_urls"] = request.form.getlist("pdf_autocomplete_urls")
        session["pdf_t1_header_img_autocomplete_url"] = request.form.get("pdf_t1_header_img_autocomplete_url", "")
        session.modified = True
        welcome_img = request.files.get("pdf_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _r2.upload_file(welcome_img, f"pdf/_tmp/{tmp_key}/welcome{ext}")
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
                unique_cover_name = f"pdf_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                _r2.upload_file(cover_img, f"pdf/_tmp/{tmp_key}/{unique_cover_name}")
                session["cover_img_tmp_key"] = tmp_key
                session["cover_img_tmp_name"] = unique_cover_name
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

@app.route("/qr/new/text")
@app.route("/qr/new/text/back", methods=["GET", "POST"])
def user_new_qr_text():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    text_content = ""
    qr_name = ""
    if request.method == "POST":
        text_content = request.form.get("text_content", "")
        qr_name = request.form.get("qr_name", "")
    return render_template(
        "/user/new_qr_content_text.html",
        qr_type="text",
        text_content=text_content,
        qr_name=qr_name,
        form_action="/qr/new/text/qr-design",
        back_url="/qr/new",
        step1_url="/qr/new",
    )

@app.route("/qr/new/text/qr-design", methods=["POST"])
def user_new_qr_design_text():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_text_proc
    proc = qr_text_proc.qr_text_proc(app)
    text_content = request.form.get("text_content", "")
    qr_name = request.form.get("qr_name", "Untitled QR")
    if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
        return render_template(
            "/user/new_qr_content_text.html",
            qr_type="text",
            error_msg="A QR card with this name already exists. Please choose a unique name.",
            text_content=text_content,
            qr_name=qr_name,
            form_action="/qr/new/text/qr-design",
            back_url="/qr/new",
            step1_url="/qr/new",
        )
    return render_template(
        "/user/new_qr_design_text.html",
        qr_type="text",
        text_content=text_content,
        qr_name=qr_name,
        form_action="/qr/save/text",
        step1_url="/qr/new",
    )

@app.route("/qr/save/text", methods=["POST"])
def qr_save_text():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_text_proc
    proc = qr_text_proc.qr_text_proc(app)
    text_content = request.form.get("text_content", "")
    qr_name = request.form.get("qr_name", "Untitled QR")
    result = proc.add_qrcard_text({
        "fk_user_id": session.get("fk_user_id"),
        "name": qr_name,
        "text_content": text_content,
    })
    if result.get("message_action") == "ADD_QRCARD_SUCCESS":
        _qid = result.get("message_data", {}).get("qrcard_id")
        _update_frame_id(session.get("fk_user_id"), _qid, request.form.get("frame_id", ""))
        _enc_url_s = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": _qid}, {"url_content": 1}) or {}).get("url_content", "")
        _save_custom_qr_image(session.get("fk_user_id"), _qid, request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), _qid, _enc_url_s, request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_t
        _uap_t.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=_qid or "", qr_name=qr_name, qr_type="text", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return render_template(
        "/user/new_qr_design_text.html",
        qr_type="text",
        text_content=text_content,
        qr_name=qr_name,
        form_action="/qr/save/text",
        error_msg=result.get("message_desc", "Save failed."),
        step1_url="/qr/new",
    )

@app.route("/qr/new/web-static")
@app.route("/qr/new/web-static/back", methods=["GET", "POST"])
def user_new_qr_web_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    url_content = ""
    qr_name = ""
    if request.method == "POST":
        url_content = request.form.get("url_content", "")
        qr_name = request.form.get("qr_name", "")
    return render_template(
        "/user/new_qr_content_web_static.html",
        qr_type="web-static",
        url_content=url_content,
        qr_name=qr_name,
        form_action="/qr/new/web-static/qr-design",
        back_url="/qr/new",
        step1_url="/qr/new",
    )

@app.route("/qr/new/web-static/qr-design", methods=["POST"])
def user_new_qr_design_web_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_web_static_proc
    proc = qr_web_static_proc.qr_web_static_proc(app)
    url_content = request.form.get("url_content", "")
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = request.form.get("qr_name", "Untitled QR")
    if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
        return render_template(
            "/user/new_qr_content_web_static.html",
            qr_type="web-static",
            error_msg="A QR card with this name already exists. Please choose a unique name.",
            url_content=url_content,
            qr_name=qr_name,
            form_action="/qr/new/web-static/qr-design",
            back_url="/qr/new",
            step1_url="/qr/new",
        )
    return render_template(
        "/user/new_qr_design_web_static.html",
        qr_type="web-static",
        url_content=url_content,
        qr_name=qr_name,
        qr_encode_url=url_content,
        form_action="/qr/save/web-static",
        step1_url="/qr/new",
    )

@app.route("/qr/save/web-static", methods=["POST"])
def qr_save_web_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_web_static_proc
    proc = qr_web_static_proc.qr_web_static_proc(app)
    url_content = request.form.get("url_content", "")
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = request.form.get("qr_name", "Untitled QR")
    result = proc.add_qrcard_static({
        "fk_user_id": session.get("fk_user_id"),
        "name": qr_name,
        "url_content": url_content,
    })
    if result.get("message_action") == "ADD_QRCARD_SUCCESS":
        _qid = result.get("message_data", {}).get("qrcard_id")
        _update_frame_id(session.get("fk_user_id"), _qid, request.form.get("frame_id", ""))
        _enc_url_s = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": _qid}, {"url_content": 1}) or {}).get("url_content", "")
        _save_custom_qr_image(session.get("fk_user_id"), _qid, request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), _qid, _enc_url_s, request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_ws
        _uap_ws.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=_qid or "", qr_name=qr_name, qr_type="web-static", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return render_template(
        "/user/new_qr_design_web_static.html",
        qr_type="web-static",
        url_content=url_content,
        qr_name=qr_name,
        qr_encode_url=url_content,
        form_action="/qr/save/web-static",
        error_msg=result.get("message_desc", "Save failed."),
        step1_url="/qr/new",
    )

@app.route("/qr/update/web-static/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_web_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_web_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_web_static_proc.qr_web_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    error_msg = None
    qr_name = qrcard.get("name", "")
    url_content = qrcard.get("url_content", "")
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        url_content = draft.get("url_content") or url_content
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
        else:
            _set_qr_draft(session, qrcard_id, url_content, qr_name, None, None)
            return redirect(url_for("qr_update_design_web_static", qrcard_id=qrcard_id))
    return render_template("/user/edit_qr_content_web_static.html",
        qrcard_id=qrcard_id, qr_name=qr_name,
        url_content=url_content.replace("https://", "").replace("http://", "") if url_content else "",
        error_msg=error_msg)


@app.route("/qr/update/web-static/qr-design/<qrcard_id>", methods=["GET"])
def qr_update_design_web_static(qrcard_id):
    """Step 3 (design) for editing web-static — separate URL so the address bar updates after Content → Next (POST-redirect-GET)."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_web_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_web_static_proc.qr_web_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_web_static_qrcard_with_base(fk_user_id, qrcard_id, qrcard)
    draft = _get_qr_draft(session, qrcard_id)
    qr_name = qrcard.get("name", "")
    url_content = qrcard.get("url_content", "")
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        url_content = draft.get("url_content") or url_content
    return render_template(
        "/user/edit_qr_design_web_static.html",
        qrcard_id=qrcard_id,
        qrcard=qrcard,
        qr_name=qr_name,
        url_content=url_content,
    )


@app.route("/qr/update/save/web-static/<qrcard_id>", methods=["POST"])
def qr_update_save_web_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_web_static_proc
    fk_user_id = session.get("fk_user_id")
    url_content = (request.form.get("url_content") or "").strip()
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    qr_web_static_proc.qr_web_static_proc(app).edit_qrcard_static({
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": qr_name, "url_content": url_content,
    })
    _update_frame_id(fk_user_id, qrcard_id, request.form.get("frame_id", ""))
    _enc_url_u = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id}, {"url_content": 1}) or {}).get("url_content", "")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_u, request.form.get("frame_id", ""))
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/update/text/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_text(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_text_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_text_proc.qr_text_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    error_msg = None
    qr_name = qrcard.get("name", "")
    text_content = qrcard.get("text_content", "")
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "text_content" in draft:
            text_content = draft["text_content"]
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        text_content = request.form.get("text_content", "")
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
        else:
            _set_qr_draft(
                session, qrcard_id, "", qr_name, None,
                extra_data={"text_content": text_content},
            )
            return redirect(url_for("qr_update_design_text", qrcard_id=qrcard_id))
    return render_template("/user/edit_qr_content_text.html",
        qrcard_id=qrcard_id, qr_name=qr_name, text_content=text_content, error_msg=error_msg)


@app.route("/qr/update/text/qr-design/<qrcard_id>", methods=["GET"])
def qr_update_design_text(qrcard_id):
    """Text QR design step — own URL so the address bar updates after Content → Next."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_text_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_text_proc.qr_text_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_text_qrcard_with_base(fk_user_id, qrcard_id, qrcard)
    draft = _get_qr_draft(session, qrcard_id)
    qr_name = qrcard.get("name", "")
    text_content = qrcard.get("text_content", "")
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "text_content" in draft:
            text_content = draft["text_content"]
    return render_template(
        "/user/edit_qr_design_text.html",
        qrcard_id=qrcard_id,
        qrcard=qrcard,
        qr_name=qr_name,
        text_content=text_content,
    )


@app.route("/qr/update/save/text/<qrcard_id>", methods=["POST"])
def qr_update_save_text(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_text_proc
    fk_user_id = session.get("fk_user_id")
    text_content = request.form.get("text_content", "")
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    qr_text_proc.qr_text_proc(app).edit_qrcard_text({
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": qr_name, "text_content": text_content,
    })
    _update_frame_id(fk_user_id, qrcard_id, request.form.get("frame_id", ""))
    _enc_url_u = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id}, {"url_content": 1}) or {}).get("url_content", "")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_u, request.form.get("frame_id", ""))
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/new/wa-static")
@app.route("/qr/new/wa-static/back", methods=["GET", "POST"])
def user_new_qr_wa_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    wa_phone = ""
    wa_message = ""
    qr_name = ""
    if request.method == "POST":
        wa_phone = request.form.get("wa_phone", "")
        wa_message = request.form.get("wa_message", "")
        qr_name = request.form.get("qr_name", "")
    return render_template(
        "/user/new_qr_content_wa_static.html",
        qr_type="wa-static",
        wa_phone=wa_phone,
        wa_message=wa_message,
        qr_name=qr_name,
        form_action="/qr/new/wa-static/qr-design",
        back_url="/qr/new",
        step1_url="/qr/new",
    )

@app.route("/qr/new/wa-static/qr-design", methods=["POST"])
def user_new_qr_design_wa_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_wa_static_proc
    wa_phone = request.form.get("wa_phone", "").strip()
    wa_message = request.form.get("wa_message", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    proc = qr_wa_static_proc.qr_wa_static_proc(app)
    if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
        return render_template(
            "/user/new_qr_content_wa_static.html",
            qr_type="wa-static",
            error_msg="A QR card with this name already exists. Please choose a unique name.",
            wa_phone=wa_phone,
            wa_message=wa_message,
            qr_name=qr_name,
            form_action="/qr/new/wa-static/qr-design",
            back_url="/qr/new",
            step1_url="/qr/new",
        )
    return render_template(
        "/user/new_qr_design_wa_static.html",
        qr_type="wa-static",
        wa_phone=wa_phone,
        wa_message=wa_message,
        qr_name=qr_name,
        form_action="/qr/save/wa-static",
        step1_url="/qr/new",
    )

@app.route("/qr/save/wa-static", methods=["POST"])
def qr_save_wa_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_wa_static_proc
    fk_user_id = session.get("fk_user_id")
    wa_phone = request.form.get("wa_phone", "").strip()
    wa_message = request.form.get("wa_message", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    proc = qr_wa_static_proc.qr_wa_static_proc(app)
    result = proc.add_qrcard_wa_static({
        "fk_user_id": fk_user_id,
        "name": qr_name,
        "wa_phone": wa_phone,
        "wa_message": wa_message,
    })
    if result.get("message_action") == "ADD_QRCARD_SUCCESS":
        _qid = result.get("message_data", {}).get("qrcard_id")
        _update_frame_id(fk_user_id, _qid, request.form.get("frame_id", ""))
        _enc_url_s = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": _qid}, {"url_content": 1}) or {}).get("url_content", "")
        _save_custom_qr_image(fk_user_id, _qid, request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, fk_user_id, _qid, _enc_url_s, request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_wa
        _uap_wa.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=_qid or "", qr_name=qr_name, qr_type="wa-static", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return render_template(
        "/user/new_qr_design_wa_static.html",
        qr_type="wa-static",
        wa_phone=wa_phone,
        wa_message=wa_message,
        qr_name=qr_name,
        form_action="/qr/save/wa-static",
        error_msg=result.get("message_desc", "Save failed."),
        step1_url="/qr/new",
    )

@app.route("/qr/update/wa-static/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_wa_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_wa_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_wa_static_proc.qr_wa_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    error_msg = None
    qr_name = qrcard.get("name", "")
    wa_phone = qrcard.get("wa_phone", "")
    wa_message = qrcard.get("wa_message", "")
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "wa_phone" in draft:
            wa_phone = draft["wa_phone"]
        if "wa_message" in draft:
            wa_message = draft["wa_message"]
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        wa_phone = request.form.get("wa_phone", "").strip()
        wa_message = request.form.get("wa_message", "").strip()
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
        else:
            _set_qr_draft(
                session, qrcard_id, "", qr_name, None,
                extra_data={"wa_phone": wa_phone, "wa_message": wa_message},
            )
            return redirect(url_for("qr_update_design_wa_static", qrcard_id=qrcard_id))
    return render_template("/user/edit_qr_content_wa_static.html",
        qrcard_id=qrcard_id, qr_name=qr_name,
        wa_phone=wa_phone, wa_message=wa_message, error_msg=error_msg)


@app.route("/qr/update/wa-static/qr-design/<qrcard_id>", methods=["GET"])
def qr_update_design_wa_static(qrcard_id):
    """WA static design step — own URL after Content → Next (POST-redirect-GET)."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_wa_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_wa_static_proc.qr_wa_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_wa_static_qrcard_with_base(fk_user_id, qrcard_id, qrcard)
    draft = _get_qr_draft(session, qrcard_id)
    qr_name = qrcard.get("name", "")
    wa_phone = qrcard.get("wa_phone", "")
    wa_message = qrcard.get("wa_message", "")
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "wa_phone" in draft:
            wa_phone = draft["wa_phone"]
        if "wa_message" in draft:
            wa_message = draft["wa_message"]
    return render_template(
        "/user/edit_qr_design_wa_static.html",
        qrcard_id=qrcard_id,
        qrcard=qrcard,
        qr_name=qr_name,
        wa_phone=wa_phone,
        wa_message=wa_message,
    )


@app.route("/qr/update/save/wa-static/<qrcard_id>", methods=["POST"])
def qr_update_save_wa_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_wa_static_proc
    fk_user_id = session.get("fk_user_id")
    wa_phone = request.form.get("wa_phone", "").strip()
    wa_message = request.form.get("wa_message", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    qr_wa_static_proc.qr_wa_static_proc(app).edit_qrcard_wa_static({
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": qr_name, "wa_phone": wa_phone, "wa_message": wa_message,
    })
    _update_frame_id(fk_user_id, qrcard_id, request.form.get("frame_id", ""))
    _enc_url_u = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id}, {"url_content": 1}) or {}).get("url_content", "")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_u, request.form.get("frame_id", ""))
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/new/vcard-static")
@app.route("/qr/new/vcard-static/back", methods=["GET", "POST"])
def user_new_qr_vcard_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    data = {}
    if request.method == "POST":
        for k in ["vcard_first_name","vcard_surname","vcard_company","vcard_title","vcard_email","vcard_website","vcard_phones_json","qr_name"]:
            data[k] = request.form.get(k, "")
    return render_template("/user/new_qr_content_vcard_static.html", qr_type="vcard-static",
        form_action="/qr/new/vcard-static/qr-design", back_url="/qr/new", step1_url="/qr/new", **data)

@app.route("/qr/new/vcard-static/qr-design", methods=["POST"])
def user_new_qr_design_vcard_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    import json as _json
    from pytavia_modules.qr import qr_vcard_static_proc
    def _vd(k): return request.form.get(k, "").strip()
    first_name = _vd("vcard_first_name")
    surname = _vd("vcard_surname")
    company = _vd("vcard_company")
    title = _vd("vcard_title")
    email = _vd("vcard_email")
    website = _vd("vcard_website")
    phones_json = request.form.get("vcard_phones_json", "[]")
    qr_name = (_vd("qr_name") or "Untitled QR")
    proc = qr_vcard_static_proc.qr_vcard_static_proc(app)
    if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
        return render_template("/user/new_qr_content_vcard_static.html", qr_type="vcard-static",
            error_msg="A QR card with this name already exists.",
            vcard_first_name=first_name, vcard_surname=surname, vcard_company=company,
            vcard_title=title, vcard_email=email, vcard_website=website,
            vcard_phones_json=phones_json, qr_name=qr_name,
            form_action="/qr/new/vcard-static/qr-design", back_url="/qr/new", step1_url="/qr/new")
    return render_template("/user/new_qr_design_vcard_static.html", qr_type="vcard-static",
        vcard_first_name=first_name, vcard_surname=surname, vcard_company=company,
        vcard_title=title, vcard_email=email, vcard_website=website,
        vcard_phones_json=phones_json, qr_name=qr_name,
        form_action="/qr/save/vcard-static", step1_url="/qr/new")

@app.route("/qr/save/vcard-static", methods=["POST"])
def qr_save_vcard_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    import json as _json
    from pytavia_modules.qr import qr_vcard_static_proc
    def _vd(k): return request.form.get(k, "").strip()
    phones = []
    try: phones = _json.loads(request.form.get("vcard_phones_json", "[]"))
    except Exception: pass
    result = qr_vcard_static_proc.qr_vcard_static_proc(app).add_qrcard_vcard_static({
        "fk_user_id": session.get("fk_user_id"),
        "name": _vd("qr_name") or "Untitled QR",
        "vcard_first_name": _vd("vcard_first_name"),
        "vcard_surname": _vd("vcard_surname"),
        "vcard_company": _vd("vcard_company"),
        "vcard_title": _vd("vcard_title"),
        "vcard_phones": phones,
        "vcard_email": _vd("vcard_email"),
        "vcard_website": _vd("vcard_website"),
    })
    if result.get("message_action") == "ADD_QRCARD_SUCCESS":
        _qid = result.get("message_data", {}).get("qrcard_id")
        _update_frame_id(session.get("fk_user_id"), _qid, request.form.get("frame_id", ""))
        _enc_url_s = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": _qid}, {"url_content": 1}) or {}).get("url_content", "")
        _save_custom_qr_image(session.get("fk_user_id"), _qid, request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), _qid, _enc_url_s, request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_vc
        _uap_vc.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=_qid or "", qr_name=_vd("qr_name") or "Untitled QR",
            qr_type="vcard-static", source="create",
        )
        return redirect(url_for("user_qr_list"))
    phones_json = request.form.get("vcard_phones_json", "[]")
    return render_template("/user/new_qr_design_vcard_static.html", qr_type="vcard-static",
        vcard_first_name=_vd("vcard_first_name"), vcard_surname=_vd("vcard_surname"),
        vcard_company=_vd("vcard_company"), vcard_title=_vd("vcard_title"),
        vcard_email=_vd("vcard_email"), vcard_website=_vd("vcard_website"),
        vcard_phones_json=phones_json, qr_name=_vd("qr_name"),
        form_action="/qr/save/vcard-static",
        error_msg=result.get("message_desc", "Save failed."), step1_url="/qr/new")

@app.route("/qr/update/vcard-static/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_vcard_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    import json as _json
    from pytavia_modules.qr import qr_vcard_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_vcard_static_proc.qr_vcard_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    error_msg = None
    qr_name = qrcard.get("name", "")
    first_name = qrcard.get("vcard_first_name", "")
    surname = qrcard.get("vcard_surname", "")
    company = qrcard.get("vcard_company", "")
    title = qrcard.get("vcard_title", "")
    phones = qrcard.get("vcard_phones", [])
    email = qrcard.get("vcard_email", "")
    website = qrcard.get("vcard_website", "")
    phones_json = _json.dumps(phones)
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "vcard_first_name" in draft:
            first_name = draft["vcard_first_name"]
        if "vcard_surname" in draft:
            surname = draft["vcard_surname"]
        if "vcard_company" in draft:
            company = draft["vcard_company"]
        if "vcard_title" in draft:
            title = draft["vcard_title"]
        if "vcard_email" in draft:
            email = draft["vcard_email"]
        if "vcard_website" in draft:
            website = draft["vcard_website"]
        if "vcard_phones_json" in draft:
            phones_json = draft["vcard_phones_json"]
            try:
                phones = _json.loads(phones_json)
            except Exception:
                phones = []
    if request.method == "POST":
        def _vd(k): return request.form.get(k, "").strip()
        qr_name = _vd("qr_name") or "Untitled QR"
        first_name = _vd("vcard_first_name")
        surname = _vd("vcard_surname")
        company = _vd("vcard_company")
        title = _vd("vcard_title")
        email = _vd("vcard_email")
        website = _vd("vcard_website")
        phones_json = request.form.get("vcard_phones_json", "[]")
        phones = []
        try:
            phones = _json.loads(phones_json)
        except Exception:
            pass
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            error_msg = "A QR card with this name already exists."
        else:
            _set_qr_draft(
                session, qrcard_id, "", qr_name, None,
                extra_data={
                    "vcard_first_name": first_name,
                    "vcard_surname": surname,
                    "vcard_company": company,
                    "vcard_title": title,
                    "vcard_email": email,
                    "vcard_website": website,
                    "vcard_phones_json": phones_json,
                },
            )
            return redirect(url_for("qr_update_design_vcard_static", qrcard_id=qrcard_id))
    return render_template("/user/edit_qr_content_vcard_static.html",
        qrcard_id=qrcard_id, qr_name=qr_name, vcard_first_name=first_name,
        vcard_surname=surname, vcard_company=company, vcard_title=title,
        vcard_email=email, vcard_website=website,
        vcard_phones_json=phones_json, error_msg=error_msg)


@app.route("/qr/update/vcard-static/qr-design/<qrcard_id>", methods=["GET"])
def qr_update_design_vcard_static(qrcard_id):
    """vCard static design step — own URL after Content → Next."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    import json as _json
    from pytavia_modules.qr import qr_vcard_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_vcard_static_proc.qr_vcard_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_vcard_static_qrcard_with_base(fk_user_id, qrcard_id, qrcard)
    draft = _get_qr_draft(session, qrcard_id)
    qr_name = qrcard.get("name", "")
    first_name = qrcard.get("vcard_first_name", "")
    surname = qrcard.get("vcard_surname", "")
    company = qrcard.get("vcard_company", "")
    title = qrcard.get("vcard_title", "")
    email = qrcard.get("vcard_email", "")
    website = qrcard.get("vcard_website", "")
    phones = qrcard.get("vcard_phones", [])
    phones_json = _json.dumps(phones)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "vcard_first_name" in draft:
            first_name = draft["vcard_first_name"]
        if "vcard_surname" in draft:
            surname = draft["vcard_surname"]
        if "vcard_company" in draft:
            company = draft["vcard_company"]
        if "vcard_title" in draft:
            title = draft["vcard_title"]
        if "vcard_email" in draft:
            email = draft["vcard_email"]
        if "vcard_website" in draft:
            website = draft["vcard_website"]
        if "vcard_phones_json" in draft:
            phones_json = draft["vcard_phones_json"]
    return render_template(
        "/user/edit_qr_design_vcard_static.html",
        qrcard_id=qrcard_id,
        qrcard=qrcard,
        qr_name=qr_name,
        vcard_first_name=first_name,
        vcard_surname=surname,
        vcard_company=company,
        vcard_title=title,
        vcard_email=email,
        vcard_website=website,
        vcard_phones_json=phones_json,
    )


@app.route("/qr/update/save/vcard-static/<qrcard_id>", methods=["POST"])
def qr_update_save_vcard_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    import json as _json
    from pytavia_modules.qr import qr_vcard_static_proc
    def _vd(k): return request.form.get(k, "").strip()
    phones = []
    try: phones = _json.loads(request.form.get("vcard_phones_json", "[]"))
    except Exception: pass
    qr_vcard_static_proc.qr_vcard_static_proc(app).edit_qrcard_vcard_static({
        "fk_user_id": session.get("fk_user_id"), "qrcard_id": qrcard_id,
        "name": _vd("qr_name") or "Untitled QR",
        "vcard_first_name": _vd("vcard_first_name"),
        "vcard_surname": _vd("vcard_surname"),
        "vcard_company": _vd("vcard_company"),
        "vcard_title": _vd("vcard_title"),
        "vcard_phones": phones,
        "vcard_email": _vd("vcard_email"),
        "vcard_website": _vd("vcard_website"),
    })
    _update_frame_id(session.get("fk_user_id"), qrcard_id, request.form.get("frame_id", ""))
    _enc_url_u = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id}, {"url_content": 1}) or {}).get("url_content", "")
    _save_custom_qr_image(session.get("fk_user_id"), qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, session.get("fk_user_id"), qrcard_id, _enc_url_u, request.form.get("frame_id", ""))
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

@app.route("/qr/new/email-static")
@app.route("/qr/new/email-static/back", methods=["GET", "POST"])
def user_new_qr_email_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    email_address = ""
    email_subject = ""
    email_body = ""
    qr_name = ""
    if request.method == "POST":
        email_address = request.form.get("email_address", "")
        email_subject = request.form.get("email_subject", "")
        email_body = request.form.get("email_body", "")
        qr_name = request.form.get("qr_name", "")
    return render_template(
        "/user/new_qr_content_email_static.html",
        qr_type="email-static",
        email_address=email_address,
        email_subject=email_subject,
        email_body=email_body,
        qr_name=qr_name,
        form_action="/qr/new/email-static/qr-design",
        back_url="/qr/new",
        step1_url="/qr/new",
    )

@app.route("/qr/new/email-static/qr-design", methods=["POST"])
def user_new_qr_design_email_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_email_static_proc
    email_address = request.form.get("email_address", "").strip()
    email_subject = request.form.get("email_subject", "").strip()
    email_body = request.form.get("email_body", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    proc = qr_email_static_proc.qr_email_static_proc(app)
    if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
        return render_template(
            "/user/new_qr_content_email_static.html",
            qr_type="email-static",
            error_msg="A QR card with this name already exists. Please choose a unique name.",
            email_address=email_address,
            email_subject=email_subject,
            email_body=email_body,
            qr_name=qr_name,
            form_action="/qr/new/email-static/qr-design",
            back_url="/qr/new",
            step1_url="/qr/new",
        )
    return render_template(
        "/user/new_qr_design_email_static.html",
        qr_type="email-static",
        email_address=email_address,
        email_subject=email_subject,
        email_body=email_body,
        qr_name=qr_name,
        form_action="/qr/save/email-static",
        step1_url="/qr/new",
    )

@app.route("/qr/save/email-static", methods=["POST"])
def qr_save_email_static():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_email_static_proc
    fk_user_id = session.get("fk_user_id")
    email_address = request.form.get("email_address", "").strip()
    email_subject = request.form.get("email_subject", "").strip()
    email_body = request.form.get("email_body", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    proc = qr_email_static_proc.qr_email_static_proc(app)
    result = proc.add_qrcard_email_static({
        "fk_user_id": fk_user_id,
        "name": qr_name,
        "email_address": email_address,
        "email_subject": email_subject,
        "email_body": email_body,
    })
    if result.get("message_action") == "ADD_QRCARD_SUCCESS":
        _qid = result.get("message_data", {}).get("qrcard_id")
        _update_frame_id(fk_user_id, _qid, request.form.get("frame_id", ""))
        _enc_url_s = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": _qid}, {"url_content": 1}) or {}).get("url_content", "")
        _save_custom_qr_image(fk_user_id, _qid, request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, fk_user_id, _qid, _enc_url_s, request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_em
        _uap_em.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=_qid or "", qr_name=qr_name, qr_type="email-static", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return render_template(
        "/user/new_qr_design_email_static.html",
        qr_type="email-static",
        email_address=email_address,
        email_subject=email_subject,
        email_body=email_body,
        qr_name=qr_name,
        form_action="/qr/save/email-static",
        error_msg=result.get("message_desc", "Save failed."),
        step1_url="/qr/new",
    )

@app.route("/qr/update/email-static/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_email_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_email_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_email_static_proc.qr_email_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    error_msg = None
    qr_name = qrcard.get("name", "")
    email_address = qrcard.get("email_address", "")
    email_subject = qrcard.get("email_subject", "")
    email_body = qrcard.get("email_body", "")
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "email_address" in draft:
            email_address = draft["email_address"]
        if "email_subject" in draft:
            email_subject = draft["email_subject"]
        if "email_body" in draft:
            email_body = draft["email_body"]
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        email_address = request.form.get("email_address", "").strip()
        email_subject = request.form.get("email_subject", "").strip()
        email_body = request.form.get("email_body", "").strip()
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
        else:
            _set_qr_draft(
                session, qrcard_id, "", qr_name, None,
                extra_data={
                    "email_address": email_address,
                    "email_subject": email_subject,
                    "email_body": email_body,
                },
            )
            return redirect(url_for("qr_update_design_email_static", qrcard_id=qrcard_id))
    return render_template("/user/edit_qr_content_email_static.html",
        qrcard_id=qrcard_id, qr_name=qr_name,
        email_address=email_address, email_subject=email_subject, email_body=email_body,
        error_msg=error_msg)


@app.route("/qr/update/email-static/qr-design/<qrcard_id>", methods=["GET"])
def qr_update_design_email_static(qrcard_id):
    """Email static design step — own URL after Content → Next."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_email_static_proc
    fk_user_id = session.get("fk_user_id")
    proc = qr_email_static_proc.qr_email_static_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_email_static_qrcard_with_base(fk_user_id, qrcard_id, qrcard)
    draft = _get_qr_draft(session, qrcard_id)
    qr_name = qrcard.get("name", "")
    email_address = qrcard.get("email_address", "")
    email_subject = qrcard.get("email_subject", "")
    email_body = qrcard.get("email_body", "")
    if draft:
        qr_name = draft.get("qr_name") or qr_name
        if "email_address" in draft:
            email_address = draft["email_address"]
        if "email_subject" in draft:
            email_subject = draft["email_subject"]
        if "email_body" in draft:
            email_body = draft["email_body"]
    return render_template(
        "/user/edit_qr_design_email_static.html",
        qrcard_id=qrcard_id,
        qrcard=qrcard,
        qr_name=qr_name,
        email_address=email_address,
        email_subject=email_subject,
        email_body=email_body,
    )


@app.route("/qr/update/save/email-static/<qrcard_id>", methods=["POST"])
def qr_update_save_email_static(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.qr import qr_email_static_proc
    fk_user_id = session.get("fk_user_id")
    email_address = request.form.get("email_address", "").strip()
    email_subject = request.form.get("email_subject", "").strip()
    email_body = request.form.get("email_body", "").strip()
    qr_name = (request.form.get("qr_name") or "").strip() or "Untitled QR"
    qr_email_static_proc.qr_email_static_proc(app).edit_qrcard_email_static({
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": qr_name,
        "email_address": email_address,
        "email_subject": email_subject,
        "email_body": email_body,
    })
    _update_frame_id(fk_user_id, qrcard_id, request.form.get("frame_id", ""))
    _enc_url_u = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id}, {"url_content": 1}) or {}).get("url_content", "")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_u, request.form.get("frame_id", ""))
    _clear_qr_draft(session, qrcard_id)
    return redirect(url_for("user_qr_list"))

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
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
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
    from flask import request, url_for
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_ecard
    v = view_ecard.view_ecard(app)
    if request.method == "POST":
        # Back from design: re-show content form with saved data
        from itertools import zip_longest
        url_content = request.form.get("url_content", "QRkartu")
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
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    ecard_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
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
        _r2 = r2_mod.r2_storage_proc()

        session.modified = True
        welcome_img = request.files.get("E-card_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _r2.upload_file(welcome_img, f"ecard/_tmp/{tmp_key}/welcome{ext}")
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
                _r2.upload_file(cover_img, f"ecard/_tmp/{tmp_key}/pdf_cover_img{ext}")
                session["cover_img_tmp_key"] = tmp_key
                session["cover_img_tmp_name"] = "pdf_cover_img" + ext
                session.pop("ecard_cover_img_autocomplete_url", None)
                session.modified = True
        else:
            _ac_cover = request.form.get("ecard_cover_img_autocomplete_url", "").strip()
            if _ac_cover:
                session["ecard_cover_img_autocomplete_url"] = _ac_cover
                session.pop("cover_img_tmp_key", None)
                session.pop("cover_img_tmp_name", None)
                session.modified = True
        gallery_imgs = request.files.getlist("ecard_gallery_images[]")
        gallery_tmp_list = []
        for gf in gallery_imgs:
            if not gf or not gf.filename:
                continue
            gf.seek(0, 2)
            if gf.tell() > 5 * 1024 * 1024:
                continue
            gf.seek(0)
            ext = os.path.splitext(gf.filename)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                ext = ".jpg"
            safe_name = "gallery_" + _uuid.uuid4().hex + ext
            try:
                _r2.upload_file(gf, f"ecard/_tmp/{tmp_key}/{safe_name}")
                gallery_tmp_list.append({"safe_name": safe_name, "tmp_key": tmp_key})
            except Exception:
                pass
        if gallery_tmp_list:
            session["ecard_gallery_tmp_files"] = gallery_tmp_list
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
        # Put tmp image public URLs into ecard_data so the Back form includes them
        if session.get("cover_img_tmp_key") and session.get("cover_img_tmp_name"):
            _cover_url = _r2.public_url("ecard/_tmp/{}/{}".format(
                session["cover_img_tmp_key"], session["cover_img_tmp_name"]
            ))
            ecard_data["E-card_t1_header_img_url"] = _cover_url
            ecard_data["E-card_t3_circle_img_url"] = _cover_url
            ecard_data["E-card_t4_circle_img_url"] = _cover_url
        elif session.get("ecard_cover_img_autocomplete_url"):
            _cover_url = session["ecard_cover_img_autocomplete_url"]
            ecard_data["E-card_t1_header_img_url"] = _cover_url
            ecard_data["E-card_t3_circle_img_url"] = _cover_url
            ecard_data["E-card_t4_circle_img_url"] = _cover_url
        if session.get("welcome_img_tmp_key") and session.get("welcome_img_tmp_name"):
            ecard_data["welcome_img_url"] = _r2.public_url("ecard/_tmp/{}/{}".format(
                session["welcome_img_tmp_key"], session["welcome_img_tmp_name"]
            ))
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
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), response.get("qrcard_id", ""), response.get("qr_encode_url", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_pdf
        _uap_pdf.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=request.form.get("qr_name", ""), qr_type="pdf", source="create",
        )
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
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), response.get("qrcard_id", ""), response.get("qr_encode_url", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_web
        _uap_web.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=response.get("qr_name", "") or request.form.get("qr_name", ""),
            qr_type="web", source="create",
        )
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
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), response.get("qrcard_id", ""), response.get("qr_encode_url", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_ec
        _uap_ec.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=response.get("qr_name", "") or request.form.get("qr_name", ""),
            qr_type="ecard", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return view_ecard.view_ecard(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        ecard_data=response.get("ecard_data", {}),
    )


# ─── Links QR routes ─────────────────────────────────────────────────────────

@app.route("/qr/new/links", methods=["GET"])
@app.route("/qr/new/links/back", methods=["POST"])
def user_new_qr_links():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_links
    v = view_links.view_links(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        links_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    links_data[key] = val_list
                else:
                    links_data[key] = val_list[0] if val_list else ""
        if session.get("links_cover_tmp_key") and session.get("links_cover_tmp_name"):
            links_data["Links_cover_img_url"] = r2_mod.r2_storage_proc().public_url("links/_tmp/{}/{}".format(session["links_cover_tmp_key"], session["links_cover_tmp_name"]))
        if session.get("links_welcome_tmp_key") and session.get("links_welcome_tmp_name"):
            links_data["welcome_img_url"] = r2_mod.r2_storage_proc().public_url("links/_tmp/{}/{}".format(session["links_welcome_tmp_key"], session["links_welcome_tmp_name"]))
        # Rebuild links list for pre-filling
        urls = links_data.get("Links_link_url[]", [])
        names = links_data.get("Links_link_name[]", [])
        descs = links_data.get("Links_link_desc[]", [])
        if isinstance(urls, str):
            urls = [urls]
        if isinstance(names, str):
            names = [names]
        if isinstance(descs, str):
            descs = [descs]
        from itertools import zip_longest
        links_list = [{"url": u or "", "name": n or "", "desc": d or ""} for u, n, d in zip_longest(urls, names, descs, fillvalue="")]
        links_data["Links_links"] = links_list
        return v.new_qr_content_html(base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, links_data=links_data)
    return v.new_qr_content_html(base_url=config.G_BASE_URL)


@app.route("/qr/new/links/qr-design", methods=["GET", "POST"])
def user_new_qr_design_links():
    import os, re, uuid as _uuid
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_links
    from pytavia_modules.qr import qr_links_proc
    v = view_links.view_links(app)
    proc = qr_links_proc.qr_links_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    links_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    links_data[key] = val_list
                else:
                    links_data[key] = val_list[0] if val_list else ""
        tmp_key = session.get("links_tmp_key") or _uuid.uuid4().hex
        session["links_tmp_key"] = tmp_key
        session.modified = True
        _r2 = r2_mod.r2_storage_proc()
        welcome_img = request.files.get("Links_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "welcome" + ext
                _r2.upload_file(welcome_img, f"links/_tmp/{tmp_key}/{fname}")
                session["links_welcome_tmp_key"] = tmp_key
                session["links_welcome_tmp_name"] = fname
                session.modified = True
            else:
                error_msg = "Welcome image must be 1 MB or smaller."
        cover_img = request.files.get("Links_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "links_cover_img" + ext
                _r2.upload_file(cover_img, f"links/_tmp/{tmp_key}/{fname}")
                session["links_cover_tmp_key"] = tmp_key
                session["links_cover_tmp_name"] = fname
                session.modified = True
        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/links/" + short_code
        if session.get("links_cover_tmp_key") and session.get("links_cover_tmp_name"):
            links_data["Links_cover_img_url"] = r2_mod.r2_storage_proc().public_url("links/_tmp/{}/{}".format(session["links_cover_tmp_key"], session["links_cover_tmp_name"]))
        if session.get("links_welcome_tmp_key") and session.get("links_welcome_tmp_name"):
            links_data["welcome_img_url"] = r2_mod.r2_storage_proc().public_url("links/_tmp/{}/{}".format(session["links_welcome_tmp_key"], session["links_welcome_tmp_name"]))
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, links_data=links_data)


@app.route("/qr/save/links", methods=["POST"])
def qr_save_links():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_links_proc
    from pytavia_modules.view import view_links
    response = qr_links_proc.qr_links_proc(app).complete_links_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), response.get("qrcard_id", ""), response.get("qr_encode_url", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_lk
        _uap_lk.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=response.get("qr_name", "") or request.form.get("qr_name", ""),
            qr_type="links", source="create",
        )
        return redirect(url_for("user_qr_list"))
    return view_links.view_links(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        links_data=response.get("links_data", {}),
    )


def _merge_links_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Overlay db_qrcard_links document onto db_qrcard base (so qr_image_url etc. are included)."""
    try:
        base_doc = mgd_db.db_qrcard.find_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id})
    except Exception:
        base_doc = None
    out = {k: v for k, v in (base_doc or qrcard).items() if k != "_id"}
    try:
        links_doc = mgd_db.db_qrcard_links.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    except Exception:
        links_doc = None
    if links_doc:
        for key, value in links_doc.items():
            if key != "_id":
                out[key] = value
    return out


@app.route("/qr/update/links/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_links(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_links_proc as _qrl
    proc = _qrl.qr_links_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_links_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    if request.method == "POST":
        if request.form.get("back_from_design"):
            draft = dict(qrcard)
            for key in request.form:
                if key in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                    continue
                if key.endswith("[]"):
                    continue
                val_list = request.form.getlist(key)
                draft[key] = val_list if len(val_list) > 1 else (val_list[0] if val_list else "")
            urls = request.form.getlist("Links_link_url[]")
            names = request.form.getlist("Links_link_name[]")
            descs = request.form.getlist("Links_link_desc[]")
            from itertools import zip_longest
            draft["Links_links"] = [{"url": u or "", "name": n or "", "desc": d or ""} for u, n, d in zip_longest(urls, names, descs, fillvalue="")]
            draft["short_code"] = (request.form.get("short_code") or draft.get("short_code") or "").strip()
            return view_update_links.view_update_links(app).update_qr_content_html(qrcard=draft, base_url=config.G_BASE_URL)
        # Normal POST: save content + go to design
        import os, uuid as _uuid
        url_content = (request.form.get("url_content") or "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = (request.form.get("qr_name") or "").strip()
        short_code = (request.form.get("short_code") or "").strip().lower()
        urls = request.form.getlist("Links_link_url[]")
        names_l = request.form.getlist("Links_link_name[]")
        descs = request.form.getlist("Links_link_desc[]")
        from itertools import zip_longest
        links_list = [{"url": u.strip(), "name": n.strip(), "desc": d.strip()} for u, n, d in zip_longest(urls, names_l, descs, fillvalue="") if (u or "").strip()]
        content_update = {
            "name": qr_name,
            "url_content": url_content,
            "Links_title": (request.form.get("Links_title") or "").strip(),
            "Links_desc": (request.form.get("Links_desc") or "").strip(),
            "Links_links": links_list,
        }
        for key in request.form:
            if key.startswith("Links_") and not key.endswith("[]") and key not in ["Links_title", "Links_desc"]:
                content_update[key] = request.form.get(key, "").strip()
        for key in ["welcome_time", "welcome_bg_color"]:
            if request.form.get(key):
                content_update[key] = request.form.get(key)
        _mgd = database.get_db_conn(config.mainDB)
        if request.form.get("reset_qr_style") == "1":
            _unset_fields = {
                "qr_composite_url": "",
                "qr_image_url": "",
                "qr_dot_style": "",
                "qr_corner_style": "",
                "qr_dot_color": "",
                "qr_bg_color": "",
                "card_bg_color": "",
            }
            _mgd.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _unset_fields}
            )
            _mgd.db_qrcard_links.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _unset_fields}
            )
        # Handle welcome image delete
        if request.form.get("welcome_img_delete") == "1":
            _mgd.db_qrcard_links.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            content_update["welcome_img_url"] = ""
        # Handle cover image upload
        _r2 = r2_mod.r2_storage_proc()
        cover_img = request.files.get("Links_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                content_update["Links_cover_img_url"] = _r2.upload_file(cover_img, f"links/{qrcard_id}/links_cover_img{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links"})
        # Handle cover delete
        if request.form.get("Links_profile_img_delete") == "1":
            content_update["Links_cover_img_url"] = ""
        cover_asset_url = (request.form.get("links_cover_img_autocomplete_url") or "").strip()
        if cover_asset_url:
            if cover_asset_url.startswith("http://") or cover_asset_url.startswith("https://"):
                content_update["Links_cover_img_url"] = cover_asset_url
            elif cover_asset_url.startswith("/static/"):
                local_path = os.path.join(app.root_path, cover_asset_url.lstrip("/").replace("/", os.sep))
                if os.path.isfile(local_path):
                    ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    unique_cover = f"links_cover_img_{_uuid.uuid4().hex[:12]}{ext}"
                    try:
                        with open(local_path, "rb") as f:
                            content_update["Links_cover_img_url"] = _r2.upload_bytes(
                                f.read(),
                                f"links/{qrcard_id}/{unique_cover}",
                                track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links", "file_name": unique_cover}
                            )
                    except Exception:
                        pass
        # Handle welcome image upload
        welcome_img = request.files.get("Links_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                content_update["welcome_img_url"] = _r2.upload_file(welcome_img, f"links/{qrcard_id}/welcome_{int(time.time())}{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links"})
        welcome_asset_url = (request.form.get("links_welcome_img_autocomplete_url") or "").strip()
        if welcome_asset_url:
            if welcome_asset_url.startswith("http://") or welcome_asset_url.startswith("https://"):
                content_update["welcome_img_url"] = welcome_asset_url
            elif welcome_asset_url.startswith("/static/"):
                local_path = os.path.join(app.root_path, welcome_asset_url.lstrip("/").replace("/", os.sep))
                if os.path.isfile(local_path):
                    ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    unique_welcome = f"welcome_{_uuid.uuid4().hex[:12]}{ext}"
                    try:
                        with open(local_path, "rb") as f:
                            content_update["welcome_img_url"] = _r2.upload_bytes(
                                f.read(),
                                f"links/{qrcard_id}/{unique_welcome}",
                                track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links", "file_name": unique_welcome}
                            )
                    except Exception:
                        pass
        params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, **content_update}
        if short_code:
            params["short_code"] = short_code
        proc.edit_qrcard(params)
        qrcard.update(content_update)
        return redirect(url_for("qr_update_design_links", qrcard_id=qrcard_id))
    return view_update_links.view_update_links(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


@app.route("/qr/update/links/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_links(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_links_proc as _qrl
    proc = _qrl.qr_links_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_links_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    # Explicitly pull QR image URLs from db_qrcard in case merge missed them
    _base = database.get_db_conn(config.mainDB).db_qrcard.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
        {"qr_composite_url": 1, "qr_image_url": 1, "qr_dot_style": 1,
         "qr_corner_style": 1, "qr_dot_color": 1, "qr_bg_color": 1, "_id": 0}
    ) or {}
    for _k in ("qr_composite_url", "qr_image_url", "qr_dot_style", "qr_corner_style", "qr_dot_color", "qr_bg_color"):
        if _base.get(_k):
            qrcard[_k] = _base[_k]
    qr_encode_url = config.G_BASE_URL + "/links/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_links.view_update_links(app).update_qr_design_html(qrcard=qrcard, qr_encode_url=qr_encode_url)


@app.route("/qr/update/save/links/<qrcard_id>", methods=["POST"])
def qr_update_save_links(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_links_proc as _qrl
    proc = _qrl.qr_links_proc(app)
    if not database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}):
        return redirect(url_for("user_qr_list"))
    design_update = {}
    for key in request.form:
        if key.startswith("Links_") and not key.endswith("[]"):
            val = request.form.get(key)
            if val is not None:
                design_update[key] = val.strip()
    if request.form.get("Links_font_apply_all") in ("on", "true", "1", "yes"):
        design_update["Links_font_apply_all"] = True
    params = {
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": (request.form.get("qr_name") or "").strip() or "Untitled QR",
        "url_content": (request.form.get("url_content") or "").strip(),
        **design_update,
    }
    proc.edit_qrcard(params)
    _frame_id_links = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_links)
    _enc_url_links = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_links", "/links/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_links, _frame_id_links)
    return redirect(url_for("user_qr_list"))


# ─── Sosmed QR routes ─────────────────────────────────────────────────────────

@app.route("/qr/new/sosmed", methods=["GET"])
@app.route("/qr/new/sosmed/back", methods=["POST"])
def user_new_qr_sosmed():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_sosmed
    v = view_sosmed.view_sosmed(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        sosmed_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    sosmed_data[key] = val_list
                else:
                    sosmed_data[key] = val_list[0] if val_list else ""
        if session.get("sosmed_cover_tmp_key") and session.get("sosmed_cover_tmp_name"):
            sosmed_data["Sosmed_cover_img_url"] = r2_mod.r2_storage_proc().public_url("sosmed/_tmp/{}/{}".format(session["sosmed_cover_tmp_key"], session["sosmed_cover_tmp_name"]))
        if session.get("sosmed_welcome_tmp_key") and session.get("sosmed_welcome_tmp_name"):
            sosmed_data["welcome_img_url"] = r2_mod.r2_storage_proc().public_url("sosmed/_tmp/{}/{}".format(session["sosmed_welcome_tmp_key"], session["sosmed_welcome_tmp_name"]))
        icons = sosmed_data.get("Sosmed_item_icon[]", [])
        names = sosmed_data.get("Sosmed_item_name[]", [])
        descs = sosmed_data.get("Sosmed_item_desc[]", [])
        if isinstance(icons, str): icons = [icons]
        if isinstance(names, str): names = [names]
        if isinstance(descs, str): descs = [descs]
        from itertools import zip_longest
        items_list = [{"icon": ic or "fa-solid fa-globe", "name": n or "", "desc": d or ""} for ic, n, d in zip_longest(icons, names, descs, fillvalue="")]
        sosmed_data["Sosmed_items"] = items_list
        return v.new_qr_content_html(base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, sosmed_data=sosmed_data)
    return v.new_qr_content_html(base_url=config.G_BASE_URL)


@app.route("/qr/new/sosmed/qr-design", methods=["GET", "POST"])
def user_new_qr_design_sosmed():
    import os, re, uuid as _uuid
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_sosmed
    from pytavia_modules.qr import qr_sosmed_proc
    v = view_sosmed.view_sosmed(app)
    proc = qr_sosmed_proc.qr_sosmed_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    sosmed_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    sosmed_data[key] = val_list
                else:
                    sosmed_data[key] = val_list[0] if val_list else ""
        tmp_key = session.get("sosmed_tmp_key") or _uuid.uuid4().hex
        session["sosmed_tmp_key"] = tmp_key
        session.modified = True
        _r2 = r2_mod.r2_storage_proc()
        welcome_img = request.files.get("Sosmed_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "welcome" + ext
                _r2.upload_file(welcome_img, f"sosmed/_tmp/{tmp_key}/{fname}")
                session["sosmed_welcome_tmp_key"] = tmp_key
                session["sosmed_welcome_tmp_name"] = fname
                session.modified = True
            else:
                error_msg = "Welcome image must be 1 MB or smaller."
        cover_img = request.files.get("Sosmed_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "sosmed_cover_img" + ext
                _r2.upload_file(cover_img, f"sosmed/_tmp/{tmp_key}/{fname}")
                session["sosmed_cover_tmp_key"] = tmp_key
                session["sosmed_cover_tmp_name"] = fname
                session.modified = True
        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/sosmed/" + short_code
        if session.get("sosmed_cover_tmp_key") and session.get("sosmed_cover_tmp_name"):
            sosmed_data["Sosmed_cover_img_url"] = r2_mod.r2_storage_proc().public_url("sosmed/_tmp/{}/{}".format(session["sosmed_cover_tmp_key"], session["sosmed_cover_tmp_name"]))
        if session.get("sosmed_welcome_tmp_key") and session.get("sosmed_welcome_tmp_name"):
            sosmed_data["welcome_img_url"] = r2_mod.r2_storage_proc().public_url("sosmed/_tmp/{}/{}".format(session["sosmed_welcome_tmp_key"], session["sosmed_welcome_tmp_name"]))
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, sosmed_data=sosmed_data)


@app.route("/qr/save/sosmed", methods=["POST"])
def qr_save_sosmed():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_sosmed_proc
    from pytavia_modules.view import view_sosmed
    response = qr_sosmed_proc.qr_sosmed_proc(app).complete_sosmed_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
            "qr_dot_style": request.form.get("qr_dot_style", "square"),
            "qr_corner_style": request.form.get("qr_corner_style", "square"),
            "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
            "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
        })
        _save_qr_composite(app, session.get("fk_user_id"), response.get("qrcard_id", ""), response.get("qr_encode_url", ""), request.form.get("frame_id", ""))
        return redirect(url_for("user_qr_list"))
    return view_sosmed.view_sosmed(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        sosmed_data=response.get("sosmed_data", {}),
    )


def _merge_sosmed_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Overlay db_qrcard_sosmed document onto qrcard."""
    try:
        sosmed_doc = mgd_db.db_qrcard_sosmed.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    except Exception:
        sosmed_doc = None
    if not sosmed_doc:
        return qrcard
    out = dict(qrcard)
    for key, value in sosmed_doc.items():
        if key != "_id":
            out[key] = value
    return out


@app.route("/qr/update/sosmed/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_sosmed(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_sosmed_proc as _qrs
    proc = _qrs.qr_sosmed_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_sosmed_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    if request.method == "POST":
        if request.form.get("back_from_design"):
            draft = dict(qrcard)
            for key in request.form:
                if key in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                    continue
                if key.endswith("[]"):
                    continue
                val_list = request.form.getlist(key)
                draft[key] = val_list if len(val_list) > 1 else (val_list[0] if val_list else "")
            icons = request.form.getlist("Sosmed_item_icon[]")
            names = request.form.getlist("Sosmed_item_name[]")
            descs = request.form.getlist("Sosmed_item_desc[]")
            from itertools import zip_longest
            draft["Sosmed_items"] = [{"icon": ic or "fa-solid fa-globe", "name": n or "", "desc": d or ""} for ic, n, d in zip_longest(icons, names, descs, fillvalue="")]
            draft["short_code"] = (request.form.get("short_code") or draft.get("short_code") or "").strip()
            return view_update_sosmed.view_update_sosmed(app).update_qr_content_html(qrcard=draft, base_url=config.G_BASE_URL)
        import os
        url_content = (request.form.get("url_content") or "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = (request.form.get("qr_name") or "").strip()
        short_code = (request.form.get("short_code") or "").strip().lower()
        icons = request.form.getlist("Sosmed_item_icon[]")
        names_l = request.form.getlist("Sosmed_item_name[]")
        descs = request.form.getlist("Sosmed_item_desc[]")
        from itertools import zip_longest
        items_list = [{"icon": ic.strip() or "fa-solid fa-globe", "name": n.strip(), "desc": d.strip()} for ic, n, d in zip_longest(icons, names_l, descs, fillvalue="") if (n or "").strip()]
        content_update = {
            "name": qr_name,
            "url_content": url_content,
            "Sosmed_title": (request.form.get("Sosmed_title") or "").strip(),
            "Sosmed_desc": (request.form.get("Sosmed_desc") or "").strip(),
            "Sosmed_items": items_list,
        }
        for key in request.form:
            if key.startswith("Sosmed_") and not key.endswith("[]") and key not in ["Sosmed_title", "Sosmed_desc"]:
                content_update[key] = request.form.get(key, "").strip()
        for key in ["welcome_time", "welcome_bg_color"]:
            if request.form.get(key):
                content_update[key] = request.form.get(key)
        _mgd = database.get_db_conn(config.mainDB)
        if request.form.get("welcome_img_delete") == "1":
            _mgd.db_qrcard_sosmed.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            content_update["welcome_img_url"] = ""
        _r2 = r2_mod.r2_storage_proc()
        cover_img = request.files.get("Sosmed_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                content_update["Sosmed_cover_img_url"] = _r2.upload_file(cover_img, f"sosmed/{qrcard_id}/sosmed_cover_img{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed"})
        if request.form.get("Sosmed_profile_img_delete") == "1":
            content_update["Sosmed_cover_img_url"] = ""
        welcome_img = request.files.get("Sosmed_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                content_update["welcome_img_url"] = _r2.upload_file(welcome_img, f"sosmed/{qrcard_id}/welcome_{int(time.time())}{ext}", track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed"})
        params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, **content_update}
        if short_code:
            params["short_code"] = short_code
        proc.edit_qrcard(params)
        qrcard.update(content_update)
        qr_encode_url = config.G_BASE_URL + "/sosmed/" + (qrcard.get("short_code") or short_code or "")
        return view_update_sosmed.view_update_sosmed(app).update_qr_design_html(qrcard=qrcard, url_content=url_content, qr_name=qr_name, qr_encode_url=qr_encode_url)
    return view_update_sosmed.view_update_sosmed(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


@app.route("/qr/update/sosmed/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_sosmed(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_sosmed_proc as _qrs
    proc = _qrs.qr_sosmed_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_sosmed_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    qr_encode_url = config.G_BASE_URL + "/sosmed/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_sosmed.view_update_sosmed(app).update_qr_design_html(qrcard=qrcard, qr_encode_url=qr_encode_url)


@app.route("/qr/update/save/sosmed/<qrcard_id>", methods=["POST"])
def qr_update_save_sosmed(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_sosmed_proc as _qrs
    proc = _qrs.qr_sosmed_proc(app)
    if not database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}):
        return redirect(url_for("user_qr_list"))
    design_update = {}
    for key in request.form:
        if key.startswith("Sosmed_") and not key.endswith("[]"):
            val = request.form.get(key)
            if val is not None:
                design_update[key] = val.strip()
    if request.form.get("Sosmed_font_apply_all") in ("on", "true", "1", "yes"):
        design_update["Sosmed_font_apply_all"] = True
    params = {
        "fk_user_id": fk_user_id, "qrcard_id": qrcard_id,
        "name": (request.form.get("qr_name") or "").strip() or "Untitled QR",
        "url_content": (request.form.get("url_content") or "").strip(),
        **design_update,
    }
    proc.edit_qrcard(params)
    _frame_id_sosmed = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_sosmed)
    _enc_url_sosmed = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_sosmed", "/sosmed/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_sosmed, _frame_id_sosmed)
    return redirect(url_for("user_qr_list"))


# ─── All-in-One QR routes ─────────────────────────────────────────────────────

@app.route("/qr/new/allinone", methods=["GET"])
@app.route("/qr/new/allinone/back", methods=["POST"])
def user_new_qr_allinone():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    import json as _json
    from pytavia_modules.view import view_allinone
    v = view_allinone.view_allinone(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        allinone_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design", "allinone_sections_json"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    allinone_data[key] = val_list
                else:
                    allinone_data[key] = val_list[0] if val_list else ""
        sections_json_str = request.form.get("allinone_sections_json", "[]")
        try:
            allinone_data["Allinone_sections"] = _json.loads(sections_json_str)
        except Exception:
            allinone_data["Allinone_sections"] = []
        if session.get("allinone_cover_r2_url"):
            allinone_data["Allinone_cover_img_url"] = session["allinone_cover_r2_url"]
        return v.new_qr_content_html(base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, allinone_data=allinone_data)
    return v.new_qr_content_html(base_url=config.G_BASE_URL)


@app.route("/qr/new/allinone/qr-design", methods=["GET", "POST"])
def user_new_qr_design_allinone():
    import os, re, uuid as _uuid, json as _json
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_allinone
    from pytavia_modules.qr import qr_allinone_proc
    v = view_allinone.view_allinone(app)
    proc = qr_allinone_proc.qr_allinone_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    allinone_data = {}
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "allinone_sections_json"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    allinone_data[key] = val_list
                else:
                    allinone_data[key] = val_list[0] if val_list else ""
        # Parse sections JSON
        sections_json_str = request.form.get("allinone_sections_json", "[]")
        try:
            sections = _json.loads(sections_json_str)
            if not isinstance(sections, list):
                sections = []
        except Exception:
            sections = []
        tmp_key = session.get("allinone_tmp_key") or _uuid.uuid4().hex
        session["allinone_tmp_key"] = tmp_key
        session.modified = True
        _r2 = r2_mod.r2_storage_proc()
        # Handle cover image → upload directly to R2 tmp
        cover_img = request.files.get("Allinone_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname_cover = "allinone_cover" + ext
                r2_cover_url = _r2.upload_file(cover_img, f"allinone/_tmp/{tmp_key}/{fname_cover}")
                session["allinone_cover_tmp_key"] = tmp_key
                session["allinone_cover_tmp_name"] = fname_cover
                session["allinone_cover_r2_url"]   = r2_cover_url
                session.modified = True
        # Handle section file uploads (image/pdf/video) → upload directly to R2 tmp
        # Note: autocomplete /static/ paths are handled at save time, not here
        for i, s in enumerate(sections):
            stype = s.get("type", "")
            if stype in ("image", "pdf", "video"):
                fobj = request.files.get(f"allinone_file_{i}")
                if fobj and fobj.filename:
                    fobj.seek(0, 2)
                    if fobj.tell() <= 5 * 1024 * 1024:
                        fobj.seek(0)
                        ext = os.path.splitext(fobj.filename)[1].lower()
                        allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"} if stype == "image" else ({".pdf"} if stype == "pdf" else {".mp4", ".mov", ".avi", ".mkv", ".webm"})
                        if ext not in allowed:
                            ext = ".jpg" if stype == "image" else (".pdf" if stype == "pdf" else ".mp4")
                        fname = f"{stype}_{i}_{_uuid.uuid4().hex[:8]}{ext}"
                        sections[i]["v1"] = _r2.upload_file(fobj, f"allinone/_tmp/{tmp_key}/{fname}")
        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name, include_draft=False):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/allinone/" + short_code
        if session.get("allinone_cover_r2_url"):
            allinone_data["Allinone_cover_img_url"] = session["allinone_cover_r2_url"]
        allinone_data["Allinone_sections"] = sections
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, allinone_data=allinone_data)


@app.route("/qr/new/allinone/save-draft", methods=["POST"])
def qr_new_allinone_save_draft():
    """AJAX endpoint: save allinone QR as DRAFT and return JSON with qrcard_id."""
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_allinone_proc
    proc = qr_allinone_proc.qr_allinone_proc(app)
    response = proc.save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({
        "status": "ok",
        "qrcard_id": response["qrcard_id"],
        "short_code": response["short_code"],
        "qr_encode_url": response["qr_encode_url"],
    }), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/allinone/design/<qrcard_id>", methods=["GET"])
def qr_new_allinone_design_draft(qrcard_id):
    """Load design step for a DRAFT allinone QR (created via save-draft)."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_allinone_proc as _qra
    from pytavia_modules.view import view_allinone
    proc = _qra.qr_allinone_proc(app)
    qrcard = proc.get_allinone_by_qrcard_id(qrcard_id, fk_user_id, allow_draft=True)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_allinone_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    short_code = qrcard.get("short_code") or ""
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/allinone/" + short_code if short_code else None
    v = view_allinone.view_allinone(app)
    return v.new_qr_design_html(
        url_content=qrcard.get("url_content", ""),
        qr_name=qrcard.get("name", ""),
        short_code=short_code,
        qr_encode_url=qr_encode_url,
        allinone_data=qrcard,
        qrcard_id=qrcard_id,
    )


# ─── DRAFT save-draft + design routes for all 8 types ────────────────────────

def _activate_draft_qrcard(fk_user_id, qrcard_id, type_collection, qr_type_path):
    """If qrcard is DRAFT, set ACTIVE in all 3 collections and return (short_code, qr_encode_url)."""
    from pytavia_core import database as _db_m, config as _cfg
    _db = _db_m.get_db_conn(_cfg.mainDB)
    _qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if _qrcard.get("status") == "DRAFT":
        _db.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "ACTIVE"}})
        getattr(_db, type_collection).update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "ACTIVE"}})
        _db.db_qr_index.update_one({"qrcard_id": qrcard_id}, {"$set": {"status": "ACTIVE"}})
    sc = _qrcard.get("short_code", "")
    qr_encode_url = _cfg.G_BASE_URL.rstrip("/") + qr_type_path + sc if sc else ""
    return qr_encode_url


@app.route("/qr/new/web/save-draft", methods=["POST"])
def qr_new_web_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_web_proc
    response = qr_web_proc.qr_web_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/web/design/<qrcard_id>", methods=["GET"])
def qr_new_web_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_web
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/web/" + sc if sc else None
    return view_web.view_web(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
    )


@app.route("/qr/new/ecard/save-draft", methods=["POST"])
def qr_new_ecard_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_ecard_proc
    response = qr_ecard_proc.qr_ecard_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/ecard/design/<qrcard_id>", methods=["GET"])
def qr_new_ecard_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_ecard
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/ecard/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_ecard.view_ecard(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        ecard_data=_data,
    )


@app.route("/qr/new/links/save-draft", methods=["POST"])
def qr_new_links_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_links_proc
    response = qr_links_proc.qr_links_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/links/design/<qrcard_id>", methods=["GET"])
def qr_new_links_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_links
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/links/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_links.view_links(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        links_data=_data,
    )


@app.route("/qr/new/sosmed/save-draft", methods=["POST"])
def qr_new_sosmed_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_sosmed_proc
    response = qr_sosmed_proc.qr_sosmed_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/sosmed/design/<qrcard_id>", methods=["GET"])
def qr_new_sosmed_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_sosmed
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/sosmed/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_sosmed.view_sosmed(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        sosmed_data=_data,
    )


@app.route("/qr/new/pdf/save-draft", methods=["POST"])
def qr_new_pdf_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_pdf_proc
    response = qr_pdf_proc.qr_pdf_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/pdf/design/<qrcard_id>", methods=["GET"])
def qr_new_pdf_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_pdf
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/pdf/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_pdf.view_pdf(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        pdf_data=_data,
    )


@app.route("/qr/new/images/save-draft", methods=["POST"])
def qr_new_images_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_images_proc
    response = qr_images_proc.qr_images_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    if request.form.get("reset_qr_style") == "1":
        _fk = session.get("fk_user_id")
        _qid = response["qrcard_id"]
        database.get_db_conn(config.mainDB).db_qrcard.update_one(
            {"fk_user_id": _fk, "qrcard_id": _qid},
            {"$unset": {"qr_dot_style": "", "qr_corner_style": "", "qr_dot_color": "", "qr_bg_color": "", "card_bg_color": "", "qr_image_url": "", "qr_composite_url": ""}},
        )
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/images/design/<qrcard_id>", methods=["GET"])
def qr_new_images_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_images
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/images/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url','qr_dot_style','qr_corner_style','qr_dot_color','qr_bg_color','card_bg_color'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_images.view_images(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        images_data=_data,
    )


@app.route("/qr/new/video/save-draft", methods=["POST"])
def qr_new_video_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_video_proc
    response = qr_video_proc.qr_video_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/video/design/<qrcard_id>", methods=["GET"])
def qr_new_video_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.view import view_video
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/video/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','welcome_img_url'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    return view_video.view_video(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        video_data=_data,
    )


@app.route("/qr/new/special/save-draft", methods=["POST"])
def qr_new_special_save_draft():
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_special_proc
    response = qr_special_proc.qr_special_proc(app).save_draft(request, session, app.root_path)
    if response.get("status") != "ok":
        return _json.dumps({"status": "error", "message_desc": response.get("message_desc", "Save failed.")}), 400, {"Content-Type": "application/json"}
    return _json.dumps({"status": "ok", "qrcard_id": response["qrcard_id"], "short_code": response["short_code"], "qr_encode_url": response["qr_encode_url"]}), 200, {"Content-Type": "application/json"}


@app.route("/qr/new/special/design/<qrcard_id>", methods=["GET"])
def qr_new_special_design_draft(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    import json as _json_sd
    from pytavia_modules.view import view_special
    _db_sd = database.get_db_conn(config.mainDB)
    qrcard = _db_sd.db_qrcard_special.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or \
             _db_sd.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id, "qr_type": "special"})
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/special/" + sc if sc else None
    _special_sections = qrcard.get("special_sections", [])
    if isinstance(_special_sections, str):
        try:
            _special_sections = _json_sd.loads(_special_sections)
        except Exception:
            _special_sections = []
    return view_special.view_special(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url,
        special_sections=_special_sections, qrcard_id=qrcard_id,
    )


@app.route("/qr/save/allinone", methods=["POST"])
def qr_save_allinone():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_allinone_proc
    from pytavia_modules.view import view_allinone
    response = qr_allinone_proc.qr_allinone_proc(app).complete_allinone_save(request, session, app.root_path)
    if response.get("status") != "ok":
        return view_allinone.view_allinone(app).new_qr_design_html(
            url_content=request.form.get("url_content", ""),
            qr_name=request.form.get("qr_name", ""),
            short_code=request.form.get("short_code", ""),
            error_msg=response.get("message_desc", "Save failed."),
        )
    _frame_id = request.form.get("frame_id", "") or request.form.get("Allinone_frame_id", "")
    _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), _frame_id)
    _save_custom_qr_image(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(
        app, session.get("fk_user_id"), response.get("qrcard_id", ""),
        response.get("qr_encode_url", ""), _frame_id,
    )
    from pytavia_modules.user import user_activity_proc as _uap_aio
    _uap_aio.user_activity_proc(app).log(
        fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
        qrcard_id=response.get("qrcard_id", ""),
        qr_name=request.form.get("qr_name", ""), qr_type="allinone", source="create",
    )
    return redirect(url_for("user_qr_list"))


def _merge_allinone_into_qrcard(mgd_db, fk_user_id, qrcard_id, qrcard):
    """Overlay db_qrcard_allinone document onto qrcard."""
    try:
        allinone_doc = mgd_db.db_qrcard_allinone.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    except Exception:
        allinone_doc = None
    if not allinone_doc:
        return qrcard
    merged = dict(qrcard)
    for key, value in allinone_doc.items():
        if key != "_id":
            merged[key] = value
    return merged


@app.route("/qr/update/allinone/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_allinone(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_allinone_proc as _qra
    proc = _qra.qr_allinone_proc(app)
    qrcard = proc.get_allinone_by_qrcard_id(qrcard_id, fk_user_id, allow_draft=True)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_allinone_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    if request.method == "POST":
        result = proc.update_allinone_content(request, session, app.root_path, qrcard_id)
        if result.get("status") != "ok":
            return view_update_allinone.view_update_allinone(app).update_qr_content_html(
                qrcard=qrcard, base_url=config.G_BASE_URL, error_msg=result.get("message_desc")
            )
        qrcard = proc.get_allinone_by_qrcard_id(qrcard_id, fk_user_id)
        qrcard = _merge_allinone_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
        short_code = qrcard.get("short_code") or ""
        qr_encode_url = config.G_BASE_URL + "/allinone/" + short_code if short_code else None
        return view_update_allinone.view_update_allinone(app).update_qr_design_html(
            qrcard=qrcard, qr_encode_url=qr_encode_url, msg="Saved successfully."
        )
    return view_update_allinone.view_update_allinone(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


@app.route("/qr/update/allinone/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_allinone(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_allinone_proc as _qra
    proc = _qra.qr_allinone_proc(app)
    qrcard = proc.get_allinone_by_qrcard_id(qrcard_id, fk_user_id, allow_draft=True)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    qrcard = _merge_allinone_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    qr_encode_url = config.G_BASE_URL + "/allinone/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_allinone.view_update_allinone(app).update_qr_design_html(qrcard=qrcard, qr_encode_url=qr_encode_url)


@app.route("/qr/update/save/allinone/<qrcard_id>", methods=["POST"])
def qr_update_save_allinone(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_allinone_proc as _qra
    proc = _qra.qr_allinone_proc(app)
    qrcard = proc.get_allinone_by_qrcard_id(qrcard_id, fk_user_id, allow_draft=True)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    design_update = {}
    for key in request.form:
        if key.startswith("Allinone_") and not key.endswith("[]"):
            val = request.form.get(key)
            if val is not None:
                design_update[key] = val.strip()
    if request.form.get("Allinone_font_apply_all") in ("on", "true", "1", "yes"):
        design_update["Allinone_font_apply_all"] = True
    # Always activate when completing design step
    design_update["status"] = "ACTIVE"
    database.get_db_conn(config.mainDB).db_qrcard.update_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": design_update}
    )
    database.get_db_conn(config.mainDB).db_qrcard_allinone.update_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": design_update}, upsert=True
    )
    database.get_db_conn(config.mainDB).db_qr_index.update_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"status": "ACTIVE"}}
    )
    # Clean up any other DRAFT records with the same name (orphans from old sessions / double-submits)
    _qr_name = qrcard.get("name", "")
    if _qr_name:
        _mgd = database.get_db_conn(config.mainDB)
        _orphan_ids = [
            d["qrcard_id"] for d in _mgd.db_qrcard.find(
                {"fk_user_id": fk_user_id, "name": _qr_name, "status": "DRAFT",
                 "qrcard_id": {"$ne": qrcard_id}},
                {"qrcard_id": 1}
            )
        ]
        if _orphan_ids:
            _mgd.db_qrcard.delete_many({"qrcard_id": {"$in": _orphan_ids}})
            _mgd.db_qrcard_allinone.delete_many({"qrcard_id": {"$in": _orphan_ids}})
            _mgd.db_qr_index.delete_many({"qrcard_id": {"$in": _orphan_ids}})

    _frame_id = request.form.get("frame_id", "") or request.form.get("Allinone_frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id)
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _qr_encode_url = config.G_BASE_URL.rstrip("/") + "/allinone/" + (qrcard.get("short_code") or "")
    _save_qr_composite(app, fk_user_id, qrcard_id, _qr_encode_url, _frame_id)
    if qrcard.get("status") == "DRAFT":
        from pytavia_modules.user import user_activity_proc as _uap_aio2
        _uap_aio2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=qrcard.get("name", ""), qr_type="allinone", source="create",
        )
    return redirect(url_for("user_qr_list"))


# ─── Special QR routes ────────────────────────────────────────────────────────

@app.route("/qr/new/special", methods=["GET"])
@app.route("/qr/new/special/back", methods=["POST"])
def user_new_qr_special():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    import json as _json
    from pytavia_modules.view import view_special
    v = view_special.view_special(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        sections_json = request.form.get("special_sections", "[]")
        try:
            special_sections = _json.loads(sections_json)
        except Exception:
            special_sections = []
        return v.new_qr_content_html(
            base_url=config.G_BASE_URL,
            url_content=url_content,
            qr_name=qr_name,
            short_code=short_code,
            special_sections=special_sections,
        )
    return v.new_qr_content_html(base_url=config.G_BASE_URL)


@app.route("/qr/new/special/qr-design", methods=["GET", "POST"])
def user_new_qr_design_special():
    import re
    import json as _json
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.view import view_special
    from pytavia_modules.qr import qr_special_proc
    v = view_special.view_special(app)
    proc = qr_special_proc.qr_special_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    special_sections = []
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        sections_json = request.form.get("special_sections", "[]")
        print(f"[DEBUG-STEP2] raw special_sections: {sections_json[:300]}")
        try:
            special_sections = _json.loads(sections_json)
            print(f"[DEBUG-STEP2] parsed sections count: {len(special_sections)}")
        except Exception as e:
            print(f"[DEBUG-STEP2] JSON parse error: {e}")
            special_sections = []
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2-32 characters: letters, numbers, '-' or '_'."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/special/" + short_code
    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code,
        qr_encode_url=qr_encode_url, error_msg=error_msg, special_sections=special_sections,
    )


@app.route("/qr/save/special", methods=["POST"])
def qr_save_special():
    """Save new special QR card."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_special_proc
    from pytavia_modules.view import view_special
    print(f"[DEBUG-STEP3] qr_save_special called, form keys: {list(request.form.keys())}")
    raw_ss = request.form.get("special_sections", "[]")
    print(f"[DEBUG-STEP3] raw special_sections: {raw_ss[:300]}")
    response = qr_special_proc.qr_special_proc(app).complete_special_save(request, session, app.root_path)
    print(f"[DEBUG-STEP3] save response success: {response.get('success')}")
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        return redirect(url_for("user_qr_list"))
    return view_special.view_special(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        special_sections=response.get("special_sections", []),
    )

@app.route("/qr/special/upload-image", methods=["POST"])
def qr_special_upload_image():
    """API endpoint to handle image uploads from the HTML editor in Special QR."""
    import os
    import uuid as _uuid
    import re as _re
    from flask import request, jsonify

    if "fk_user_id" not in session:
        return jsonify({"success": False, "message": "unauthorized"}), 401
    
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "No file uploaded"}), 400
        
    file.seek(0, 2)
    if file.tell() > 2 * 1024 * 1024:
        return jsonify({"success": False, "message": "File too large (max 2MB)"}), 400
    file.seek(0)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
        return jsonify({"success": False, "message": "Invalid file type"}), 400
        
    safe_name = _re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename)
    if ".." in safe_name: safe_name = safe_name.replace("..", "_")
    
    # Prepend uuid to avoid collisions in same day
    unique_name = _uuid.uuid4().hex[:8] + "_" + safe_name
    
    # Upload to R2 under special/images/
    _r2 = r2_mod.r2_storage_proc()
    r2_key = f"special/images/{unique_name}"
    file_url = _r2.upload_file(file, r2_key, track_meta={"fk_user_id": session.get("fk_user_id"), "qrcard_id": None, "qr_type": "special", "file_name": file.filename})

    return jsonify({
        "success": True,
        "file": {
            "url": file_url,
            "original_filename": file.filename
        }
    })


@app.route("/qr/update/special/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_special(qrcard_id):
    """Edit content step for special QR."""
    import json as _json
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_special_proc
    from pytavia_modules.view import view_update_special
    proc = qr_special_proc.qr_special_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        if request.form.get("back_from_design"):
            url_content = (request.form.get("url_content") or "").strip()
            qr_name = (request.form.get("qr_name") or "").strip()
            short_code = (request.form.get("short_code") or "").strip()
            sections_json = request.form.get("special_sections", "[]")
            try:
                special_sections = _json.loads(sections_json)
            except Exception:
                special_sections = qrcard.get("special_sections", [])
            draft = dict(qrcard)
            draft["url_content"] = url_content or draft.get("url_content", "")
            draft["name"] = qr_name or draft.get("name", "")
            draft["short_code"] = short_code or draft.get("short_code", "")
            return view_update_special.view_update_special(app).update_qr_content_html(
                qrcard=draft, base_url=config.G_BASE_URL,
                url_content=draft.get("url_content", "QRkartu"),
                qr_name=draft.get("name", ""),
                short_code=draft.get("short_code", ""),
                special_sections=special_sections,
            )
        # Normal POST: content -> design
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "").strip()
        short_code = request.form.get("short_code", "").strip()
        sections_json = request.form.get("special_sections", "[]")
        try:
            special_sections = _json.loads(sections_json)
        except Exception:
            special_sections = []
        extra_data = {"special_sections": special_sections}
        if request.form.get("scan_limit_enabled"):
            extra_data["scan_limit_enabled"] = True
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        if raw_limit.isdigit():
            extra_data["scan_limit_value"] = int(raw_limit)

        extra_data["welcome_bg_color"] = request.form.get("welcome_bg_color", "#2F6BFD")
        extra_data["welcome_time"] = request.form.get("welcome_time", "2.5")

        import os, re as _re
        _r2 = r2_mod.r2_storage_proc()
        if request.form.get("welcome_img_delete") == "1":
            qrcard["welcome_img_url"] = ""
            extra_data["welcome_img_url"] = ""
            try:
                from pytavia_core import database as _db_w, config as _cfg_w
                _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
                _mgd.db_qrcard_special.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            except Exception: pass
        else:
            welcome_img = request.files.get("special_welcome_img")
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    safe_name = _re.sub(r"[^a-zA-Z0-9_.-]", "_", welcome_img.filename)
                    welcome_name = f"welcome_{int(time.time())}_{safe_name}"
                    r2_key = f"special/{qrcard_id}/{welcome_name}"
                    welcome_url = _r2.upload_file(welcome_img, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "special"})
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    try:
                        from pytavia_core import database as _db_w, config as _cfg_w
                        _mgd = _db_w.get_db_conn(_cfg_w.mainDB)
                        _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                        _mgd.db_qrcard_special.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    except Exception: pass
            elif qrcard.get("welcome_img_url"):
                extra_data["welcome_img_url"] = qrcard["welcome_img_url"]

        _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, extra_data)
        return redirect(url_for("qr_update_design_special", qrcard_id=qrcard_id))
    # GET: show content form
    special_sections = qrcard.get("special_sections", [])
    return view_update_special.view_update_special(app).update_qr_content_html(
        qrcard=qrcard, base_url=config.G_BASE_URL,
        url_content=qrcard.get("url_content", "QRkartu"),
        qr_name=qrcard.get("name", ""),
        short_code=qrcard.get("short_code", ""),
        special_sections=special_sections,
    )


@app.route("/qr/update/special/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_special(qrcard_id):
    """Edit design step for special QR."""
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_special_proc
    from pytavia_modules.view import view_update_special
    proc = qr_special_proc.qr_special_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    draft = _get_qr_draft(session, qrcard_id)
    if draft:
        qrcard.update(draft)
        url_content = draft.get("url_content") or qrcard.get("url_content") or "QRkartu"
        qr_name = draft.get("qr_name") or qrcard.get("name") or "Untitled QR"
        special_sections = draft.get("special_sections", qrcard.get("special_sections", []))
    else:
        url_content = qrcard.get("url_content") or "QRkartu"
        qr_name = qrcard.get("name") or "Untitled QR"
        special_sections = qrcard.get("special_sections", [])
    qr_encode_url = config.G_BASE_URL + "/special/" + qrcard["short_code"] if qrcard.get("short_code") else None
    return view_update_special.view_update_special(app).update_qr_design_html(
        qrcard=qrcard, url_content=url_content, qr_name=qr_name, qr_encode_url=qr_encode_url,
        special_sections=special_sections,
    )


@app.route("/qr/update/save/special/<qrcard_id>", methods=["POST"])
def qr_update_save_special(qrcard_id):
    """Save special QR update."""
    import json as _json
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    draft = _get_qr_draft(session, qrcard_id) or {}
    url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
    short_code = (request.form.get("short_code") or "").strip().lower() or (draft.get("short_code") or "").strip().lower()
    # Get special_sections from draft or from form hidden input
    import json as _json_save
    special_sections = draft.get("special_sections", [])
    if not special_sections:
        # Fallback: read from the design form's hidden input
        raw_ss = request.form.get("special_sections", "[]")
        try:
            special_sections = _json_save.loads(raw_ss)
            if not isinstance(special_sections, list):
                special_sections = []
        except Exception:
            special_sections = []
    from pytavia_modules.qr import qr_special_proc
    proc = qr_special_proc.qr_special_proc(app)
    params = {
        "fk_user_id": fk_user_id,
        "qrcard_id": qrcard_id,
        "name": qr_name,
        "url_content": url_content,
        "special_sections": special_sections,
    }
    if short_code:
        params["short_code"] = short_code
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _frame_id_special = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_special)
    _enc_url_special = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_special", "/special/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_special, _frame_id_special)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/new/images", methods=["GET"])
@app.route("/qr/new/images/back", methods=["POST"])
def user_new_qr_images():
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.view import view_images
    v = view_images.view_images(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        images_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    images_data[key] = val_list
                else:
                    images_data[key] = val_list[0] if val_list else ""
        
        from flask import url_for as _url_for
        tmp_gallery = session.get("images_tmp_gallery", [])
        if tmp_gallery:
            images_data["images_gallery_files"] = []
            for f_info in tmp_gallery:
                url = _url_for("static", filename=f"uploads/images/_tmp/{session.get('images_tmp_key')}/{f_info['safe_name']}")
                images_data["images_gallery_files"].append({"url": url, "name": f_info.get("name",""), "desc": f_info.get("desc","")})
        if session.get("welcome_img_tmp_key") and session.get("welcome_img_tmp_name"):
            images_data["welcome_img_url"] = _url_for("static", filename=f"uploads/images/_tmp/{session['welcome_img_tmp_key']}/{session['welcome_img_tmp_name']}")

        return v.new_qr_content_html(base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=images_data)
    return v.new_qr_content_html(base_url=config.G_BASE_URL)

@app.route("/qr/new/images/qr-design", methods=["GET", "POST"])
def user_new_qr_design_images():
    from flask import request
    import os
    import re
    import uuid as _uuid
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.view import view_images
    from pytavia_modules.qr import qr_images_proc
    v = view_images.view_images(app)
    proc = qr_images_proc.qr_images_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    images_data = {}
    
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "images_files"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): images_data[key] = val_list
                else: images_data[key] = val_list[0] if val_list else ""
                
        tmp_key = session.get("images_tmp_key") or _uuid.uuid4().hex
        session["images_tmp_key"] = tmp_key
        _r2 = r2_mod.r2_storage_proc()
        session.modified = True

        files = request.files.getlist("images_files")
        images_names = request.form.getlist("images_name[]")
        images_descs = request.form.getlist("images_desc[]")

        tmp_gallery = session.get("images_tmp_gallery", [])
        new_file_offset = len(tmp_gallery)
        for i, f in enumerate(files):
            if f and f.filename and f.filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                f.seek(0, 2)
                if f.tell() <= 2 * 1024 * 1024:
                    f.seek(0)
                    ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
                    safe_name = _uuid.uuid4().hex + ext
                    _r2.upload_file(f, f"images/_tmp/{tmp_key}/{safe_name}")
                    form_idx = new_file_offset + i
                    name = images_names[form_idx] if form_idx < len(images_names) else ""
                    desc = images_descs[form_idx] if form_idx < len(images_descs) else ""
                    tmp_gallery.append({"safe_name": safe_name, "name": name, "desc": desc})
                else:
                    error_msg = f"Image {f.filename} exceeds 2MB limit."
        
        # Update existing items in the gallery
        for i in range(min(len(tmp_gallery), len(images_names))):
            tmp_gallery[i]["name"] = images_names[i]
            if i < len(images_descs): tmp_gallery[i]["desc"] = images_descs[i]
            
        session["images_tmp_gallery"] = tmp_gallery
        session["images_autocomplete_urls"] = request.form.getlist("images_autocomplete_urls[]")
        session["images_autocomplete_names"] = request.form.getlist("images_autocomplete_names[]")
        session["images_autocomplete_descs"] = request.form.getlist("images_autocomplete_descs[]")
        session.modified = True

        # Welcome image
        welcome_img = request.files.get("images_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                _wext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if _wext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    _wext = ".jpg"
                _r2.upload_file(welcome_img, f"images/_tmp/{tmp_key}/welcome{_wext}")
                session["welcome_img_tmp_key"] = tmp_key
                session["welcome_img_tmp_name"] = "welcome" + _wext
                session.modified = True
            else:
                error_msg = "Welcome image must be 1 MB or smaller."
        elif request.form.get("images_welcome_img_delete") == "1":
            session.pop("welcome_img_tmp_key", None)
            session.pop("welcome_img_tmp_name", None)
            session.modified = True

        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=images_data)

        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=images_data)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=images_data)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=images_data)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/images/" + short_code
        
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, images_data=images_data)

@app.route("/qr/save/images", methods=["POST"])
def qr_save_images():
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_images_proc
    from pytavia_modules.view import view_images
    response = qr_images_proc.qr_images_proc(app).complete_images_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        return redirect(url_for("user_qr_list"))
    return view_images.view_images(app).new_qr_design_html(
        url_content=response.get("url_content", ""), qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""), qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed.")
    )

def _get_video_embed_url(url):
    import re
    url = url.strip()
    yt_match = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    if yt_match:
        return f"https://www.youtube.com/embed/{yt_match.group(1)}"
    vm_match = re.search(r'vimeo\.com\/(?:.*#|.*\/videos\/)?([0-9]+)', url)
    if vm_match:
        return f"https://player.vimeo.com/video/{vm_match.group(1)}"
    return url

@app.route("/qr/new/video", methods=["GET"])
@app.route("/qr/new/video/back", methods=["POST"])
def user_new_qr_video():
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from flask import request
    from pytavia_modules.view import view_video
    v = view_video.view_video(app)
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        video_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    video_data[key] = val_list
                else:
                    video_data[key] = val_list[0] if val_list else ""
        
        return v.new_qr_content_html(base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, video_data=video_data)
    return v.new_qr_content_html(base_url=config.G_BASE_URL)

@app.route("/qr/new/video/qr-design", methods=["GET", "POST"])
def user_new_qr_design_video():
    from flask import request
    import os
    import re
    import uuid as _uuid
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.view import view_video
    from pytavia_modules.qr import qr_video_proc
    v = view_video.view_video(app)
    proc = qr_video_proc.qr_video_proc(app)
    url_content = "QRkartu"
    qr_name = "Untitled QR"
    short_code = ""
    qr_encode_url = None
    error_msg = None
    video_data = {}
    
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()
        
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"]:
                if key in ["video_type[]", "video_url[]", "video_name[]", "video_desc[]"]: continue
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): video_data[key] = val_list
                else: video_data[key] = val_list[0] if val_list else ""
                
        video_types = request.form.getlist("video_type[]")
        video_urls = request.form.getlist("video_url[]")
        video_names = request.form.getlist("video_name[]")
        video_descs = request.form.getlist("video_desc[]")
        video_files = request.files.getlist("video_files")
        
        tmp_key = session.get("video_tmp_key") or _uuid.uuid4().hex
        session["video_tmp_key"] = tmp_key
        _r2 = r2_mod.r2_storage_proc()
        session.modified = True

        tmp_gallery = []
        file_idx = 0

        if not video_types and video_urls:
            video_types = ['link'] * len(video_urls)

        for i, vtype in enumerate(video_types):
            url = video_urls[i] if i < len(video_urls) else ""
            name = video_names[i] if i < len(video_names) else ""
            desc = video_descs[i] if i < len(video_descs) else ""

            if vtype == 'upload':
                if file_idx < len(video_files):
                    f = video_files[file_idx]
                    file_idx += 1
                    if f and f.filename:
                        f.seek(0, 2)
                        if f.tell() <= 50 * 1024 * 1024:
                            f.seek(0)
                            ext = os.path.splitext(f.filename)[1].lower() or ".mp4"
                            safe_name = _uuid.uuid4().hex + ext
                            _r2.upload_file(f, f"videos/_tmp/{tmp_key}/{safe_name}")
                            tmp_gallery.append({"type": "upload", "safe_name": safe_name, "name": name.strip(), "desc": desc.strip()})
                        else:
                            error_msg = f"Video {f.filename} exceeds 50MB limit."
            else:
                if url.strip():
                    embed_url = _get_video_embed_url(url.strip())
                    tmp_gallery.append({"type": "link", "url": embed_url, "name": name.strip(), "desc": desc.strip()})
                    
        session["video_tmp_gallery"] = tmp_gallery

        # ── Welcome image upload ──
        if request.form.get("video_welcome_img_delete") == "1":
            session.pop("video_welcome_img_tmp_key", None)
            session.pop("video_welcome_img_tmp_name", None)
            video_data["welcome_img_url"] = ""
        else:
            welcome_img_file = request.files.get("video_welcome_img")
            if welcome_img_file and welcome_img_file.filename:
                welcome_img_file.seek(0, 2)
                if welcome_img_file.tell() <= 1 * 1024 * 1024:
                    welcome_img_file.seek(0)
                    import os as _os
                    _wext = _os.path.splitext(welcome_img_file.filename)[1].lower() or ".jpg"
                    _wkey = session.get("video_welcome_img_tmp_key") or _uuid.uuid4().hex
                    session["video_welcome_img_tmp_key"] = _wkey
                    session["video_welcome_img_tmp_name"] = "welcome" + _wext
                    _r2.upload_file(welcome_img_file, f"video/_tmp/{_wkey}/welcome{_wext}")
                else:
                    error_msg = "Welcome image exceeds 1 MB limit."
            # Preserve existing URL if already uploaded previously
            existing_url = session.get("video_welcome_img_url", "")
            if existing_url:
                video_data["welcome_img_url"] = existing_url
        session.modified = True

        if error_msg:
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, video_data=video_data)
            
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, video_data=video_data)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, video_data=video_data)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, video_data=video_data)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/video/" + short_code
        
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, video_data=video_data)

@app.route("/qr/save/video", methods=["POST"])
def qr_save_video():
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_video_proc
    from pytavia_modules.view import view_video
    response = qr_video_proc.qr_video_proc(app).complete_video_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        return redirect(url_for("user_qr_list"))
    return view_video.view_video(app).new_qr_design_html(
        url_content=response.get("url_content", ""), qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""), qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed.")
    )


@app.route("/qr/update/images/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_images(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_images_proc as _qrp
    from pytavia_modules.view import view_update_images
    proc = _qrp.qr_images_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard: return redirect(url_for("user_qr_list"))
    qrcard = _merge_images_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    
    if request.method == "POST":
        if request.form.get("back_from_design"):
            existing_draft = _get_qr_draft(session, qrcard_id) or {}
            short_code = request.form.get("short_code", "").strip() or qrcard.get("short_code")
            return view_update_images.view_update_images(app).update_qr_content_html(
                qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"),
                short_code=short_code, base_url=config.G_BASE_URL
            )
            
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        images_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design", "images_files"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): images_data[key] = val_list
                else: images_data[key] = val_list[0] if val_list else ""
                
        import os, uuid as _uuid
        _r2 = r2_mod.r2_storage_proc()

        new_files = request.files.getlist("images_files")
        images_names = request.form.getlist("images_name[]")
        images_descs = request.form.getlist("images_desc[]")
        existing_urls = request.form.getlist("images_existing_url[]")
        autocomplete_urls = request.form.getlist("images_autocomplete_urls[]")
        autocomplete_names = request.form.getlist("images_autocomplete_names[]")
        autocomplete_descs = request.form.getlist("images_autocomplete_descs[]")

        db_files = list(qrcard.get("images_gallery_files", []))
        db_map = {f.get("url"): dict(f) for f in db_files}

        updated_gallery = []
        for i, url in enumerate(existing_urls):
            entry = db_map.get(url, {"url": url})
            if i < len(images_names): entry["name"] = images_names[i]
            if i < len(images_descs): entry["desc"] = images_descs[i]
            updated_gallery.append(entry)

        new_file_offset = len(existing_urls)
        for i, f in enumerate(new_files):
            if f and f.filename and f.filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                f.seek(0, 2)
                if f.tell() <= 2 * 1024 * 1024:
                    f.seek(0)
                    ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
                    safe_name = _uuid.uuid4().hex + ext
                    r2_key = f"images/{qrcard_id}/{safe_name}"
                    file_url = _r2.upload_file(f, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "images", "file_name": safe_name})
                    form_idx = new_file_offset + i
                    name = images_names[form_idx] if form_idx < len(images_names) else ""
                    desc = images_descs[form_idx] if form_idx < len(images_descs) else ""
                    updated_gallery.append({
                        "url": file_url,
                        "name": name,
                        "desc": desc
                    })

        # Assets picked from "My Assets" gallery picker
        for i, ac_url in enumerate(autocomplete_urls):
            if not ac_url:
                continue
            entry = {"url": ac_url}
            if i < len(autocomplete_names):
                entry["name"] = autocomplete_names[i]
            if i < len(autocomplete_descs):
                entry["desc"] = autocomplete_descs[i]
            updated_gallery.append(entry)
                    
        qrcard["images_gallery_files"] = updated_gallery
        images_data["images_gallery_files"] = updated_gallery

        # Welcome image handling (upload / delete / pick-from-assets)
        _welcome_delete = request.form.get("images_welcome_img_delete") == "1"
        _welcome_img = request.files.get("images_welcome_img")
        _welcome_asset_url = (request.form.get("images_welcome_img_autocomplete_url") or "").strip()
        if _welcome_delete:
            images_data["welcome_img_url"] = ""
            qrcard["welcome_img_url"] = ""
        elif _welcome_img and _welcome_img.filename:
            _welcome_img.seek(0, 2)
            _welcome_size = _welcome_img.tell()
            _welcome_img.seek(0)
            if _welcome_size <= 1024 * 1024:
                _ext = os.path.splitext(_welcome_img.filename)[1].lower() or ".jpg"
                if _ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    _ext = ".jpg"
                _safe = "welcome_" + _uuid.uuid4().hex[:12] + _ext
                _key = f"images/{qrcard_id}/{_safe}"
                _welcome_url = _r2.upload_file(_welcome_img, _key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "images", "file_name": _safe})
                images_data["welcome_img_url"] = _welcome_url
                qrcard["welcome_img_url"] = _welcome_url
        elif _welcome_asset_url:
            images_data["welcome_img_url"] = _welcome_asset_url
            qrcard["welcome_img_url"] = _welcome_asset_url
        
        # Save straight to DB so design step has it
        try:
            database.get_db_conn(config.mainDB).db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"images_gallery_files": updated_gallery}})
            database.get_db_conn(config.mainDB).db_qrcard_images.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"images_gallery_files": updated_gallery}}, upsert=True)
            if "welcome_img_url" in images_data:
                database.get_db_conn(config.mainDB).db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": images_data.get("welcome_img_url", "")}},
                )
                database.get_db_conn(config.mainDB).db_qrcard_images.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": images_data.get("welcome_img_url", "")}},
                    upsert=True,
                )
        except Exception: pass
        
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), images_data)
        qrcard.update(images_data)

        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_images.view_update_images(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists.", base_url=config.G_BASE_URL
            )

        if request.form.get("reset_qr_style") == "1":
            _unset_fields = {"qr_composite_url": "", "qr_image_url": "", "qr_dot_style": "", "qr_corner_style": "", "qr_dot_color": "", "qr_bg_color": "", "card_bg_color": ""}
            database.get_db_conn(config.mainDB).db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$unset": _unset_fields}
            )
            database.get_db_conn(config.mainDB).db_qrcard_images.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$unset": {"qr_composite_url": "", "qr_image_url": ""}}
            )

        return redirect(url_for("qr_update_design_images", qrcard_id=qrcard_id))
    
    draft = _get_qr_draft(session, qrcard_id)
    if draft: qrcard.update(draft)
    from pytavia_modules.view import view_update_images
    return view_update_images.view_update_images(app).update_qr_content_html(
        qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"),
        short_code=qrcard.get("short_code") or None, base_url=config.G_BASE_URL
    )

@app.route("/qr/update/images/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_images(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_images_proc as _qrp
    from pytavia_modules.view import view_update_images
    proc = _qrp.qr_images_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard: return redirect(url_for("user_qr_list"))
    qrcard = _merge_images_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        images_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): images_data[key] = val_list
                else: images_data[key] = val_list[0] if val_list else ""
                
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), images_data)
        qrcard.update(images_data)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft: qrcard.update(draft)
        
    qr_encode_url = config.G_BASE_URL + "/images/" + (qrcard["short_code"] if qrcard.get("short_code") else "")
    return view_update_images.view_update_images(app).update_qr_design_html(
        qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"), qr_encode_url=qr_encode_url
    )

@app.route("/qr/update/save/images/<qrcard_id>", methods=["POST"])
def qr_update_save_images(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    draft = _get_qr_draft(session, qrcard_id) or {}
    url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
    short_code = (request.form.get("short_code") or "").strip().lower() or (draft.get("short_code") or "").strip().lower()
    
    from pytavia_modules.qr import qr_images_proc
    proc = qr_images_proc.qr_images_proc(app)
    params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "name": qr_name, "url_content": url_content}
    if short_code: params["short_code"] = short_code
    
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    
    for key in request.form:
        if key not in ["csrf_token", "url_content", "qr_name", "short_code", "scan_limit_enabled", "scan_limit_value"]:
            val_list = request.form.getlist(key)
            if len(val_list) > 1 or key.endswith("[]"): params[key] = val_list
            else: params[key] = val_list[0] if val_list else ""
            
    for key, val in draft.items():
        if key not in params and key not in ["url_content", "qr_name", "short_code"]:
            params[key] = val
            
    _hl_raw = request.form.get("images_hide_labels") if "images_hide_labels" in request.form else params.get("images_hide_labels", "")
    params["images_hide_labels"] = str(_hl_raw or "").lower() in ("on", "true", "1", "yes")
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _frame_id_images = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_images)
    _enc_url_images = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_images", "/images/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_images, _frame_id_images)
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/video/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_video(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_video_proc as _qrp
    from pytavia_modules.view import view_update_video
    proc = _qrp.qr_video_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard: return redirect(url_for("user_qr_list"))
    qrcard = _merge_video_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    
    if request.method == "POST":
        if request.form.get("back_from_design"):
            existing_draft = _get_qr_draft(session, qrcard_id) or {}
            short_code = request.form.get("short_code", "").strip() or qrcard.get("short_code")
            return view_update_video.view_update_video(app).update_qr_content_html(
                qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"),
                short_code=short_code, base_url=config.G_BASE_URL
            )
            
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        video_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                if key in ["video_type[]", "video_url[]", "video_name[]", "video_desc[]"]: continue
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): video_data[key] = val_list
                else: video_data[key] = val_list[0] if val_list else ""
                
        import os, uuid as _uuid
        _r2 = r2_mod.r2_storage_proc()

        # Welcome image handling (upload / delete / pick-from-assets)
        _welcome_delete = request.form.get("video_welcome_img_delete") == "1"
        _welcome_img = request.files.get("video_welcome_img")
        _welcome_asset_url = (request.form.get("video_welcome_img_autocomplete_url") or "").strip()
        if _welcome_delete:
            video_data["welcome_img_url"] = ""
            qrcard["welcome_img_url"] = ""
            try:
                database.get_db_conn(config.mainDB).db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": ""}},
                )
                database.get_db_conn(config.mainDB).db_qrcard_video.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": ""}},
                    upsert=True,
                )
            except Exception:
                pass
        elif _welcome_img and _welcome_img.filename:
            _welcome_img.seek(0, 2)
            _welcome_size = _welcome_img.tell()
            _welcome_img.seek(0)
            if _welcome_size <= 1024 * 1024:
                _ext = os.path.splitext(_welcome_img.filename)[1].lower() or ".jpg"
                if _ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    _ext = ".jpg"
                _safe = "welcome_" + _uuid.uuid4().hex[:12] + _ext
                _key = f"video/{qrcard_id}/{_safe}"
                _welcome_url = _r2.upload_file(
                    _welcome_img,
                    _key,
                    track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "video", "file_name": _safe},
                )
                video_data["welcome_img_url"] = _welcome_url
                qrcard["welcome_img_url"] = _welcome_url
                try:
                    database.get_db_conn(config.mainDB).db_qrcard.update_one(
                        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                        {"$set": {"welcome_img_url": _welcome_url}},
                    )
                    database.get_db_conn(config.mainDB).db_qrcard_video.update_one(
                        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                        {"$set": {"welcome_img_url": _welcome_url}},
                        upsert=True,
                    )
                except Exception:
                    pass
        elif _welcome_asset_url:
            video_data["welcome_img_url"] = _welcome_asset_url
            qrcard["welcome_img_url"] = _welcome_asset_url
            try:
                database.get_db_conn(config.mainDB).db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": _welcome_asset_url}},
                )
                database.get_db_conn(config.mainDB).db_qrcard_video.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$set": {"welcome_img_url": _welcome_asset_url}},
                    upsert=True,
                )
            except Exception:
                pass

        video_files = request.files.getlist("video_files")
        video_types = request.form.getlist("video_type[]")
        video_urls = request.form.getlist("video_url[]")
        video_names = request.form.getlist("video_name[]")
        video_descs = request.form.getlist("video_desc[]")

        updated_links = []
        file_idx = 0

        if not video_types and video_urls:
            video_types = ['link'] * len(video_urls)

        for i, vtype in enumerate(video_types):
            url = video_urls[i] if i < len(video_urls) else ""
            name = video_names[i] if i < len(video_names) else ""
            desc = video_descs[i] if i < len(video_descs) else ""

            if vtype == 'upload':
                if url.strip() and not url.startswith('/static/uploads/'):
                    # existing R2 URL — keep as-is
                    updated_links.append({"url": url, "name": name.strip(), "desc": desc.strip()})
                elif url.startswith('/static/uploads/'):
                    updated_links.append({"url": url, "name": name.strip(), "desc": desc.strip()})
                else:
                    if file_idx < len(video_files):
                        f = video_files[file_idx]
                        file_idx += 1
                        if f and f.filename:
                            f.seek(0, 2)
                            if f.tell() <= 50 * 1024 * 1024:
                                f.seek(0)
                                ext = os.path.splitext(f.filename)[1].lower() or ".mp4"
                                safe_name = _uuid.uuid4().hex + ext
                                r2_key = f"videos/{qrcard_id}/{safe_name}"
                                file_url = _r2.upload_file(f, r2_key, track_meta={"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "video", "file_name": safe_name})
                                updated_links.append({"url": file_url, "name": name.strip(), "desc": desc.strip()})
            else:
                if url.strip():
                    embed_url = _get_video_embed_url(url.strip())
                    updated_links.append({"url": embed_url, "name": name.strip(), "desc": desc.strip()})
                    
        qrcard["video_links"] = updated_links
        video_data["video_links"] = updated_links
        
        # Save straight to DB so design step has it
        try:
            database.get_db_conn(config.mainDB).db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"video_links": updated_links}})
            database.get_db_conn(config.mainDB).db_qrcard_video.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"video_links": updated_links}}, upsert=True)
        except Exception: pass
        
        if not proc.is_name_unique(fk_user_id, qr_name, exclude_id=qrcard_id):
            return view_update_video.view_update_video(app).update_qr_content_html(
                qrcard=qrcard, error_msg="A QR card with this name already exists.", base_url=config.G_BASE_URL
            )

        if request.form.get("reset_qr_style") == "1":
            database.get_db_conn(config.mainDB).db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": {"qr_image_url": "", "qr_composite_url": "",
                            "qr_dot_style": "", "qr_corner_style": "",
                            "qr_dot_color": "", "qr_bg_color": ""}},
            )
            qrcard.pop("qr_image_url", None)
            qrcard.pop("qr_composite_url", None)

        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), video_data)
        qrcard.update(video_data)

        return redirect(url_for("qr_update_design_video", qrcard_id=qrcard_id))
    
    draft = _get_qr_draft(session, qrcard_id)
    if draft: qrcard.update(draft)
    from pytavia_modules.view import view_update_video
    return view_update_video.view_update_video(app).update_qr_content_html(
        qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"),
        short_code=qrcard.get("short_code") or None, base_url=config.G_BASE_URL
    )

@app.route("/qr/update/video/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_video(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_video_proc as _qrp
    from pytavia_modules.view import view_update_video
    proc = _qrp.qr_video_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard: return redirect(url_for("user_qr_list"))
    qrcard = _merge_video_into_qrcard(database.get_db_conn(config.mainDB), fk_user_id, qrcard_id, qrcard)
    
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
            
        video_data = {}
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "back_from_design"]:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): video_data[key] = val_list
                else: video_data[key] = val_list[0] if val_list else ""
                
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), video_data)
        qrcard.update(video_data)
        qrcard["url_content"] = url_content
        qrcard["name"] = qr_name
    else:
        draft = _get_qr_draft(session, qrcard_id)
        if draft: qrcard.update(draft)
        
    qr_encode_url = config.G_BASE_URL + "/video/" + (qrcard["short_code"] if qrcard.get("short_code") else "")
    return view_update_video.view_update_video(app).update_qr_design_html(
        qrcard=qrcard, url_content=qrcard.get("url_content"), qr_name=qrcard.get("name"), qr_encode_url=qr_encode_url
    )

@app.route("/qr/update/save/video/<qrcard_id>", methods=["POST"])
def qr_update_save_video(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    draft = _get_qr_draft(session, qrcard_id) or {}
    url_content = (request.form.get("url_content") or "").strip() or draft.get("url_content") or ""
    if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
        url_content = "https://" + url_content
    qr_name = (request.form.get("qr_name") or "").strip() or draft.get("qr_name") or "Untitled QR"
    short_code = (request.form.get("short_code") or "").strip().lower() or (draft.get("short_code") or "").strip().lower()
    
    from pytavia_modules.qr import qr_video_proc
    proc = qr_video_proc.qr_video_proc(app)
    params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "name": qr_name, "url_content": url_content}
    if short_code: params["short_code"] = short_code
    
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    
    # Use draft values as base
    for key, val in draft.items():
        if key not in ["url_content", "qr_name", "short_code"]:
            params[key] = val

    for key in request.form:
        if key not in ["csrf_token", "url_content", "qr_name", "short_code", "scan_limit_enabled", "scan_limit_value"]:
            val_list = request.form.getlist(key)
            if len(val_list) > 1 or key.endswith("[]"): params[key] = val_list
            else: params[key] = val_list[0] if val_list else ""
            
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _frame_id_video = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_video)
    _enc_url_video = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_video", "/video/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_video, _frame_id_video)
    return redirect(url_for("user_qr_list"))


@app.route("/api/proxy_download", methods=["GET"])
def api_proxy_download():
    """Proxy-download a file from R2 or a local static path so the browser saves it."""
    from flask import request, Response, stream_with_context, send_from_directory
    import urllib.request as _ureq
    import os, re
    url  = request.args.get("url", "").strip()
    name = request.args.get("name", "").strip()
    if not url:
        return "Missing url", 400
    allowed_base = config.R2_PUBLIC_BASE_URL.rstrip("/")
    is_r2 = url.startswith(allowed_base + "/")
    is_static = url.startswith("/static/")
    if not is_r2 and not is_static:
        return "Forbidden", 403
    safe_name = re.sub(r"[^\w\-. ]", "_", name) if name else ""
    if not safe_name:
        safe_name = os.path.basename(url.split("?")[0]) or "file"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    # Serve local static files directly
    if is_static:
        static_rel = url[len("/static/"):]  # e.g. "assets/autocomplete_field_helper/pdf/..."
        static_dir = os.path.join(app.root_path, "static", os.path.dirname(static_rel))
        filename   = os.path.basename(static_rel)
        try:
            return send_from_directory(static_dir, filename, as_attachment=True,
                                       download_name=safe_name)
        except Exception:
            return "File not found", 404
    try:
        req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        remote = _ureq.urlopen(req, timeout=30)
        content_type = remote.headers.get("Content-Type", "application/pdf")
        def generate():
            while True:
                chunk = remote.read(65536)
                if not chunk:
                    break
                yield chunk
        headers = {
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Content-Type": content_type,
        }
        return Response(stream_with_context(generate()), headers=headers)
    except Exception:
        return "Could not fetch file", 502


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

@app.route("/user/storage")
def user_storage():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.user import user_storage_proc as _usp
    info = _usp.user_storage_proc(app).get_storage_info(session["fk_user_id"])
    return render_template("user/storage.html", info=info)

@app.route("/api/user/image_assets")
def api_user_image_assets():
    """Return active image assets for the logged-in user (for asset-picker UI)."""
    if "fk_user_id" not in session:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_ia
    assets = _atp_ia().get_user_assets(session["fk_user_id"])
    images = [
        {"r2_key": a["r2_key"], "file_name": a.get("file_name", ""), "url": a.get("r2_key", "")}
        for a in assets
        if a.get("file_category") == "image" and a.get("r2_key")
    ]
    from pytavia_modules.storage.r2_storage_proc import r2_storage_proc as _r2_ia
    base = _r2_ia().public_url("")
    base = base.rstrip("/")
    for img in images:
        img["url"] = base + "/" + img["r2_key"]
    return jsonify({"ok": True, "images": images})


@app.route("/api/storage/garbage")
def api_storage_garbage():
    """Return orphaned (garbage) assets for the logged-in user."""
    if "fk_user_id" not in session:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    from pytavia_modules.user import user_storage_proc as _usp
    files = _usp.user_storage_proc(app).get_garbage_files(session["fk_user_id"])
    total = sum(f["size"] for f in files)
    from pytavia_modules.user.user_storage_proc import _fmt_size
    return jsonify({"ok": True, "files": files, "count": len(files), "total_fmt": _fmt_size(total), "total_bytes": total})


@app.route("/api/storage/cleanup_garbage", methods=["POST"])
def api_storage_cleanup_garbage():
    """Delete all orphaned assets from R2 and mark them DELETED in db_qr_assets."""
    if "fk_user_id" not in session:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    try:
        from pytavia_modules.user import user_storage_proc as _usp
        from pytavia_modules.storage import r2_storage_proc as _r2_mod
        from pytavia_modules.user import asset_tracker_proc as _atp
        from pytavia_core import database as _db_mod, config as _cfg

        fk_user_id = session["fk_user_id"]
        garbage = _usp.user_storage_proc(app).get_garbage_files(fk_user_id)
        if not garbage:
            return jsonify({"ok": True, "deleted": 0, "freed_bytes": 0, "freed_fmt": "0 B"})

        _r2 = _r2_mod.r2_storage_proc()
        tracker = _atp.asset_tracker_proc(app)
        freed_bytes = 0
        deleted = 0
        for f in garbage:
            key = f.get("r2_key", "")
            if not key:
                continue
            try:
                _r2.delete_file(key)
            except Exception:
                pass
            tracker.untrack_key(key)
            freed_bytes += f.get("size", 0)
            deleted += 1

        from pytavia_modules.user.user_storage_proc import _fmt_size
        return jsonify({"ok": True, "deleted": deleted, "freed_bytes": freed_bytes, "freed_fmt": _fmt_size(freed_bytes)})
    except Exception:
        app.logger.debug("cleanup_garbage failed", exc_info=True)
        return jsonify({"ok": False, "error": "Cleanup failed"}), 500


@app.route("/api/storage/delete_qr_assets", methods=["POST"])
def api_storage_delete_qr_assets():
    if "fk_user_id" not in session:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    try:
        data       = request.get_json(force=True) or {}
        qrcard_id  = str(data.get("qrcard_id", "")).strip()
        qr_type    = str(data.get("qr_type", "")).strip()
        if not qrcard_id or not qr_type:
            return jsonify({"ok": False, "error": "Missing qrcard_id or qr_type"}), 400

        from pytavia_core import database, config as _cfg
        _db = database.get_db_conn(_cfg.mainDB)

        # Verify the QR belongs to this user
        collection = "db_qrcard" if qr_type != "frame" else "db_qr_frame"
        id_field   = "qrcard_id" if qr_type != "frame" else "frame_id"
        record = getattr(_db, collection).find_one(
            {id_field: qrcard_id, "fk_user_id": session["fk_user_id"]}
        )
        if not record:
            return jsonify({"ok": False, "error": "QR not found"}), 404

        # Soft-delete tracked assets (no R2 deletion — deferred to admin bulk cleanup)
        from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_st2
        _atp_st2().soft_delete_qr(qrcard_id)

        # Mark QR as deleted in DB (main collection + index + type-specific)
        getattr(_db, collection).update_one(
            {id_field: qrcard_id},
            {"$set": {"status": "DELETED"}}
        )
        _db.db_qr_index.update_one(
            {"qrcard_id": qrcard_id, "fk_user_id": session["fk_user_id"]},
            {"$set": {"status": "DELETED"}}
        )
        _type_col_map = {
            "pdf": "db_qrcard_pdf",
            "web-static": "db_qrcard_web_static",
            "text": "db_qrcard_text",
            "wa-static": "db_qrcard_wa_static",
            "email-static": "db_qrcard_email_static",
            "vcard-static": "db_qrcard_vcard_static",
            "allinone": "db_qrcard_allinone",
        }
        if qr_type in _type_col_map:
            getattr(_db, _type_col_map[qr_type]).update_one(
                {"qrcard_id": qrcard_id, "fk_user_id": session["fk_user_id"]},
                {"$set": {"status": "DELETED"}}
            )

        from pytavia_modules.user import user_activity_proc as _uap_st
        _uap_st.user_activity_proc(app).log(
            fk_user_id=session["fk_user_id"],
            action="DELETE_QR_ASSETS",
            qrcard_id=qrcard_id,
            qr_name=record.get("name", ""),
            qr_type=qr_type,
            source="storage",
            detail={"note": "soft_deleted_assets_pending_r2_cleanup"},
        )

        return jsonify({"ok": True, "deleted_count": 0, "freed_bytes": 0})
    except Exception as e:
        app.logger.debug(e)
        return jsonify({"ok": False, "error": "Server error"}), 500

@app.route("/user/templates")
def user_templates():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).templates_html(fk_user_id=session["fk_user_id"])


@app.route("/user/frames/api")
def user_frames_api():
    if "fk_user_id" not in session:
        return jsonify([])
    from pytavia_modules.qr import qr_frame_proc
    frames = qr_frame_proc.qr_frame_proc(app).get_frames(session["fk_user_id"])
    result = []
    for f in frames:
        result.append({
            "frame_id": f.get("frame_id"),
            "name": f.get("name"),
            "image_url": f.get("image_url"),
            "qr_x": f.get("qr_x"),
            "qr_y": f.get("qr_y"),
            "qr_w": f.get("qr_w"),
            "qr_h": f.get("qr_h"),
        })
    return jsonify(result)


@app.route("/user/frames/save", methods=["POST"])
def user_frames_save():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_frame_proc
    fk_user_id = session["fk_user_id"]
    image_file = request.files.get("frame_image")
    name = (request.form.get("frame_name") or "").strip()
    try:
        qr_x = float(request.form.get("qr_x", 0))
        qr_y = float(request.form.get("qr_y", 0))
        qr_w = float(request.form.get("qr_w", 0))
        qr_h = float(request.form.get("qr_h", 0))
    except (ValueError, TypeError):
        return view_user.view_user(app).templates_html(
            fk_user_id=fk_user_id,
            error_msg="Invalid QR area coordinates."
        )
    if not image_file or not image_file.filename:
        return view_user.view_user(app).templates_html(
            fk_user_id=fk_user_id,
            error_msg="Please upload an image."
        )
    result = qr_frame_proc.qr_frame_proc(app).add_frame(
        fk_user_id, name, image_file, qr_x, qr_y, qr_w, qr_h, app.root_path
    )
    if not result.get("ok"):
        return view_user.view_user(app).templates_html(
            fk_user_id=fk_user_id,
            error_msg=result.get("error", "Save failed.")
        )
    return view_user.view_user(app).templates_html(
        fk_user_id=fk_user_id,
        msg="Frame saved successfully."
    )


@app.route("/user/frames/delete/<frame_id>", methods=["POST"])
def user_frames_delete(frame_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_frame_proc
    fk_user_id = session["fk_user_id"]
    qr_frame_proc.qr_frame_proc(app).delete_frame(fk_user_id, frame_id)
    return redirect(url_for("user_templates"))


@app.route("/user/settings")
def user_settings():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).settings_html()

@app.route("/user/security-history")
def user_security_history():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).security_history_html()

@app.route("/user/activity-history")
def user_activity_history():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    page = int(request.args.get("page", 1))
    return view_user.view_user(app).activity_history_html(
        fk_user_id=session["fk_user_id"], page=page
    )

@app.route("/register", methods=["GET"])
def register_view():
    return view_login.view_login().register_html()

@app.route("/auth/register", methods=["POST"])
def auth_register():
    params = request.form.to_dict()
    response = auth_proc.auth_proc(app).register(params)
    if response["message_action"] == "REGISTER_SUCCESS":
        return redirect(url_for("signup_success_view"))
    else:
        return view_login.view_login().register_html(error_msg=response["message_desc"])

@app.route("/signup-success", methods=["GET"])
def signup_success_view():
    return view_login.view_login().signup_success_html()

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
