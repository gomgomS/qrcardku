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
    client_id=os.getenv('GOOGLE_CLIENT_ID', config.GOOGLE_CLIENT_ID),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET', config.GOOGLE_CLIENT_SECRET),
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


def _get_sub_info(fk_user_id):
    """Returns subscription summary dict for a user. Used by context_processor and routes."""
    import time as _t
    try:
        from pytavia_core import database as _db_sub, config as _cfg_sub
        _db = _db_sub.get_db_conn(_cfg_sub.mainDB)
        now = int(_t.time())
        sub = _db.db_user_subscription.find_one(
            {"fk_user_id": fk_user_id, "status": "ACTIVE", "is_deleted": {"$ne": True}, "expires_at": {"$gt": now}},
            sort=[("expires_at", -1)]
        )
        if not sub:
            return {"has_active": False, "days_remaining": 0, "plan_name": "", "max_qr": 0, "max_storage_mb": 0}
        expires_at = sub.get("expires_at", 0)
        days_remaining = max(0, int((expires_at - now) / 86400))
        return {
            "has_active": True,
            "days_remaining": days_remaining,
            "plan_name": sub.get("plan_name", ""),
            "max_qr": sub.get("max_qr", 0),
            "max_storage_mb": sub.get("max_storage_mb", 0),
            "is_trial": sub.get("plan_id") == "free_trial",
        }
    except Exception:
        return {"has_active": False, "days_remaining": 0, "plan_name": "", "max_qr": 0, "max_storage_mb": 0}

def _get_user_qr_quota(fk_user_id):
    """Return accumulated QR quota across ALL active subscriptions + current usage."""
    import time as _t
    try:
        _db = database.get_db_conn(config.mainDB)
        now = int(_t.time())
        subs = list(_db.db_user_subscription.find(
            {"fk_user_id": fk_user_id, "status": "ACTIVE", "is_deleted": {"$ne": True}, "expires_at": {"$gt": now}}
        ))
        total_max_qr = sum(s.get("max_qr", 0) for s in subs)
        used_qr = _db.db_qr_index.count_documents(
            {"fk_user_id": fk_user_id, "status": {"$nin": ["DELETED", "SOFT_DELETED", "DRAFT"]}}
        )
        remaining = max(0, total_max_qr - used_qr)
        return {
            "total_max_qr": total_max_qr,
            "used_qr": used_qr,
            "remaining_qr": remaining,
            "has_active": len(subs) > 0,
            "exceeded": used_qr >= total_max_qr if total_max_qr > 0 else True,
        }
    except Exception:
        return {"total_max_qr": 0, "used_qr": 0, "remaining_qr": 0, "has_active": False, "exceeded": True}


_QR_TYPE_COLLECTION_MAP = {
    "pdf": "db_qrcard_pdf",
    "web-static": "db_qrcard_web_static",
    "text": "db_qrcard_text",
    "wa-static": "db_qrcard_wa_static",
    "email-static": "db_qrcard_email_static",
    "vcard-static": "db_qrcard_vcard_static",
    "allinone": "db_qrcard_allinone",
    "images": "db_qrcard_images",
    "video": "db_qrcard_video",
    "special": "db_qrcard_special",
}


def _sync_user_qr_activation_quota(fk_user_id, mgdDB=None):
    """
    Keep only the newest QRs ACTIVE according to currently available QR quota.
    This runs on backend so expired subscriptions automatically deactivate excess QRs.
    """
    import time as _t
    try:
        _db = mgdDB or database.get_db_conn(config.mainDB)
        now = int(_t.time())

        _db.db_user_subscription.update_many(
            {"fk_user_id": fk_user_id, "status": "ACTIVE", "expires_at": {"$lt": now, "$gt": 0}},
            {"$set": {"status": "EXPIRED"}},
        )

        subs = list(_db.db_user_subscription.find(
            {"fk_user_id": fk_user_id, "status": "ACTIVE", "is_deleted": {"$ne": True}, "expires_at": {"$gt": now}},
            {"_id": 0, "max_qr": 1},
        ))
        total_max_qr = sum(int(s.get("max_qr", 0) or 0) for s in subs)

        qr_docs = list(_db.db_qr_index.find(
            {"fk_user_id": fk_user_id, "status": {"$in": ["ACTIVE", "INACTIVE"]}},
            {"_id": 0, "qrcard_id": 1, "qr_type": 1, "status": 1, "timestamp": 1},
        ).sort("timestamp", -1))

        allowed_ids = set(d.get("qrcard_id") for d in qr_docs[:total_max_qr]) if total_max_qr > 0 else set()
        active_count = 0

        for doc in qr_docs:
            qrcard_id = doc.get("qrcard_id")
            if not qrcard_id:
                continue
            desired_status = "ACTIVE" if qrcard_id in allowed_ids else "INACTIVE"
            if desired_status == "ACTIVE":
                active_count += 1
            if doc.get("status") == desired_status:
                continue

            set_op = {"$set": {"status": desired_status}}
            _db.db_qr_index.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, set_op)
            _db.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, set_op)

            col_name = _QR_TYPE_COLLECTION_MAP.get(doc.get("qr_type", ""))
            if col_name:
                getattr(_db, col_name).update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    set_op,
                )

        return {
            "total_max_qr": total_max_qr,
            "active_qr": active_count,
            "allowed_ids": allowed_ids,
            "has_active": total_max_qr > 0,
        }
    except Exception:
        return {
            "total_max_qr": 0,
            "active_qr": 0,
            "allowed_ids": set(),
            "has_active": False,
        }

@app.before_request
def _check_qr_quota_on_save():
    """Block QR creation if user has exceeded their accumulated quota."""
    from flask import request as _req
    if "fk_user_id" in session:
        _sync_user_qr_activation_quota(session["fk_user_id"])
    if _req.method == "POST" and _req.path.startswith("/qr/save/"):
        if "fk_user_id" not in session:
            return
        quota = _get_user_qr_quota(session["fk_user_id"])
        if quota["exceeded"]:
            used = quota["used_qr"]
            total = quota["total_max_qr"]
            return redirect(url_for("user_new_qr",
                quota_error=f"QR slot quota exceeded ({used}/{total}). Please upgrade your plan."))

@app.context_processor
def inject_user_sub_info():
    """Inject subscription info and unread help ticket count into every template."""
    if "fk_user_id" in session:
        fk_uid = session["fk_user_id"]
        try:
            from pytavia_core import database as _db_ctx, config as _cfg_ctx
            _db_c = _db_ctx.get_db_conn(_cfg_ctx.mainDB)
            _unread = _db_c.db_support_tickets.count_documents({
                "fk_user_id": fk_uid,
                "unread_user": {"$gt": 0},
            })
        except Exception:
            _unread = 0
        return {"sub_info": _get_sub_info(fk_uid), "help_unread_count": _unread}
    return {"sub_info": {"has_active": False, "days_remaining": 0, "plan_name": "", "max_qr": 0, "max_storage_mb": 0, "is_trial": False}, "help_unread_count": 0}

@app.route("/")
def index():
    return view_landing.view_landing().html()


@app.route("/contact")
def landing_contact():
    return render_template("landing/contact.html")

@app.route("/admin")
def admin_redirect():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    return redirect(url_for("admin_admins"))

@app.route("/login", methods=["GET"])
def login_view():
    return view_login.view_login().html()

@app.route("/auth/logout")
def auth_logout():
    session.clear()
    return redirect(url_for("login_view"))

@app.route('/auth/login/<provider>')
def auth_social_login(provider):
    # Use fixed public base URL to avoid http/host mismatch
    # when running behind reverse proxy / CDN.
    base_url = (getattr(config, "G_BASE_URL", "") or "").rstrip("/")
    if provider == 'google':
        redirect_uri = (base_url + "/auth/callback/google") if base_url else url_for('auth_social_callback', provider='google', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)
    elif provider == 'linkedin':
        redirect_uri = (base_url + "/auth/callback/linkedin") if base_url else url_for('auth_social_callback', provider='linkedin', _external=True)
        return oauth.linkedin.authorize_redirect(redirect_uri)
    return abort(404)

import traceback
@app.route('/auth/callback/<provider>')
def auth_social_callback(provider):
    try:
        base_url = (getattr(config, "G_BASE_URL", "") or "").rstrip("/")
        if provider == 'google':
            redirect_uri = (base_url + "/auth/callback/google") if base_url else None
            token = oauth.google.authorize_access_token(redirect_uri=redirect_uri)
            user_info = oauth.google.parse_id_token(token, nonce=None)
            if not user_info:
                user_info = oauth.google.userinfo()
        elif provider == 'linkedin':
            redirect_uri = (base_url + "/auth/callback/linkedin") if base_url else None
            token = oauth.linkedin.authorize_access_token(redirect_uri=redirect_uri)
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


# ── Plan definitions ──────────────────────────────────────────────────────────

_PLAN_DEFAULTS = [
    {
        "plan_id": "single",
        "name": "Single",
        "price_idr": 20000,
        "period_days": 30,
        "max_qr": 1,
        "max_storage_mb": 30,
        "description": "Perfect for individuals who need one dynamic QR.",
        "features": ["1 QR card slot", "30 MB storage", "All QR types", "Scan analytics"],
        "duration_discounts": {"1": 0, "3": 20, "6": 30, "12": 50},
        "status": "ACTIVE",
    },
    {
        "plan_id": "team",
        "name": "Team",
        "price_idr": 120000,
        "period_days": 30,
        "max_qr": 10,
        "max_storage_mb": 250,
        "description": "Great for small teams managing multiple QR cards.",
        "features": ["10 QR card slots", "250 MB storage", "All QR types", "Scan analytics", "Priority support"],
        "duration_discounts": {"1": 0, "3": 20, "6": 30, "12": 50},
        "status": "ACTIVE",
    },
    {
        "plan_id": "corporate",
        "name": "Corporate",
        "price_idr": 420000,
        "period_days": 30,
        "max_qr": 40,
        "max_storage_mb": 500,
        "description": "For large organizations with high-volume QR needs.",
        "features": ["40 QR card slots", "500 MB storage", "All QR types", "Scan analytics", "Priority support", "Dedicated account manager"],
        "duration_discounts": {"1": 0, "3": 20, "6": 30, "12": 50},
        "status": "ACTIVE",
    },
]

def _get_plans_from_db(db):
    """Return all 3 plans from DB, seeding defaults if missing."""
    plans = {p["plan_id"]: p for p in db.db_plan_definition.find({}, {"_id": 0})}
    import time
    result = []
    for d in _PLAN_DEFAULTS:
        if d["plan_id"] not in plans:
            db.db_plan_definition.insert_one(dict(d, created_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), timestamp=time.time()))
            result.append(dict(d))
        else:
            result.append(plans[d["plan_id"]])
    return result


def _normalize_duration_discounts(raw):
    defaults = {"1": 0, "3": 20, "6": 30, "12": 50}
    out = dict(defaults)
    if not isinstance(raw, dict):
        return out
    for key in ("1", "3", "6", "12"):
        try:
            out[key] = max(0, min(100, int(raw.get(key, out[key]))))
        except Exception:
            out[key] = defaults[key]
    out["1"] = 0
    return out


def _build_checkout_duration_options(plan_doc):
    base_price = max(0, int(plan_doc.get("price_idr", 0)))
    base_days = max(1, int(plan_doc.get("period_days", 30)))
    discounts = _normalize_duration_discounts(plan_doc.get("duration_discounts", {}))
    options = []
    for months in (1, 3, 6, 12):
        discount_pct = discounts.get(str(months), 0)
        subtotal = base_price * months
        discount_amount = int(round(subtotal * (discount_pct / 100.0)))
        final_price = max(0, subtotal - discount_amount)
        options.append({
            "months": months,
            "discount_pct": discount_pct,
            "subtotal_idr": subtotal,
            "discount_idr": discount_amount,
            "final_price_idr": final_price,
            "period_days": base_days * months,
        })
    return options


def _find_duration_option(options, months):
    for opt in options:
        if int(opt.get("months", 0)) == int(months):
            return opt
    return None
@app.route("/admin/transactions")
def admin_transactions():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
        
    from pytavia_core import database as _db_c, config as _cfg_c
    import time
    
    _db = _db_c.get_db_conn(_cfg_c.mainDB)
    now = time.time()
    
    # System-wide auto cleanup before pulling stats
    _db.db_user_subscription.update_many(
        {"status": "ACTIVE", "expires_at": {"$lt": now, "$gt": 0}},
        {"$set": {"status": "EXPIRED"}}
    )
    _db.db_user_subscription.update_many(
        {"status": "PENDING", "timestamp": {"$lt": now - 3600}},
        {"$set": {"status": "FAILED"}}
    )
    
    transactions = list(_db.db_user_subscription.find({}, {"_id": 0}).sort("timestamp", -1))
    
    # Map Users — db_user uses 'pkey' as the user ID key (for fallback on old records)
    users = list(_db.db_user.find({}, {"_id": 0, "pkey": 1, "email": 1, "name": 1}))
    user_map = {u["pkey"]: {"email": u.get("email", ""), "name": u.get("name", "")} for u in users if "pkey" in u}
    
    for t in transactions:
        # Prefer embedded fields (stored at checkout), fallback to live lookup
        if t.get("user_email"):
            t["user_name"] = t.get("user_name") or "—"
        else:
            u_info = user_map.get(t.get("fk_user_id"), {"email": "(not found)", "name": "Unknown User"})
            t["user_email"] = u_info["email"]
            t["user_name"] = u_info["name"]
        
    return render_template("admin/transactions.html",
        transactions=transactions,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
        now=now
    )


@app.route("/admin/plans")
def admin_plans():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    plans = _get_plans_from_db(_db)
    return render_template("admin/plans.html",
        plans=plans,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )


@app.route("/admin/plans/save", methods=["POST"])
def admin_plans_save():
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    from pytavia_core import database as _db_p, config as _cfg_p
    import time
    data = request.get_json(force=True) or {}
    plan_id = str(data.get("plan_id", "")).strip()
    if plan_id not in ("single", "team", "corporate"):
        return jsonify({"ok": False, "error": "Invalid plan_id"}), 400
    _db = _db_p.get_db_conn(_cfg_p.mainDB)

    features_raw = data.get("features", [])
    if isinstance(features_raw, str):
        features_raw = [f.strip() for f in features_raw.splitlines() if f.strip()]

    duration_discounts = _normalize_duration_discounts(data.get("duration_discounts", {}))

    update = {
        "name":            str(data.get("name", "")).strip(),
        "price_idr":       max(0, int(data.get("price_idr", 0))),
        "period_days":     max(1, int(data.get("period_days", 30))),
        "max_qr":          max(0, int(data.get("max_qr", 0))),
        "max_storage_mb":  max(0, int(data.get("max_storage_mb", 0))),
        "description":     str(data.get("description", "")).strip(),
        "features":        features_raw,
        "duration_discounts": duration_discounts,
        "status":          "ACTIVE" if data.get("status") == "ACTIVE" else "INACTIVE",
        "updated_at":      time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    _db.db_plan_definition.update_one(
        {"plan_id": plan_id},
        {"$set": update},
        upsert=True,
    )
    return jsonify({"ok": True})


@app.route("/admin/subscriptions")
def admin_subscriptions():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    
    subs = list(_db.db_user_subscription.find({}, {"_id": 0}).sort("timestamp", -1))
    
    return render_template("admin/subscriptions.html",
        subscriptions=subs,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )


@app.route("/admin/subscriptions/activate/<sub_id>", methods=["POST"])
def admin_subscriptions_activate(sub_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_core import database as _db_p, config as _cfg_p
    import time
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    
    sub_record = _db.db_user_subscription.find_one({"subscription_id": sub_id})
    if sub_record and sub_record.get("status") == "PENDING":
        now_ts = int(time.time())
        period_days = sub_record.get("period_days", 30)
        expires_at = now_ts + (period_days * 86400)
        
        _db.db_user_subscription.update_one(
            {"subscription_id": sub_id},
            {"$set": {
                "status": "ACTIVE",
                "started_at": now_ts,
                "expires_at": expires_at
            }}
        )
    return redirect(url_for("admin_subscriptions"))



@app.route("/admin/active-users")
def admin_active_users():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    import time as _t
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    now = int(_t.time())

    # Find user_ids that have at least one currently-active subscription
    active_subs = list(_db.db_user_subscription.find(
        {"status": "ACTIVE", "is_deleted": {"$ne": True}, "expires_at": {"$gt": now}},
        {"fk_user_id": 1}
    ))
    active_user_ids = list({s["fk_user_id"] for s in active_subs if s.get("fk_user_id")})

    if not active_user_ids:
        return render_template("admin/active_users.html", users=[], **{
            "admin_name": session.get("admin_name", ""),
            "admin_email": session.get("admin_email", ""),
            "admin_role": session.get("admin_role", ""),
        })

    # Fetch user records
    users_raw = {
        u["fk_user_id"]: u
        for u in _db.db_user.find(
            {"fk_user_id": {"$in": active_user_ids}, "is_deleted": {"$ne": True}},
            {"_id": 0, "fk_user_id": 1, "username": 1, "name": 1, "email": 1, "status": 1, "timestamp": 1}
        )
    }

    # Aggregate subscription data per user
    all_subs = list(_db.db_user_subscription.find(
        {"fk_user_id": {"$in": active_user_ids}},
        {"_id": 0, "fk_user_id": 1, "status": 1, "price_paid_idr": 1, "expires_at": 1, "started_at": 1, "timestamp": 1}
    ))

    # Aggregate QR index data per user
    qr_index_pipeline = [
        {"$match": {"fk_user_id": {"$in": active_user_ids}, "status": {"$nin": ["DELETED", "SOFT_DELETED"]}}},
        {"$group": {"_id": "$fk_user_id", "qr_count": {"$sum": 1}}}
    ]
    qr_counts = {r["_id"]: r["qr_count"] for r in _db.db_qr_index.aggregate(qr_index_pipeline)}

    # Aggregate total scans per user from db_qrcard
    scan_pipeline = [
        {"$match": {"fk_user_id": {"$in": active_user_ids}}},
        {"$group": {"_id": "$fk_user_id", "total_scans": {"$sum": "$stats.scan_count"}}}
    ]
    scan_counts = {r["_id"]: r["total_scans"] for r in _db.db_qrcard.aggregate(scan_pipeline)}

    # Build per-user summary
    sub_map = {}
    for s in all_subs:
        uid = s["fk_user_id"]
        if uid not in sub_map:
            sub_map[uid] = {"total_pkgs": 0, "active_pkgs": 0, "expired_pkgs": 0,
                            "total_spent": 0, "first_purchase": 0}
        sub_map[uid]["total_pkgs"] += 1
        sub_map[uid]["total_spent"] += s.get("price_paid_idr", 0)
        ts = s.get("timestamp") or s.get("started_at") or 0
        if sub_map[uid]["first_purchase"] == 0 or (ts and ts < sub_map[uid]["first_purchase"]):
            sub_map[uid]["first_purchase"] = ts
        if s.get("status") == "ACTIVE" and s.get("expires_at", 0) > now:
            sub_map[uid]["active_pkgs"] += 1
        elif s.get("status") in ("EXPIRED",) or (s.get("status") == "ACTIVE" and s.get("expires_at", 0) <= now):
            sub_map[uid]["expired_pkgs"] += 1

    users_out = []
    for uid in active_user_ids:
        u = users_raw.get(uid)
        if not u:
            continue
        sm = sub_map.get(uid, {})
        users_out.append({
            "fk_user_id": uid,
            "username": u.get("username", "—"),
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "status": u.get("status", ""),
            "total_pkgs": sm.get("total_pkgs", 0),
            "active_pkgs": sm.get("active_pkgs", 0),
            "expired_pkgs": sm.get("expired_pkgs", 0),
            "total_spent": sm.get("total_spent", 0),
            "first_purchase": sm.get("first_purchase", 0),
            "qr_count": qr_counts.get(uid, 0),
            "total_scans": scan_counts.get(uid, 0),
        })

    users_out.sort(key=lambda x: x["total_spent"], reverse=True)

    return render_template("admin/active_users.html",
        users=users_out,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )


@app.route("/admin/active-users/<fk_user_id>")
def admin_active_user_detail(fk_user_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    import time as _t
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    now = int(_t.time())

    user = _db.db_user.find_one({"fk_user_id": fk_user_id}, {"_id": 0})
    if not user:
        return redirect(url_for("admin_active_users"))

    # All subscriptions for this user
    subs = list(_db.db_user_subscription.find(
        {"fk_user_id": fk_user_id},
        {"_id": 0}
    ).sort("timestamp", -1))

    # Subscription summary stats
    total_spent = sum(s.get("price_paid_idr", 0) for s in subs)
    active_pkgs = sum(1 for s in subs if s.get("status") == "ACTIVE" and s.get("expires_at", 0) > now)
    expired_pkgs = sum(1 for s in subs if s.get("status") == "EXPIRED" or
                       (s.get("status") == "ACTIVE" and s.get("expires_at", 0) <= now))
    first_purchase = min((s.get("timestamp") or s.get("started_at") or 0 for s in subs), default=0)

    # QR codes
    qr_list = list(_db.db_qr_index.find(
        {"fk_user_id": fk_user_id, "status": {"$nin": ["DELETED", "SOFT_DELETED"]}},
        {"_id": 0}
    ).sort("timestamp", -1))

    qr_ids = [q["qrcard_id"] for q in qr_list]
    scan_map = {}
    if qr_ids:
        for card in _db.db_qrcard.find(
            {"qrcard_id": {"$in": qr_ids}},
            {"_id": 0, "qrcard_id": 1, "stats": 1}
        ):
            scan_map[card["qrcard_id"]] = (card.get("stats") or {}).get("scan_count", 0)

    for q in qr_list:
        q["scan_count"] = scan_map.get(q["qrcard_id"], 0)

    total_scans = sum(q["scan_count"] for q in qr_list)

    return render_template("admin/active_user_detail.html",
        user=user,
        subs=subs,
        qr_list=qr_list,
        total_spent=total_spent,
        active_pkgs=active_pkgs,
        expired_pkgs=expired_pkgs,
        total_pkgs=len(subs),
        first_purchase=first_purchase,
        total_scans=total_scans,
        active_qr_count=len(qr_list),
        now=now,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )


# ── Email Templates ──────────────────────────────────────────────────────────

_DEFAULT_EMAIL_TEMPLATES = [
    {
        "name": "Package Expiry Reminder",
        "type": "reminder",
        "subject": "Your {{plan_name}} Package Expires in {{days_left}} Days — QRkartu",
        "variables": ["user_name", "plan_name", "expires_date", "days_left", "price_paid"],
        "body_html": """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Package Expiry Reminder</title></head>
<body style="margin:0;padding:0;background:#111209;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#111209;padding:40px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#181914;border-radius:16px;overflow:hidden;border:1px solid #2C2D25;">
      <!-- Header -->
      <tr><td style="background:linear-gradient(135deg,#111209,#1a1b14);padding:32px;text-align:center;border-bottom:1px solid rgba(235,168,27,0.15);">
        <div style="font-size:26px;font-weight:800;color:#EBA81B;letter-spacing:1px;">QRkartu</div>
        <div style="font-size:12px;color:#8A8878;margin-top:4px;letter-spacing:2px;text-transform:uppercase;">Package Reminder</div>
      </td></tr>
      <!-- Body -->
      <tr><td style="padding:36px 40px;">
        <p style="color:#8A8878;font-size:15px;margin:0 0 24px;">Hi <strong style="color:#E8E5DC;">{{user_name}}</strong>,</p>
        <p style="color:#E8E5DC;font-size:15px;line-height:1.7;margin:0 0 28px;">
          Your <strong style="color:#EBA81B;">{{plan_name}}</strong> package is expiring soon.<br>
          Don't let your QR codes go offline — renew now to keep everything running.
        </p>
        <!-- Package box -->
        <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(235,168,27,0.06);border:1px solid rgba(235,168,27,0.2);border-radius:12px;margin-bottom:28px;">
          <tr><td style="padding:24px 28px;">
            <div style="font-size:12px;color:#8A8878;text-transform:uppercase;letter-spacing:.6px;margin-bottom:14px;">Package Details</div>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="color:#8A8878;font-size:13px;padding:5px 0;">Plan</td>
                <td style="color:#E8E5DC;font-size:13px;font-weight:600;text-align:right;">{{plan_name}}</td>
              </tr>
              <tr>
                <td style="color:#8A8878;font-size:13px;padding:5px 0;">Expires on</td>
                <td style="color:#E8E5DC;font-size:13px;font-weight:600;text-align:right;">{{expires_date}}</td>
              </tr>
              <tr>
                <td style="color:#8A8878;font-size:13px;padding:5px 0;">Days remaining</td>
                <td style="color:#EBA81B;font-size:15px;font-weight:800;text-align:right;">{{days_left}} days</td>
              </tr>
            </table>
          </td></tr>
        </table>
        <!-- CTA -->
        <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:8px 0 32px;">
          <a href="https://qrkartu.com/user/plans" style="display:inline-block;padding:14px 40px;background:#EBA81B;color:#111209;font-size:15px;font-weight:700;text-decoration:none;border-radius:30px;">
            Renew My Package
          </a>
        </td></tr></table>
        <p style="color:#8A8878;font-size:13px;line-height:1.6;margin:0;">
          If you have any questions, reply to this email and we'll be happy to help.
        </p>
      </td></tr>
      <!-- Footer -->
      <tr><td style="padding:20px 40px;border-top:1px solid #2C2D25;text-align:center;">
        <p style="color:#5a5a4a;font-size:11px;margin:0;">
          © QRkartu · You're receiving this because you have an active subscription.<br>
          <a href="https://qrkartu.com" style="color:#8A8878;text-decoration:none;">qrkartu.com</a>
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>""",
    },
]

def _seed_email_templates(db):
    """Seed default email templates if collection is empty."""
    import time as _t
    import uuid
    if db.db_email_template.count_documents({}) == 0:
        for tpl in _DEFAULT_EMAIL_TEMPLATES:
            doc = dict(tpl)
            doc["template_id"] = uuid.uuid4().hex
            doc["status"] = "ACTIVE"
            doc["created_at"] = str(int(_t.time()))
            doc["timestamp"] = int(_t.time())
            db.db_email_template.insert_one(doc)

@app.route("/admin/email-templates")
def admin_email_templates():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    _seed_email_templates(_db)
    templates = list(_db.db_email_template.find({}, {"_id": 0}).sort("timestamp", 1))
    return render_template("admin/email_templates.html",
        templates=templates,
        admin_name=session.get("admin_name", ""),
        admin_email=session.get("admin_email", ""),
        admin_role=session.get("admin_role", ""),
    )

@app.route("/admin/email-templates/save", methods=["POST"])
def admin_email_templates_save():
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    import time as _t, uuid
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    data = request.get_json() or {}
    template_id = data.get("template_id", "").strip()
    name       = data.get("name", "").strip()
    ttype      = data.get("type", "reminder").strip()
    body_type  = data.get("body_type", "html").strip()   # "html" or "text"
    subject    = data.get("subject", "").strip()
    body_html  = data.get("body_html", "").strip()
    status     = data.get("status", "ACTIVE")
    variables  = data.get("variables", [])
    if not name or not subject or not body_html:
        return jsonify({"ok": False, "error": "name, subject and body_html are required"})
    now = int(_t.time())
    if template_id:
        _db.db_email_template.update_one(
            {"template_id": template_id},
            {"$set": {"name": name, "type": ttype, "body_type": body_type, "subject": subject,
                      "body_html": body_html, "variables": variables, "status": status}}
        )
    else:
        _db.db_email_template.insert_one({
            "template_id": uuid.uuid4().hex,
            "name": name, "type": ttype, "body_type": body_type, "subject": subject,
            "body_html": body_html, "variables": variables,
            "status": status, "created_at": str(now), "timestamp": now,
        })
    return jsonify({"ok": True})

@app.route("/admin/email-templates/delete", methods=["POST"])
def admin_email_templates_delete():
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    data = request.get_json() or {}
    template_id = data.get("template_id", "")
    if template_id:
        _db.db_email_template.delete_one({"template_id": template_id})
    return jsonify({"ok": True})

@app.route("/api/admin/email-templates")
def api_admin_email_templates():
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from pytavia_core import database as _db_p, config as _cfg_p
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    ttype = request.args.get("type", "")
    q = {"status": "ACTIVE"}
    if ttype:
        q["type"] = ttype
    templates = list(_db.db_email_template.find(q, {"_id": 0}).sort("timestamp", 1))
    return jsonify({"ok": True, "templates": templates})

@app.route("/admin/active-users/<fk_user_id>/send-email", methods=["POST"])
def admin_send_email_to_user(fk_user_id):
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    import time as _t
    from pytavia_core import database as _db_p, config as _cfg_p
    from pytavia_modules.auth.brevo import brevo_email_proc as _bep
    _db = _db_p.get_db_conn(_cfg_p.mainDB)
    data = request.get_json() or {}
    subject   = data.get("subject", "").strip()
    body      = data.get("body", "").strip()
    body_type = data.get("body_type", "html")  # "html" or "text"
    if not subject or not body:
        return jsonify({"ok": False, "error": "Subject and body are required"})
    user = _db.db_user.find_one({"fk_user_id": fk_user_id}, {"_id": 0})
    if not user or not user.get("email"):
        return jsonify({"ok": False, "error": "User or email not found"})
    to_email = user["email"]
    to_name  = user.get("name") or user.get("username") or to_email
    mailer = _bep.brevo_email_proc(app)
    if body_type == "text":
        ok = mailer._send_email(to_email, to_name, subject, text_content=body)
    else:
        ok = mailer._send_email(to_email, to_name, subject, html_content=body)
    if ok:
        return jsonify({"ok": True, "message": f"Email sent to {to_email}"})
    return jsonify({"ok": False, "error": "Failed to send email. Check Brevo API key and logs."})


@app.route("/admin/storage")
def admin_storage():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_adm
    from pytavia_core import database as _db_adm, config as _cfg_adm
    import math

    _per_page = 50
    try:
        _page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        _page = 1

    _atp = _atp_adm()
    total_count = _atp.get_soft_deleted_count()
    total_pages = max(1, math.ceil(total_count / _per_page))
    if _page > total_pages:
        _page = total_pages

    offset = (_page - 1) * _per_page
    assets = _atp.get_soft_deleted_assets(limit=_per_page, offset=offset)

    # Attach user email
    _db_adm_conn = _db_adm.get_db_conn(_cfg_adm.mainDB)
    user_ids = list({a["fk_user_id"] for a in assets if a.get("fk_user_id")})
    user_map = {}
    for u in _db_adm_conn.db_user.find({"fk_user_id": {"$in": user_ids}}, {"fk_user_id": 1, "email": 1, "_id": 0}):
        user_map[u["fk_user_id"]] = u.get("email", u["fk_user_id"])
    for a in assets:
        a["user_email"] = user_map.get(a.get("fk_user_id", ""), a.get("fk_user_id", "—"))

    total_size = sum(a.get("file_size", 0) for a in assets)
    whole_total_size = _atp.get_soft_deleted_size()
    from pytavia_modules.user.user_storage_proc import _fmt_size
    return render_template(
        "admin/storage.html",
        assets=assets,
        total_count=total_count,
        total_size_fmt=_fmt_size(total_size),
        whole_total_size_fmt=_fmt_size(whole_total_size),
        page=_page,
        per_page=_per_page,
        total_pages=total_pages,
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
    delete_result = _r2.delete_keys_batch(r2_keys)
    deleted_r2 = delete_result.get("deleted", 0)
    r2_responses = delete_result.get("results", [])
    
    # Mark all as HARD_DELETED in MongoDB
    ids_to_mark = [a["asset_id"] for a in assets if a.get("asset_id")]
    _atp.mark_hard_deleted_batch(ids_to_mark)
    freed_bytes = sum(a.get("file_size", 0) for a in assets)
    from pytavia_modules.user.user_storage_proc import _fmt_size
    return jsonify({
        "ok": True,
        "deleted": len(ids_to_mark),
        "deleted_r2": deleted_r2,
        "r2_responses": r2_responses,
        "freed_bytes": freed_bytes,
        "freed_fmt": _fmt_size(freed_bytes),
    })


_SCAN_JOBS = {}

@app.route("/admin/storage/scan_orphans/start", methods=["POST"])
def admin_storage_scan_orphans_start():
    """Starts a background thread to scan Cloudflare R2 and compare against MongoDB."""
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401

    import uuid
    import threading
    job_id = str(uuid.uuid4())
    _SCAN_JOBS[job_id] = {
        "status": "running", 
        "step": "Connecting to Cloudflare R2...",
        "current": 0, 
        "total": 0, 
        "orphans": 0,
        "error": None
    }

    def background_scan(j_id):
        try:
            from pytavia_modules.storage import r2_storage_proc
            from pytavia_core import database, config
            import time

            _r2 = r2_storage_proc.r2_storage_proc()
            _db = database.get_db_conn(config.mainDB)

            _SCAN_JOBS[j_id]["step"] = "Fetching all files from R2 bucket..."
            all_r2_files = _r2.list_prefix("")
            r2_map = {obj["key"]: obj["size"] for obj in all_r2_files}
            
            _SCAN_JOBS[j_id]["step"] = "Downloading tracked MongoDB assets..."
            db_assets = list(_db.db_qr_assets.find({}, {"r2_key": 1, "status": 1, "fk_user_id": 1}))
            db_map = {doc.get("r2_key"): doc for doc in db_assets if doc.get("r2_key")}

            _SCAN_JOBS[j_id]["step"] = "Mapping user activity statuses..."
            deleted_users_cursor = _db.db_user.find({"is_deleted": True}, {"fk_user_id": 1})
            deleted_users = {u.get("fk_user_id") for u in deleted_users_cursor if u.get("fk_user_id")}
            
            active_users_cursor = _db.db_user.find({"is_deleted": {"$ne": True}}, {"fk_user_id": 1})
            active_users = {u.get("fk_user_id") for u in active_users_cursor if u.get("fk_user_id")}

            total_files = len(r2_map)
            _SCAN_JOBS[j_id]["total"] = total_files
            _SCAN_JOBS[j_id]["step"] = "Diffing files and injecting orphans..."

            orphans_detected = 0
            current_idx = 0
            now = time.time()
            
            for r2_key, r2_size in r2_map.items():
                current_idx += 1
                if current_idx % 20 == 0:
                    _SCAN_JOBS[j_id]["current"] = current_idx
                    _SCAN_JOBS[j_id]["orphans"] = orphans_detected

                if r2_key.startswith("public/") or r2_key.startswith("static/"):
                    continue
                    
                db_entry = db_map.get(r2_key)
                is_orphan = False
                
                if not db_entry:
                    is_orphan = True
                    owner_id = "UNKNOWN"
                else:
                    owner_id = db_entry.get("fk_user_id", "")
                    if (owner_id in deleted_users) or (owner_id not in active_users and owner_id != "UNKNOWN" and owner_id != ""):
                        if db_entry.get("status") != "SOFT_DELETED":
                            is_orphan = True

                if is_orphan:
                    orphans_detected += 1
                    if not db_entry:
                        from pytavia_modules.user.asset_tracker_proc import _file_category
                        _db.db_qr_assets.insert_one({
                            "asset_id"      : str(uuid.uuid4().hex),
                            "fk_user_id"    : owner_id,
                            "qrcard_id"     : "",
                            "frame_id"      : "",
                            "qr_type"       : "orphan",
                            "r2_key"        : r2_key,
                            "file_name"     : r2_key.split("/")[-1],
                            "file_size"     : int(r2_size),
                            "file_category" : _file_category(r2_key),
                            "status"        : "SOFT_DELETED",
                            "soft_deleted_at": now,
                            "created_at"    : time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now)),
                            "timestamp"     : now,
                        })
                    else:
                        _db.db_qr_assets.update_one(
                            {"_id": db_entry["_id"]},
                            {"$set": {"status": "SOFT_DELETED", "soft_deleted_at": now}}
                        )

            _SCAN_JOBS[j_id]["current"] = current_idx
            _SCAN_JOBS[j_id]["orphans"] = orphans_detected
            _SCAN_JOBS[j_id]["status"] = "completed"

        except Exception as e:
            import traceback
            app.logger.debug(traceback.format_exc())
            _SCAN_JOBS[j_id]["status"] = "error"
            _SCAN_JOBS[j_id]["error"] = str(e)

    threading.Thread(target=background_scan, args=(job_id,)).start()
    return jsonify({"ok": True, "job_id": job_id})

@app.route("/admin/storage/scan_orphans/progress/<job_id>", methods=["GET"])
def admin_storage_scan_orphans_progress(job_id):
    if "fk_admin_id" not in session:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    job = _SCAN_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, "job": job})


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
    from pytavia_modules.qr.qr_public_visual_helper import enforce_scan_limit_and_increment
    _mgd = _db_img.get_db_conn(_cfg_img.mainDB)
    qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "images", "status": "ACTIVE"})
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
    # Merge images-specific doc
    qrcard = _merge_images_into_qrcard(_mgd, qrcard.get("fk_user_id"), qrcard["qrcard_id"], qrcard)
    qrcard = enforce_scan_limit_and_increment(qrcard, _mgd, app)
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
    _mgd.db_qrcard_images.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    return render_template("user/public_images.html", qrcard=qrcard)


@app.route("/video/<short_code>")
def qr_video_redirect(short_code):
    """Public endpoint for video-gallery short URLs."""
    from pytavia_core import database as _db_vid, config as _cfg_vid
    from pytavia_modules.qr.qr_public_visual_helper import enforce_scan_limit_and_increment
    _mgd = _db_vid.get_db_conn(_cfg_vid.mainDB)
    qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "video", "status": "ACTIVE"})
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
    qrcard = _merge_video_into_qrcard(_mgd, qrcard.get("fk_user_id"), qrcard["qrcard_id"], qrcard)
    qrcard = enforce_scan_limit_and_increment(qrcard, _mgd, app)
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
    _mgd.db_qrcard_video.update_one({"qrcard_id": qrcard["qrcard_id"]}, {"$inc": {"stats.scan_count": 1}})
    return render_template("user/public_video.html", qrcard=qrcard)


@app.route("/special/<short_code>")
def qr_special_redirect(short_code):
    """Public endpoint for special-page short URLs."""
    from pytavia_core import database as _db_sp, config as _cfg_sp
    from pytavia_modules.qr.qr_public_visual_helper import enforce_scan_limit_and_increment
    _mgd = _db_sp.get_db_conn(_cfg_sp.mainDB)
    qrcard = _mgd.db_qrcard_special.find_one({"short_code": short_code, "status": "ACTIVE"})
    if not qrcard:
        qrcard = _mgd.db_qrcard.find_one({"short_code": short_code, "qr_type": "special", "status": "ACTIVE"})
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
    _base_sp = _mgd.db_qrcard.find_one({"qrcard_id": qrcard.get("qrcard_id")})
    if _base_sp:
        _merged_sp = dict(qrcard)
        for _k in ("schedule_enabled", "schedule_since", "schedule_until", "scan_limit_enabled", "scan_limit_value", "stats"):
            if _k in _base_sp:
                _merged_sp[_k] = _base_sp[_k]
        qrcard = _merged_sp
    qrcard = enforce_scan_limit_and_increment(qrcard, _mgd, app)
    if not qrcard:
        return render_template("user/public_not_found.html"), 404
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
    from flask import request as _req_new
    quota = _get_user_qr_quota(session["fk_user_id"])
    quota_error = _req_new.args.get("quota_error")
    return view_user.view_user(app).new_qr_html(qr_quota=quota, error_msg=quota_error)

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


@app.route("/qr/toggle-status/<qrcard_id>", methods=["POST"])
def qr_toggle_status(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_tog, config as _cfg_tog
    _mgd_tog = _db_tog.get_db_conn(_cfg_tog.mainDB)
    fk_user_id = session.get("fk_user_id")
    quota_sync = _sync_user_qr_activation_quota(fk_user_id, _mgd_tog)

    # Verify ownership and get qr_type from db_qr_index
    idx = _mgd_tog.db_qr_index.find_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
        {"_id": 0, "status": 1, "qr_type": 1},
    )
    if not idx:
        return redirect(url_for("user_qr_list"))

    qr_type = idx.get("qr_type", "")

    _type_col_map = {
        "pdf":          "db_qrcard_pdf",
        "web-static":   "db_qrcard_web_static",
        "text":         "db_qrcard_text",
        "wa-static":    "db_qrcard_wa_static",
        "email-static": "db_qrcard_email_static",
        "vcard-static": "db_qrcard_vcard_static",
        "allinone":     "db_qrcard_allinone",
        "images":       "db_qrcard_images",
        "video":        "db_qrcard_video",
        "special":      "db_qrcard_special",
    }
    col_name = _type_col_map.get(qr_type)

    # Read the authoritative current status from the type-specific collection
    # (same source the list view uses), falling back to db_qrcard, then db_qr_index.
    # This avoids stale-sync issues where previous partial updates left collections
    # out of step with each other.
    cur_status = None
    if col_name:
        spec_doc = getattr(_mgd_tog, col_name).find_one(
            {"qrcard_id": qrcard_id}, {"_id": 0, "status": 1}
        )
        if spec_doc:
            cur_status = spec_doc.get("status")
    if cur_status is None:
        base_doc = _mgd_tog.db_qrcard.find_one(
            {"qrcard_id": qrcard_id}, {"_id": 0, "status": 1}
        )
        cur_status = (base_doc or {}).get("status") or idx.get("status", "ACTIVE")

    if cur_status == "DRAFT":
        return redirect(url_for("user_qr_list"))

    if cur_status == "INACTIVE":
        total_quota = int(quota_sync.get("total_max_qr", 0) or 0)
        active_qr = int(quota_sync.get("active_qr", 0) or 0)
        if total_quota <= 0 or active_qr >= total_quota:
            return redirect(url_for("user_qr_list", error_msg="Sorry oops, you don't have a quota."))

    new_status = "INACTIVE" if cur_status == "ACTIVE" else "ACTIVE"
    set_op = {"$set": {"status": new_status}}

    # Update all collections in sync
    _mgd_tog.db_qr_index.update_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, set_op
    )
    _mgd_tog.db_qrcard.update_one(
        {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, set_op
    )
    if col_name:
        getattr(_mgd_tog, col_name).update_one(
            {"qrcard_id": qrcard_id}, set_op
        )

    return redirect(url_for("user_qr_list"))


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
    _was_draft_pdf = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": _fk_pdf}) or {}).get("status") == "DRAFT"
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
    from pytavia_modules.user import user_activity_proc as _uap_pdf2
    if _was_draft_pdf:
        _uap_pdf2.user_activity_proc(app).log(
            fk_user_id=_fk_pdf, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="pdf", source="create",
        )
    else:
        _uap_pdf2.user_activity_proc(app).log(
            fk_user_id=_fk_pdf, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="pdf", source="edit",
        )
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
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()
    _frame_id_web = request.form.get("frame_id", "")
    _was_draft_web = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
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
    from pytavia_modules.user import user_activity_proc as _uap_web2
    if _was_draft_web:
        _uap_web2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=qr_name,
            qr_type="web", source="create",
        )
    else:
        _uap_web2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=qr_name,
            qr_type="web", source="edit",
        )
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
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()

    _ecard_skip = frozenset([
        "csrf_token", "url_content", "qr_name", "short_code",
        "scan_limit_enabled", "scan_limit_value",
        "schedule_enabled", "schedule_since", "schedule_until",
    ])
    for key in request.form:
        if key not in _ecard_skip:
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
        _valid_gallery = [(gfile, _uuid.uuid4().hex + (os.path.splitext(gfile.filename)[1].lower() or ".jpg")) for gfile in gallery_files if gfile and gfile.filename]
        if _valid_gallery:
            _gallery_specs = []
            for gfile, safe_name in _valid_gallery:
                try:
                    gfile.seek(0, 2)
                    data = gfile.read()
                    gfile.seek(0)
                    _gallery_specs.append((data, f"ecard/{qrcard_id}/gallery/{safe_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": safe_name}))
                except Exception:
                    pass
            if _gallery_specs:
                _gallery_results = r2.upload_files_parallel(_gallery_specs, max_workers=5)
                for gr in _gallery_results:
                    if gr["status"] == "success":
                        saved_gallery.append({"url": gr["url"]})
        if saved_gallery:
            proc.mgdDB.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}})
            proc.mgdDB.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"ecard_gallery_files": saved_gallery}}, upsert=True)

    _was_draft_ecard = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
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
    from pytavia_modules.user import user_activity_proc as _uap_ecard2
    if _was_draft_ecard:
        _uap_ecard2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=qr_name,
            qr_type="ecard", source="create",
        )
    else:
        _uap_ecard2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=qr_name,
            qr_type="ecard", source="edit",
        )
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/pdf/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_pdf(qrcard_id):
    """Step 2 (design) for PDF. GET or POST from content -> design; save is POST to /qr/update/save/pdf/<id>."""
    from flask import request
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_pdf_proc as _qrp
    qrcard = _qrp.qr_pdf_proc(app).get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        pdf_fields = ["pdf_template", "pdf_primary_color", "pdf_secondary_color", "pdf_title_font", "pdf_title_color",
                      "pdf_text_font", "pdf_text_color", "pdf_company", "pdf_title", "pdf_desc", "pdf_website",
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "scan_limit_enabled", "scan_limit_value",
                      "pdf_font_apply_all", "schedule_enabled", "schedule_since", "schedule_until"]
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
    from pytavia_modules.qr import qr_web_proc as _qrw2
    _proc_w = _qrw2.qr_web_proc(app)
    qrcard = _proc_w.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        url_content = (request.form.get("url_content") or "").strip() or qrcard.get("url_content") or "QRkartu"
        qr_name = (request.form.get("qr_name") or "").strip() or qrcard.get("name") or "Untitled QR"
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        _raw_lim = (request.form.get("scan_limit_value") or "").strip()
        _extra_w = {
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(_raw_lim) if _raw_lim.isdigit() else 0,
        }
        _set_qr_draft(session, qrcard_id, url_content, qr_name, request.form.get("short_code", "").strip(), _extra_w)
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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

        import os, uuid as _uuid
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
            _has_welcome_upload = False
            _welcome_upload_spec = None
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    _has_welcome_upload = True
                    _welcome_upload_spec = (welcome_img, f"ecard/{qrcard_id}/welcome_{int(time.time())}{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
            elif request.form.get("ecard_welcome_img_autocomplete_url", "").strip():
                welcome_url = request.form.get("ecard_welcome_img_autocomplete_url").strip()
                extra_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                _mgd_ew = database.get_db_conn(config.mainDB)
                _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif qrcard.get("welcome_img_url"):
                extra_data["welcome_img_url"] = qrcard["welcome_img_url"]

        _has_cover_upload = False
        _cover_upload_spec = None
        _cover_img_fields = ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]
        if request.form.get("E-card_profile_img_delete") == "1":
            for f in _cover_img_fields:
                extra_data[f] = ""
                qrcard[f] = ""
            try:
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in _cover_img_fields}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in _cover_img_fields}})
            except Exception: pass
        else:
            cover_img = request.files.get("E-card_profile_img")
            if cover_img and cover_img.filename:
                cover_img.seek(0, 2)
                if cover_img.tell() <= 2 * 1024 * 1024:
                    cover_img.seek(0)
                    ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    unique_cover_name = f"ecard_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                    _has_cover_upload = True
                    _cover_upload_spec = (cover_img, f"ecard/{qrcard_id}/{unique_cover_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
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

        # ── Parallel upload: welcome + cover images ──
        _img_specs = []
        if _has_welcome_upload:
            _img_specs.append(("welcome", _welcome_upload_spec))
        if _has_cover_upload:
            _img_specs.append(("cover", _cover_upload_spec))
        if _img_specs:
            _img_results = _r2.upload_files_parallel([s[1] for s in _img_specs])
            for idx, _ir in enumerate(_img_results):
                _tag = _img_specs[idx][0]
                if _ir["status"] != "success":
                    continue
                if _tag == "welcome":
                    welcome_url = _ir["url"]
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    _mgd_ew = database.get_db_conn(config.mainDB)
                    _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                elif _tag == "cover":
                    cover_url = _ir["url"]
                    for f in _cover_img_fields:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})

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

            # Collect all upload specs: file uploads + autocomplete static uploads
            _all_gf_specs = []
            _all_gf_meta = []  # "file" | "static" | ("http", url)
            _valid_gf = [(gf, f"gallery_{uuid.uuid4().hex[:12]}{(os.path.splitext(gf.filename)[1].lower() or '.jpg')}") for gf in uploaded_gallery if gf and gf.filename]
            for gf, name in _valid_gf:
                _all_gf_specs.append((gf, f"ecard/{qrcard_id}/gallery/{name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": name}))
                _all_gf_meta.append("file")
            for ac_url in autocomplete_gallery:
                ac_url = (ac_url or "").strip()
                if not ac_url:
                    continue
                if ac_url.startswith("/static/"):
                    try:
                        ext = os.path.splitext(ac_url)[1] or ".jpg"
                        local_path = os.path.join(config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                        if os.path.isfile(local_path):
                            unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as fp:
                                _all_gf_specs.append((fp, f"ecard/{qrcard_id}/gallery/{unique_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name}))
                                _all_gf_meta.append("static")
                        else:
                            _all_gf_specs.append(None)
                            _all_gf_meta.append(("http", ac_url))
                    except Exception:
                        _all_gf_specs.append(None)
                        _all_gf_meta.append(("http", ac_url))
                elif ac_url.startswith("http://") or ac_url.startswith("https://"):
                    _all_gf_specs.append(None)
                    _all_gf_meta.append(("http", ac_url))

            # Execute all uploads in parallel
            _upload_only_specs = [s for s in _all_gf_specs if s is not None]
            if _upload_only_specs:
                _gf_results = _r2.upload_files_parallel(_upload_only_specs, max_workers=5)
                _upload_idx = 0
                for i, meta in enumerate(_all_gf_meta):
                    if meta == "file" or meta == "static":
                        if _upload_idx < len(_gf_results) and _gf_results[_upload_idx]["status"] == "success":
                            _url = _gf_results[_upload_idx]["url"]
                            if _url not in seen_urls:
                                seen_urls.add(_url)
                                gallery_items.append({"url": _url})
                        _upload_idx += 1
                    elif isinstance(meta, tuple) and meta[0] == "http":
                        if meta[1] not in seen_urls:
                            seen_urls.add(meta[1])
                            gallery_items.append({"url": meta[1]})

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
    qrcard = _qrp.qr_pdf_proc(app).get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "scan_limit_enabled", "scan_limit_value",
                      "pdf_font_apply_all", "schedule_enabled", "schedule_since", "schedule_until"]
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
            _has_welcome_upload = False
            _welcome_upload_spec = None
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
                _wts = int(time.time())
                _has_welcome_upload = True
                _welcome_upload_spec = (welcome_img, f"pdf/{qrcard_id}/welcome_{_wts}{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf"})
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
        _has_cover_upload = False
        _cover_upload_spec = None
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
                unique_cover_name = f"pdf_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                _has_cover_upload = True
                _cover_upload_spec = (cover_img, f"pdf/{qrcard_id}/{unique_cover_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf"})
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

        # ── Parallel upload: welcome image + cover image ──
        _r2 = r2_mod.r2_storage_proc()
        _img_specs = []
        if _has_welcome_upload:
            _img_specs.append(("welcome", _welcome_upload_spec))
        if _has_cover_upload:
            _img_specs.append(("cover", _cover_upload_spec))
        if _img_specs:
            _img_results = _r2.upload_files_parallel([s[1] for s in _img_specs])
            for idx, _ir in enumerate(_img_results):
                _tag = _img_specs[idx][0]
                if _ir["status"] != "success":
                    continue
                if _tag == "welcome":
                    welcome_url = _ir["url"]
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
                elif _tag == "cover":
                    cover_url = _ir["url"]
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
            _valid_pdf_files = []
            _valid_pdf_meta = []
            for f in pdf_file_list:
                if f and f.filename and f.filename.lower().endswith(".pdf"):
                    original_name = f.filename
                    safe_name = original_name.replace(" ", "_")
                    if original_name in existing_names or safe_name in existing_safe_names or original_name in seen_upload_names:
                        duplicate_name = original_name
                        break
                    seen_upload_names.add(original_name)
                    r2_key = f"pdf/{qrcard_id}/{safe_name}"
                    _valid_pdf_files.append(f)
                    _valid_pdf_meta.append({"original_name": original_name, "safe_name": safe_name, "r2_key": r2_key, "form_idx": _new_file_offset + _new_file_idx})
                    _new_file_idx += 1
                    existing_names.add(original_name)
                    existing_safe_names.add(safe_name)
            if duplicate_name:
                qrcard.update(ecard_data)
                return view_update_pdf.view_update_pdf(app).update_qr_content_html(
                    qrcard=qrcard, url_content=url_content, qr_name=qr_name, short_code=short_code or None,
                    error_msg=f"Oops, a PDF named '{duplicate_name}' is already attached to this QR card. Please rename the file or choose a different PDF.",
                    base_url=config.G_BASE_URL,
                )
            if _valid_pdf_files:
                _pdf_specs = [(f, m["r2_key"], {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "pdf", "file_name": m["original_name"]}) for f, m in zip(_valid_pdf_files, _valid_pdf_meta)]
                _pdf_results = _r2_pdf.upload_files_parallel(_pdf_specs)
                for idx, _pr in enumerate(_pdf_results):
                    if _pr["status"] != "success":
                        continue
                    m = _valid_pdf_meta[idx]
                    file_entry = {"name": m["original_name"], "url": _pr["url"]}
                    form_idx = m["form_idx"]
                    if form_idx < len(_step_display_names) and _step_display_names[form_idx].strip():
                        file_entry["display_name"] = _step_display_names[form_idx].strip()
                    if form_idx < len(_step_item_descs) and _step_item_descs[form_idx].strip():
                        file_entry["item_desc"] = _step_item_descs[form_idx].strip()
                    existing_files.append(file_entry)
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
    from pytavia_modules.qr import qr_web_proc as _qrw
    proc = _qrw.qr_web_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id)
    if not qrcard:
        return redirect(url_for("user_qr_list"))
    if request.method == "POST":
        qr_name = request.form.get("qr_name", "").strip()
        url_content = request.form.get("url_content", "").strip()
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        short_code = request.form.get("short_code", "").strip()
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
        _raw_limit = (request.form.get("scan_limit_value") or "").strip()
        _draft_extra = {
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(_raw_limit) if _raw_limit.isdigit() else 0,
        }
        _set_qr_draft(session, qrcard_id, url_content, qr_name, short_code, _draft_extra)
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
            _has_welcome_upload = False
            _welcome_upload_spec = None
            if welcome_img and welcome_img.filename:
                welcome_img.seek(0, 2)
                if welcome_img.tell() <= 1024 * 1024:
                    welcome_img.seek(0)
                    ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    _has_welcome_upload = True
                    _welcome_upload_spec = (welcome_img, f"ecard/{qrcard_id}/welcome_{int(time.time())}{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
            elif request.form.get("ecard_welcome_img_autocomplete_url", "").strip():
                welcome_url = request.form.get("ecard_welcome_img_autocomplete_url").strip()
                extra_data["welcome_img_url"] = welcome_url
                qrcard["welcome_img_url"] = welcome_url
                _mgd_ew = database.get_db_conn(config.mainDB)
                _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
            elif qrcard.get("welcome_img_url"):
                extra_data["welcome_img_url"] = qrcard["welcome_img_url"]

        _has_cover_upload = False
        _cover_upload_spec = None
        _cover_img_fields = ["E-card_t1_header_img_url", "E-card_t3_circle_img_url", "E-card_t4_circle_img_url"]
        if request.form.get("E-card_profile_img_delete") == "1":
            for f in _cover_img_fields:
                extra_data[f] = ""
                qrcard[f] = ""
            try:
                from pytavia_core import database as _db_c, config as _cfg_c
                _mgd = _db_c.get_db_conn(_cfg_c.mainDB)
                _mgd.db_qrcard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in _cover_img_fields}})
                _mgd.db_qrcard_ecard.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {_f: "" for _f in _cover_img_fields}})
            except Exception: pass
        else:
            cover_img = request.files.get("E-card_profile_img")
            if cover_img and cover_img.filename:
                cover_img.seek(0, 2)
                if cover_img.tell() <= 2 * 1024 * 1024:
                    cover_img.seek(0)
                    ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): ext = ".jpg"
                    unique_cover_name = f"ecard_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                    _has_cover_upload = True
                    _cover_upload_spec = (cover_img, f"ecard/{qrcard_id}/{unique_cover_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard"})
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

        # ── Parallel upload: welcome + cover images ──
        _img_specs = []
        if _has_welcome_upload:
            _img_specs.append(("welcome", _welcome_upload_spec))
        if _has_cover_upload:
            _img_specs.append(("cover", _cover_upload_spec))
        if _img_specs:
            _img_results = _r2.upload_files_parallel([s[1] for s in _img_specs])
            for idx, _ir in enumerate(_img_results):
                _tag = _img_specs[idx][0]
                if _ir["status"] != "success":
                    continue
                if _tag == "welcome":
                    welcome_url = _ir["url"]
                    extra_data["welcome_img_url"] = welcome_url
                    qrcard["welcome_img_url"] = welcome_url
                    _mgd_ew = database.get_db_conn(config.mainDB)
                    _mgd_ew.db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                    _mgd_ew.db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": welcome_url}})
                elif _tag == "cover":
                    cover_url = _ir["url"]
                    for f in _cover_img_fields:
                        extra_data[f] = cover_url
                        qrcard[f] = cover_url
                    database.get_db_conn(config.mainDB).db_qrcard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})
                    database.get_db_conn(config.mainDB).db_qrcard_ecard.update_one({"qrcard_id": qrcard_id}, {"$set": {"E-card_t1_header_img_url": cover_url, "E-card_t3_circle_img_url": cover_url, "E-card_t4_circle_img_url": cover_url}})

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

            # Collect all upload specs: file uploads + autocomplete static uploads
            _all_gf_specs = []
            _all_gf_meta = []  # "file" | "static" | ("http", url)
            _valid_gf = [(gf, f"gallery_{uuid.uuid4().hex[:12]}{(os.path.splitext(gf.filename)[1].lower() or '.jpg')}") for gf in uploaded_gallery if gf and gf.filename]
            for gf, name in _valid_gf:
                _all_gf_specs.append((gf, f"ecard/{qrcard_id}/gallery/{name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": name}))
                _all_gf_meta.append("file")
            for ac_url in autocomplete_gallery:
                ac_url = (ac_url or "").strip()
                if not ac_url:
                    continue
                if ac_url.startswith("/static/"):
                    try:
                        ext = os.path.splitext(ac_url)[1] or ".jpg"
                        local_path = os.path.join(config.G_HOME_PATH, ac_url.lstrip("/").replace("/", os.sep))
                        if os.path.isfile(local_path):
                            unique_name = f"gallery_{uuid.uuid4().hex[:12]}{ext}"
                            with open(local_path, "rb") as fp:
                                _all_gf_specs.append((fp, f"ecard/{qrcard_id}/gallery/{unique_name}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "ecard", "file_name": unique_name}))
                                _all_gf_meta.append("static")
                        else:
                            _all_gf_specs.append(None)
                            _all_gf_meta.append(("http", ac_url))
                    except Exception:
                        _all_gf_specs.append(None)
                        _all_gf_meta.append(("http", ac_url))
                elif ac_url.startswith("http://") or ac_url.startswith("https://"):
                    _all_gf_specs.append(None)
                    _all_gf_meta.append(("http", ac_url))

            # Execute all uploads in parallel
            _upload_only_specs = [s for s in _all_gf_specs if s is not None]
            if _upload_only_specs:
                _gf_results = _r2.upload_files_parallel(_upload_only_specs, max_workers=5)
                _upload_idx = 0
                for i, meta in enumerate(_all_gf_meta):
                    if meta == "file" or meta == "static":
                        if _upload_idx < len(_gf_results) and _gf_results[_upload_idx]["status"] == "success":
                            _url = _gf_results[_upload_idx]["url"]
                            if _url not in seen_urls:
                                seen_urls.add(_url)
                                gallery_items.append({"url": _url})
                        _upload_idx += 1
                    elif isinstance(meta, tuple) and meta[0] == "http":
                        if meta[1] not in seen_urls:
                            seen_urls.add(meta[1])
                            gallery_items.append({"url": meta[1]})

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
                      "pdf_btn_text", "welcome_time", "welcome_bg_color", "pdf_font_apply_all",
                      "schedule_enabled", "schedule_since", "schedule_until"]
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

        # Save as draft so design page has a qrcard_id for proper back navigation
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_pdf_design_draft", qrcard_id=draft_result["qrcard_id"]))

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
    from pytavia_modules.user import user_activity_proc as _uap_wsu
    _uap_wsu.user_activity_proc(app).log(
        fk_user_id=fk_user_id, action="EDIT_QR",
        qrcard_id=qrcard_id, qr_name=qr_name, qr_type="web-static", source="edit",
    )
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
    from pytavia_modules.user import user_activity_proc as _uap_txu
    _uap_txu.user_activity_proc(app).log(
        fk_user_id=fk_user_id, action="EDIT_QR",
        qrcard_id=qrcard_id, qr_name=qr_name, qr_type="text", source="edit",
    )
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
    from pytavia_modules.user import user_activity_proc as _uap_wau
    _uap_wau.user_activity_proc(app).log(
        fk_user_id=fk_user_id, action="EDIT_QR",
        qrcard_id=qrcard_id, qr_name=qr_name, qr_type="wa-static", source="edit",
    )
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
    from pytavia_modules.user import user_activity_proc as _uap_vcu
    _uap_vcu.user_activity_proc(app).log(
        fk_user_id=session.get("fk_user_id"), action="EDIT_QR",
        qrcard_id=qrcard_id, qr_name=_vd("qr_name") or "Untitled QR", qr_type="vcard-static", source="edit",
    )
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
    from pytavia_modules.user import user_activity_proc as _uap_emu
    _uap_emu.user_activity_proc(app).log(
        fk_user_id=fk_user_id, action="EDIT_QR",
        qrcard_id=qrcard_id, qr_name=qr_name, qr_type="email-static", source="edit",
    )
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
    stats_carry = None
    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()

        _ecard_stats_keys = frozenset([
            "scan_limit_enabled", "scan_limit_value",
            "schedule_enabled", "schedule_since", "schedule_until",
        ])
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"] and key not in _ecard_stats_keys:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"):
                    ecard_data[key] = val_list
                else:
                    ecard_data[key] = val_list[0] if val_list else ""

        from pytavia_modules.qr.qr_ecard_proc import _schedule_date_for_html_input as _legacy_ecard_sched
        stats_carry = {
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(request.form.get("scan_limit_value") or 0) if str(request.form.get("scan_limit_value") or "").strip().isdigit() else (request.form.get("scan_limit_value") or ""),
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": _legacy_ecard_sched(request.form.get("schedule_since")),
            "schedule_until": _legacy_ecard_sched(request.form.get("schedule_until")),
        }

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
        # Save as draft so design page has a qrcard_id for proper back navigation
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_ecard_design_draft", qrcard_id=draft_result["qrcard_id"]))
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
    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
        error_msg=error_msg, ecard_data=ecard_data, stats_carry=stats_carry,
    )

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
        _upload_specs = []
        _welcome_tmp_name = None
        _cover_tmp_name = None
        welcome_img = request.files.get("Links_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "welcome" + ext
                _upload_specs.append((welcome_img, f"links/_tmp/{tmp_key}/{fname}", {}))
                _welcome_tmp_name = fname
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
                _upload_specs.append((cover_img, f"links/_tmp/{tmp_key}/{fname}", {}))
                _cover_tmp_name = fname
        if _upload_specs:
            _r2.upload_files_parallel(_upload_specs, max_workers=5)
        if _welcome_tmp_name:
            session["links_welcome_tmp_key"] = tmp_key
            session["links_welcome_tmp_name"] = _welcome_tmp_name
            session.modified = True
        if _cover_tmp_name:
            session["links_cover_tmp_key"] = tmp_key
            session["links_cover_tmp_name"] = _cover_tmp_name
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
        # Save draft so Back button can navigate to edit content page
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_links_design_draft", qrcard_id=draft_result["qrcard_id"]))
    stats_carry = None
    if links_data and any(k in links_data for k in ("scan_limit_enabled", "scan_limit_value", "schedule_enabled", "schedule_since", "schedule_until")):
        from pytavia_modules.qr.qr_links_proc import _schedule_date_for_html_input as _links_sched_norm
        stats_carry = {
            "scan_limit_enabled": bool(links_data.get("scan_limit_enabled")),
            "scan_limit_value": links_data.get("scan_limit_value", 0),
            "schedule_enabled": bool(links_data.get("schedule_enabled")),
            "schedule_since": _links_sched_norm(links_data.get("schedule_since")),
            "schedule_until": _links_sched_norm(links_data.get("schedule_until")),
        }
    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
        error_msg=error_msg, links_data=links_data, stats_carry=stats_carry,
    )


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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
        import os, io, uuid as _uuid
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
            _mgd.db_qrcard_sosmed.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _unset_fields}
            )
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

        # --- Parallel R2 uploads for cover + welcome images ---
        _r2 = r2_mod.r2_storage_proc()
        _upload_specs = []  # (kind, file_obj, key, meta)
        _has_cover_file = False
        _has_cover_static = False
        _has_welcome_file = False
        _has_welcome_static = False

        # Cover image file upload
        cover_img = request.files.get("Links_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _has_cover_file = True
                _upload_specs.append(("cover_file", cover_img, f"links/{qrcard_id}/links_cover_img{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links"}))
        # Cover delete
        _cover_delete = request.form.get("Links_profile_img_delete") == "1"
        # Cover autocomplete
        cover_asset_url = (request.form.get("links_cover_img_autocomplete_url") or "").strip()
        if cover_asset_url and cover_asset_url.startswith("/static/"):
            local_path = os.path.join(app.root_path, cover_asset_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                unique_cover = f"links_cover_img_{_uuid.uuid4().hex[:12]}{ext}"
                try:
                    with open(local_path, "rb") as f:
                        _bio = io.BytesIO(f.read())
                    _upload_specs.append(("cover_static", _bio, f"links/{qrcard_id}/{unique_cover}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links", "file_name": unique_cover}))
                    _has_cover_static = True
                except Exception:
                    pass
        # Welcome image file upload
        welcome_img = request.files.get("Links_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _has_welcome_file = True
                _upload_specs.append(("welcome_file", welcome_img, f"links/{qrcard_id}/welcome_{int(time.time())}{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links"}))
        # Welcome autocomplete
        welcome_asset_url = (request.form.get("links_welcome_img_autocomplete_url") or "").strip()
        if welcome_asset_url and welcome_asset_url.startswith("/static/"):
            local_path = os.path.join(app.root_path, welcome_asset_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                unique_welcome = f"welcome_{_uuid.uuid4().hex[:12]}{ext}"
                try:
                    with open(local_path, "rb") as f:
                        _bio = io.BytesIO(f.read())
                    _upload_specs.append(("welcome_static", _bio, f"links/{qrcard_id}/{unique_welcome}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "links", "file_name": unique_welcome}))
                    _has_welcome_static = True
                except Exception:
                    pass

        # Execute all uploads in parallel
        _cover_result_url = None
        _welcome_result_url = None
        if _upload_specs:
            _r2_specs = [(s[1], s[2], s[3]) for s in _upload_specs]
            _upload_results = _r2.upload_files_parallel(_r2_specs, max_workers=5)
            for j, (kind, _, _, _) in enumerate(_upload_specs):
                if j < len(_upload_results) and _upload_results[j]["status"] == "success":
                    url = _upload_results[j]["url"]
                    if kind in ("cover_file", "cover_static"):
                        _cover_result_url = url
                    elif kind in ("welcome_file", "welcome_static"):
                        _welcome_result_url = url

        # Apply results with correct priority: autocomplete > delete > file upload
        if cover_asset_url:
            if cover_asset_url.startswith("http://") or cover_asset_url.startswith("https://"):
                content_update["Links_cover_img_url"] = cover_asset_url
            elif _has_cover_static and _cover_result_url:
                content_update["Links_cover_img_url"] = _cover_result_url
        elif _cover_delete:
            content_update["Links_cover_img_url"] = ""
        elif _has_cover_file and _cover_result_url:
            content_update["Links_cover_img_url"] = _cover_result_url

        if welcome_asset_url:
            if welcome_asset_url.startswith("http://") or welcome_asset_url.startswith("https://"):
                content_update["welcome_img_url"] = welcome_asset_url
            elif _has_welcome_static and _welcome_result_url:
                content_update["welcome_img_url"] = _welcome_result_url
        elif _has_welcome_file and _welcome_result_url:
            content_update["welcome_img_url"] = _welcome_result_url
        _raw_scan_lim = (request.form.get("scan_limit_value") or "").strip()
        content_update["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        content_update["scan_limit_value"] = int(_raw_scan_lim) if _raw_scan_lim.isdigit() else 0
        content_update["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
        content_update["schedule_since"] = (request.form.get("schedule_since") or "").strip()
        content_update["schedule_until"] = (request.form.get("schedule_until") or "").strip()
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
    _raw_lim_lk = (request.form.get("scan_limit_value") or "").strip()
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
    params["scan_limit_value"] = int(_raw_lim_lk) if _raw_lim_lk.isdigit() else 0
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or "").strip()
    proc.edit_qrcard(params)
    _frame_id_links = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_links)
    _was_draft_links = (database.get_db_conn(config.mainDB).db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
    _enc_url_links = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_links", "/links/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_links, _frame_id_links)
    from pytavia_modules.user import user_activity_proc as _uap_lk2
    if _was_draft_links:
        _uap_lk2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="links", source="create",
        )
    else:
        _uap_lk2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="links", source="edit",
        )
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
        _upload_specs = []
        _welcome_tmp_name = None
        _cover_tmp_name = None
        welcome_img = request.files.get("Sosmed_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                fname = "welcome" + ext
                _upload_specs.append((welcome_img, f"sosmed/_tmp/{tmp_key}/{fname}", {}))
                _welcome_tmp_name = fname
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
                _upload_specs.append((cover_img, f"sosmed/_tmp/{tmp_key}/{fname}", {}))
                _cover_tmp_name = fname
        if _upload_specs:
            _r2.upload_files_parallel(_upload_specs, max_workers=5)
        if _welcome_tmp_name:
            session["sosmed_welcome_tmp_key"] = tmp_key
            session["sosmed_welcome_tmp_name"] = _welcome_tmp_name
            session.modified = True
        if _cover_tmp_name:
            session["sosmed_cover_tmp_key"] = tmp_key
            session["sosmed_cover_tmp_name"] = _cover_tmp_name
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
        # Save draft so Back button can navigate to edit content page
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_sosmed_design_draft", qrcard_id=draft_result["qrcard_id"]))
    stats_carry = None
    if sosmed_data and any(k in sosmed_data for k in ("scan_limit_enabled", "scan_limit_value", "schedule_enabled", "schedule_since", "schedule_until")):
        from pytavia_modules.qr.qr_sosmed_proc import _schedule_date_for_html_input as _sosmed_sched_norm
        stats_carry = {
            "scan_limit_enabled": bool(sosmed_data.get("scan_limit_enabled")),
            "scan_limit_value": sosmed_data.get("scan_limit_value", 0),
            "schedule_enabled": bool(sosmed_data.get("schedule_enabled")),
            "schedule_since": _sosmed_sched_norm(sosmed_data.get("schedule_since")),
            "schedule_until": _sosmed_sched_norm(sosmed_data.get("schedule_until")),
        }
    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
        error_msg=error_msg, sosmed_data=sosmed_data, stats_carry=stats_carry,
    )


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
        from pytavia_modules.user import user_activity_proc as _uap_sm
        _uap_sm.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=request.form.get("qr_name", ""),
            qr_type="sosmed", source="create",
        )
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
    """Overlay db_qrcard_sosmed onto qrcard; QR image / frame / style always from db_qrcard."""
    try:
        sosmed_doc = mgd_db.db_qrcard_sosmed.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    except Exception:
        sosmed_doc = None
    if not sosmed_doc:
        out = dict(qrcard)
    else:
        out = dict(qrcard)
        for key, value in sosmed_doc.items():
            if key != "_id":
                out[key] = value
    _qr_base_proj = {
        "_id": 0,
        "qr_image_url": 1,
        "qr_composite_url": 1,
        "frame_id": 1,
        "qr_dot_style": 1,
        "qr_corner_style": 1,
        "qr_dot_color": 1,
        "qr_bg_color": 1,
        "card_bg_color": 1,
    }
    try:
        base = mgd_db.db_qrcard.find_one(
            {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id, "status": "ACTIVE"},
            _qr_base_proj,
        )
    except Exception:
        base = None
    if base:
        for k, v in base.items():
            out[k] = v
    return out


@app.route("/qr/update/sosmed/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_sosmed(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_sosmed_proc as _qrs
    proc = _qrs.qr_sosmed_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
        if request.form.get("reset_qr_style") == "1":
            _qr_style_unset = {
                "qr_image_url": "",
                "qr_composite_url": "",
                "qr_dot_style": "",
                "qr_corner_style": "",
                "qr_dot_color": "",
                "qr_bg_color": "",
            }
            _mgd.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _qr_style_unset},
            )
            _mgd.db_qrcard_sosmed.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _qr_style_unset},
            )
        if request.form.get("welcome_img_delete") == "1":
            _mgd.db_qrcard_sosmed.update_one({"fk_user_id": fk_user_id, "qrcard_id": qrcard_id}, {"$set": {"welcome_img_url": ""}})
            content_update["welcome_img_url"] = ""
        # --- Parallel R2 uploads for cover + welcome images ---
        import io
        _r2 = r2_mod.r2_storage_proc()
        _upload_specs = []  # (kind, file_obj, key, meta)
        _has_cover_file = False
        _has_cover_static = False
        _has_welcome_file = False
        _has_welcome_static = False

        cover_img = request.files.get("Sosmed_profile_img")
        if cover_img and cover_img.filename:
            cover_img.seek(0, 2)
            if cover_img.tell() <= 2 * 1024 * 1024:
                cover_img.seek(0)
                ext = os.path.splitext(cover_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _has_cover_file = True
                _upload_specs.append(("cover_file", cover_img, f"sosmed/{qrcard_id}/sosmed_cover_img{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed"}))
        _cover_delete = request.form.get("Sosmed_profile_img_delete") == "1"
        cover_asset_url = (request.form.get("sosmed_cover_img_autocomplete_url") or "").strip()
        if cover_asset_url and cover_asset_url.startswith("/static/"):
            local_path = os.path.join(app.root_path, cover_asset_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                unique_cover = f"sosmed_cover_img_{uuid.uuid4().hex[:12]}{ext}"
                try:
                    with open(local_path, "rb") as f:
                        _bio = io.BytesIO(f.read())
                    _upload_specs.append(("cover_static", _bio, f"sosmed/{qrcard_id}/{unique_cover}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed", "file_name": unique_cover}))
                    _has_cover_static = True
                except Exception:
                    pass
        welcome_img = request.files.get("Sosmed_welcome_img")
        if welcome_img and welcome_img.filename:
            welcome_img.seek(0, 2)
            if welcome_img.tell() <= 1024 * 1024:
                welcome_img.seek(0)
                ext = os.path.splitext(welcome_img.filename)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                _has_welcome_file = True
                _upload_specs.append(("welcome_file", welcome_img, f"sosmed/{qrcard_id}/welcome_{int(time.time())}{ext}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed"}))
        welcome_asset_url = (request.form.get("sosmed_welcome_img_autocomplete_url") or "").strip()
        if welcome_asset_url and welcome_asset_url.startswith("/static/"):
            local_path = os.path.join(app.root_path, welcome_asset_url.lstrip("/").replace("/", os.sep))
            if os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"
                unique_welcome = f"welcome_{uuid.uuid4().hex[:12]}{ext}"
                try:
                    with open(local_path, "rb") as f:
                        _bio = io.BytesIO(f.read())
                    _upload_specs.append(("welcome_static", _bio, f"sosmed/{qrcard_id}/{unique_welcome}", {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "sosmed", "file_name": unique_welcome}))
                    _has_welcome_static = True
                except Exception:
                    pass

        _cover_result_url = None
        _welcome_result_url = None
        if _upload_specs:
            _r2_specs = [(s[1], s[2], s[3]) for s in _upload_specs]
            _upload_results = _r2.upload_files_parallel(_r2_specs, max_workers=5)
            for j, (kind, _, _, _) in enumerate(_upload_specs):
                if j < len(_upload_results) and _upload_results[j]["status"] == "success":
                    url = _upload_results[j]["url"]
                    if kind in ("cover_file", "cover_static"):
                        _cover_result_url = url
                    elif kind in ("welcome_file", "welcome_static"):
                        _welcome_result_url = url

        if cover_asset_url:
            if cover_asset_url.startswith("http://") or cover_asset_url.startswith("https://"):
                content_update["Sosmed_cover_img_url"] = cover_asset_url
            elif _has_cover_static and _cover_result_url:
                content_update["Sosmed_cover_img_url"] = _cover_result_url
        elif _cover_delete:
            content_update["Sosmed_cover_img_url"] = ""
        elif _has_cover_file and _cover_result_url:
            content_update["Sosmed_cover_img_url"] = _cover_result_url

        if welcome_asset_url:
            if welcome_asset_url.startswith("http://") or welcome_asset_url.startswith("https://"):
                content_update["welcome_img_url"] = welcome_asset_url
            elif _has_welcome_static and _welcome_result_url:
                content_update["welcome_img_url"] = _welcome_result_url
        elif _has_welcome_file and _welcome_result_url:
            content_update["welcome_img_url"] = _welcome_result_url
        _raw_scan_sos = (request.form.get("scan_limit_value") or "").strip()
        content_update["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        content_update["scan_limit_value"] = int(_raw_scan_sos) if _raw_scan_sos.isdigit() else 0
        content_update["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
        content_update["schedule_since"] = (request.form.get("schedule_since") or "").strip()
        content_update["schedule_until"] = (request.form.get("schedule_until") or "").strip()
        params = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, **content_update}
        if short_code:
            params["short_code"] = short_code
        proc.edit_qrcard(params)
        # PRG: redirect so the browser URL shows the design step (/qr/update/sosmed/qr-design/...)
        # instead of staying on the content POST URL (/qr/update/sosmed/...).
        return redirect(url_for("qr_update_design_sosmed", qrcard_id=qrcard_id))
    return view_update_sosmed.view_update_sosmed(app).update_qr_content_html(qrcard=qrcard, base_url=config.G_BASE_URL)


@app.route("/qr/update/sosmed/qr-design/<qrcard_id>", methods=["GET", "POST"])
def qr_update_design_sosmed(qrcard_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_sosmed_proc as _qrs
    proc = _qrs.qr_sosmed_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
    _raw_lim_sm = (request.form.get("scan_limit_value") or "").strip()
    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
    params["scan_limit_value"] = int(_raw_lim_sm) if _raw_lim_sm.isdigit() else 0
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or "").strip()
    proc.edit_qrcard(params)
    _frame_id_sosmed = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_sosmed)
    _was_draft_sosmed = (database.get_db_conn(config.mainDB).db_qrcard.find_one(
        {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
    _enc_url_sosmed = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_sosmed", "/sosmed/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_sosmed, _frame_id_sosmed)
    from pytavia_modules.user import user_activity_proc as _uap_sm2
    if _was_draft_sosmed:
        _uap_sm2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="sosmed", source="create",
        )
    else:
        _uap_sm2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="sosmed", source="edit",
        )
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
        # Save draft so Back button can navigate to edit content page
        try:
            draft_result = proc.save_draft(request, session, app.root_path)
        except Exception:
            app.logger.exception("allinone save_draft error in qr-design handler")
            draft_result = {"status": "error"}
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_allinone_design_draft", qrcard_id=draft_result["qrcard_id"]))
    return v.new_qr_design_html(url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url, error_msg=error_msg, allinone_data=allinone_data)


@app.route("/qr/new/allinone/save-draft", methods=["POST"])
def qr_new_allinone_save_draft():
    """AJAX endpoint: save allinone QR as DRAFT and return JSON with qrcard_id."""
    import json as _json
    if "fk_user_id" not in session:
        return _json.dumps({"status": "error", "message_desc": "Not authenticated"}), 401, {"Content-Type": "application/json"}
    from pytavia_modules.qr import qr_allinone_proc
    proc = qr_allinone_proc.qr_allinone_proc(app)
    try:
        response = proc.save_draft(request, session, app.root_path)
    except Exception:
        app.logger.exception("allinone save_draft unexpected error")
        response = {"status": "error", "message_desc": "An internal error occurred while saving."}
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
    from pytavia_modules.qr import qr_web_proc as _qwp_draft
    _qwp_draft.qr_web_proc(app)._merge_schedule_from_web_row(fk_user_id, qrcard_id, qrcard)
    from pytavia_modules.qr.qr_web_proc import _schedule_date_for_html_input as _web_sched_norm
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/web/" + sc if sc else None
    _web_pdf_data = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _web_sched_norm(qrcard.get("schedule_since")),
        "schedule_until": _web_sched_norm(qrcard.get("schedule_until")),
    }
    return view_web.view_web(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        pdf_data=_web_pdf_data,
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
    # Draft cards use status DRAFT — do not use get_qrcard() here (it only matches ACTIVE).
    _db = database.get_db_conn(config.mainDB)
    qrcard = _db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}
    if not qrcard or (qrcard.get("qr_type") or "") != "ecard":
        return redirect(url_for("user_qr_list"))
    from pytavia_modules.qr.qr_ecard_proc import _schedule_date_for_html_input as _ecard_sched_norm
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/ecard/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','schedule_enabled','schedule_since','schedule_until','welcome_img_url','qr_dot_style','qr_corner_style','qr_dot_color','qr_bg_color','card_bg_color'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    _stats_carry = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _ecard_sched_norm(qrcard.get("schedule_since")),
        "schedule_until": _ecard_sched_norm(qrcard.get("schedule_until")),
    }
    return view_ecard.view_ecard(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        ecard_data=_data,
        stats_carry=_stats_carry,
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
    if not qrcard or (qrcard.get("qr_type") or "") != "links":
        return redirect(url_for("user_qr_list"))
    from pytavia_modules.qr.qr_links_proc import _schedule_date_for_html_input as _links_draft_sched
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/links/" + sc if sc else None
    _QRCARD_BASE = {
        "qrcard_id", "fk_user_id", "qr_type", "name", "url_content", "short_code", "status", "created_at", "timestamp",
        "stats", "qr_image_url", "design_data", "frame_id", "qr_composite_url",
        "scan_limit_enabled", "scan_limit_value", "schedule_enabled", "schedule_since", "schedule_until", "welcome_img_url",
        "qr_dot_style", "qr_corner_style", "qr_dot_color", "qr_bg_color", "card_bg_color",
    }
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != "_id" and isinstance(v, (str, int, float, bool, type(None)))}
    _stats_carry = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _links_draft_sched(qrcard.get("schedule_since")),
        "schedule_until": _links_draft_sched(qrcard.get("schedule_until")),
    }
    return view_links.view_links(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        links_data=_data, stats_carry=_stats_carry,
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
    if not qrcard or (qrcard.get("qr_type") or "") != "sosmed":
        return redirect(url_for("user_qr_list"))
    from pytavia_modules.qr.qr_sosmed_proc import _schedule_date_for_html_input as _sosmed_draft_sched
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/sosmed/" + sc if sc else None
    _QRCARD_BASE = {
        "qrcard_id", "fk_user_id", "qr_type", "name", "url_content", "short_code", "status", "created_at", "timestamp",
        "stats", "qr_image_url", "design_data", "frame_id", "qr_composite_url",
        "scan_limit_enabled", "scan_limit_value", "schedule_enabled", "schedule_since", "schedule_until", "welcome_img_url",
        "qr_dot_style", "qr_corner_style", "qr_dot_color", "qr_bg_color", "card_bg_color",
    }
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != "_id" and isinstance(v, (str, int, float, bool, type(None)))}
    _stats_carry = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _sosmed_draft_sched(qrcard.get("schedule_since")),
        "schedule_until": _sosmed_draft_sched(qrcard.get("schedule_until")),
    }
    return view_sosmed.view_sosmed(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        sosmed_data=_data, stats_carry=_stats_carry,
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
    from pytavia_modules.qr import qr_images_proc as _qip_d
    _qip_d.qr_images_proc(app).merge_stats_from_images_row(fk_user_id, qrcard_id, qrcard)
    from pytavia_modules.qr.qr_images_proc import _schedule_date_for_html_input as _img_sched_norm
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/images/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','schedule_enabled','schedule_since','schedule_until','welcome_img_url','qr_dot_style','qr_corner_style','qr_dot_color','qr_bg_color','card_bg_color'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    _stats_carry = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _img_sched_norm(qrcard.get("schedule_since")),
        "schedule_until": _img_sched_norm(qrcard.get("schedule_until")),
    }
    return view_images.view_images(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        images_data=_data,
        stats_carry=_stats_carry,
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
    if not qrcard or (qrcard.get("qr_type") or "") != "video":
        return redirect(url_for("user_qr_list"))
    from pytavia_modules.qr.qr_video_proc import _schedule_date_for_html_input as _vid_sched_norm
    sc = qrcard.get("short_code", "")
    qr_encode_url = config.G_BASE_URL.rstrip("/") + "/video/" + sc if sc else None
    _QRCARD_BASE = {'qrcard_id','fk_user_id','qr_type','name','url_content','short_code','status','created_at','timestamp','stats','qr_image_url','design_data','frame_id','qr_composite_url','scan_limit_enabled','scan_limit_value','schedule_enabled','schedule_since','schedule_until','welcome_img_url','qr_dot_style','qr_corner_style','qr_dot_color','qr_bg_color','card_bg_color'}
    _data = {k: v for k, v in qrcard.items() if k not in _QRCARD_BASE and k != '_id' and isinstance(v, (str, int, float, bool, type(None)))}
    _stats_carry = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _vid_sched_norm(qrcard.get("schedule_since")),
        "schedule_until": _vid_sched_norm(qrcard.get("schedule_until")),
    }
    return view_video.view_video(app).new_qr_design_html(
        url_content=qrcard.get("url_content", ""), qr_name=qrcard.get("name", ""),
        short_code=sc, qr_encode_url=qr_encode_url, qrcard_id=qrcard_id,
        video_data=_data,
        stats_carry=_stats_carry,
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
    _base_sd = _db_sd.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    if _base_sd:
        _m = dict(qrcard)
        for _k in ("schedule_enabled", "schedule_since", "schedule_until", "scan_limit_enabled", "scan_limit_value"):
            if _k in _base_sd:
                _m[_k] = _base_sd[_k]
        qrcard = _m
    from pytavia_modules.qr.qr_special_proc import _schedule_date_for_html_input as _sp_sched_draft
    _stats_carry_draft = {
        "scan_limit_enabled": qrcard.get("scan_limit_enabled"),
        "scan_limit_value": qrcard.get("scan_limit_value", 0),
        "schedule_enabled": qrcard.get("schedule_enabled"),
        "schedule_since": _sp_sched_draft(qrcard.get("schedule_since")) if qrcard.get("schedule_since") else "",
        "schedule_until": _sp_sched_draft(qrcard.get("schedule_until")) if qrcard.get("schedule_until") else "",
    }
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
        stats_carry=_stats_carry_draft,
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
    """Overlay db_qrcard_allinone onto qrcard; QR image/style fields stay authoritative from db_qrcard."""
    try:
        allinone_doc = mgd_db.db_qrcard_allinone.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
        base_doc = mgd_db.db_qrcard.find_one({"qrcard_id": qrcard_id, "fk_user_id": fk_user_id})
    except Exception:
        allinone_doc = None
        base_doc = None
    merged = dict(qrcard or {})
    if allinone_doc:
        for key, value in allinone_doc.items():
            if key != "_id":
                merged[key] = value
    if base_doc:
        for key in (
            "qr_image_url",
            "qr_composite_url",
            "qr_dot_style",
            "qr_corner_style",
            "qr_dot_color",
            "qr_bg_color",
            "card_bg_color",
        ):
            val = base_doc.get(key)
            if val not in (None, ""):
                merged[key] = val
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
        if request.form.get("back_from_design"):
            return view_update_allinone.view_update_allinone(app).update_qr_content_html(
                qrcard=qrcard, base_url=config.G_BASE_URL
            )
        _mgd_aio = database.get_db_conn(config.mainDB)
        if request.form.get("reset_qr_style") == "1":
            _qr_unset_aio = {
                "qr_image_url": "",
                "qr_composite_url": "",
                "qr_dot_style": "",
                "qr_corner_style": "",
                "qr_dot_color": "",
                "qr_bg_color": "",
            }
            _mgd_aio.db_qrcard.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _qr_unset_aio},
            )
            _mgd_aio.db_qrcard_allinone.update_one(
                {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                {"$unset": _qr_unset_aio},
            )
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
    if request.form.get("reset_qr_style") == "1":
        _mgd_rs = database.get_db_conn(config.mainDB)
        _unset_qr_aio = {
            "qr_image_url": "",
            "qr_composite_url": "",
            "qr_dot_style": "",
            "qr_corner_style": "",
            "qr_dot_color": "",
            "qr_bg_color": "",
            "card_bg_color": "",
        }
        _mgd_rs.db_qrcard.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {"$unset": _unset_qr_aio},
        )
        _mgd_rs.db_qrcard_allinone.update_one(
            {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
            {"$unset": {"qr_image_url": "", "qr_composite_url": ""}},
        )
    design_update = {}
    for key in request.form:
        if key.startswith("Allinone_") and not key.endswith("[]"):
            val = request.form.get(key)
            if val is not None:
                design_update[key] = val.strip()
    if request.form.get("Allinone_font_apply_all") in ("on", "true", "1", "yes"):
        design_update["Allinone_font_apply_all"] = True
    _aio_lim = (request.form.get("scan_limit_value") or "").strip()
    design_update["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
    design_update["scan_limit_value"] = int(_aio_lim) if _aio_lim.isdigit() else 0
    design_update["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
    design_update["schedule_since"] = (request.form.get("schedule_since") or "").strip()
    design_update["schedule_until"] = (request.form.get("schedule_until") or "").strip()
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
    from pytavia_modules.user import user_activity_proc as _uap_aio2
    if qrcard.get("status") == "DRAFT":
        _uap_aio2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=qrcard.get("name", ""), qr_type="allinone", source="create",
        )
    else:
        _uap_aio2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=qrcard.get("name", ""), qr_type="allinone", source="edit",
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
        _raw_lim = (request.form.get("scan_limit_value") or "").strip()
        _content_stats = {
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": _raw_lim if _raw_lim.isdigit() else "100",
        }
        return v.new_qr_content_html(
            base_url=config.G_BASE_URL,
            url_content=url_content,
            qr_name=qr_name,
            short_code=short_code,
            special_sections=special_sections,
            content_stats_prefill=_content_stats,
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
        _sp_stats_pref = {
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": (lambda r: r if r.isdigit() else "100")((request.form.get("scan_limit_value") or "").strip()),
        }
        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections, content_stats_prefill=_sp_stats_pref)
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2-32 characters: letters, numbers, '-' or '_'."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections, content_stats_prefill=_sp_stats_pref)
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, special_sections=special_sections, content_stats_prefill=_sp_stats_pref)
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/special/" + short_code
    _raw_lim2 = (request.form.get("scan_limit_value") or "").strip() if request.method == "POST" else ""
    _stats_carry_new = {}
    if request.method == "POST":
        _stats_carry_new = {
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(_raw_lim2) if _raw_lim2.isdigit() else 0,
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
        }
    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code,
        qr_encode_url=qr_encode_url, error_msg=error_msg, special_sections=special_sections,
        stats_carry=_stats_carry_new,
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
        from pytavia_modules.user import user_activity_proc as _uap_sp
        _uap_sp.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=request.form.get("qr_name", ""),
            qr_type="special", source="create",
        )
        return redirect(url_for("user_qr_list"))
    _rl_err = (request.form.get("scan_limit_value") or "").strip()
    return view_special.view_special(app).new_qr_design_html(
        url_content=response.get("url_content", ""),
        qr_name=response.get("qr_name", ""),
        short_code=response.get("short_code", ""),
        qr_encode_url=response.get("qr_encode_url"),
        error_msg=response.get("error_msg", "Save failed."),
        special_sections=response.get("special_sections", []),
        stats_carry={
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(_rl_err) if _rl_err.isdigit() else 0,
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": (request.form.get("schedule_since") or "").strip(),
            "schedule_until": (request.form.get("schedule_until") or "").strip(),
        },
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
            draft["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
            _rl_b = (request.form.get("scan_limit_value") or "").strip()
            draft["scan_limit_value"] = int(_rl_b) if _rl_b.isdigit() else int(draft.get("scan_limit_value") or 0)
            draft["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
            draft["schedule_since"] = (request.form.get("schedule_since") or "").strip()
            draft["schedule_until"] = (request.form.get("schedule_until") or "").strip()
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
        extra_data["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled"))
        raw_limit = (request.form.get("scan_limit_value") or "").strip()
        extra_data["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
        extra_data["schedule_enabled"] = bool(request.form.get("schedule_enabled"))
        extra_data["schedule_since"] = (request.form.get("schedule_since") or "").strip()
        extra_data["schedule_until"] = (request.form.get("schedule_until") or "").strip()

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

        if request.form.get("reset_qr_style") == "1":
            _unset_sp = {
                "qr_composite_url": "",
                "qr_image_url": "",
                "qr_dot_style": "",
                "qr_corner_style": "",
                "qr_dot_color": "",
                "qr_bg_color": "",
                "card_bg_color": "",
            }
            try:
                _mgd_rs = database.get_db_conn(config.mainDB)
                _mgd_rs.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$unset": _unset_sp},
                )
                _mgd_rs.db_qrcard_special.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id},
                    {"$unset": {"qr_composite_url": "", "qr_image_url": ""}},
                )
            except Exception:
                pass
            for _uk in _unset_sp:
                qrcard.pop(_uk, None)

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
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()
    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _frame_id_special = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_special)
    _was_draft_special = (database.get_db_conn(config.mainDB).db_qrcard.find_one(
        {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
    _enc_url_special = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_special", "/special/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_special, _frame_id_special)
    from pytavia_modules.user import user_activity_proc as _uap_sp2
    if _was_draft_special:
        _uap_sp2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="special", source="create",
        )
    else:
        _uap_sp2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="special", source="edit",
        )
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
        
        _img_stats_keys = frozenset([
            "scan_limit_enabled", "scan_limit_value",
            "schedule_enabled", "schedule_since", "schedule_until",
        ])
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code", "images_files"] and key not in _img_stats_keys:
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): images_data[key] = val_list
                else: images_data[key] = val_list[0] if val_list else ""

        from pytavia_modules.qr.qr_images_proc import _schedule_date_for_html_input as _legacy_img_sched
        _stats_carry_legacy = {
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(request.form.get("scan_limit_value") or 0) if str(request.form.get("scan_limit_value") or "").strip().isdigit() else (request.form.get("scan_limit_value") or ""),
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": _legacy_img_sched(request.form.get("schedule_since")),
            "schedule_until": _legacy_img_sched(request.form.get("schedule_until")),
        }

        def _images_content_payload(base):
            o = dict(base)
            o["scan_limit_enabled"] = _stats_carry_legacy["scan_limit_enabled"]
            o["scan_limit_value"] = _stats_carry_legacy["scan_limit_value"]
            o["schedule_enabled"] = _stats_carry_legacy["schedule_enabled"]
            o["schedule_since"] = _stats_carry_legacy["schedule_since"]
            o["schedule_until"] = _stats_carry_legacy["schedule_until"]
            return o

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
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=_images_content_payload(images_data))

        if not proc.is_name_unique(session.get("fk_user_id"), qr_name):
            error_msg = "A QR card with this name already exists. Please choose a unique name."
            return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=_images_content_payload(images_data))
        if short_code:
            if not re.match(r"^[a-z0-9_-]{2,32}$", short_code):
                error_msg = "Address identifier must be 2–32 characters: letters, numbers, '-' or '_', no spaces or other symbols."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=_images_content_payload(images_data))
            if not proc.is_short_code_unique(short_code):
                error_msg = "This address identifier is already in use. Please choose another."
                return v.new_qr_content_html(error_msg=error_msg, base_url=config.G_BASE_URL, url_content=url_content, qr_name=qr_name, short_code=short_code, images_data=_images_content_payload(images_data))
        else:
            short_code = proc._generate_short_code()
            while not proc.is_short_code_unique(short_code):
                short_code = proc._generate_short_code()
        qr_encode_url = config.G_BASE_URL + "/images/" + short_code

        # Save as draft so design page has a qrcard_id for proper back navigation
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_images_design_draft", qrcard_id=draft_result["qrcard_id"]))

        return v.new_qr_design_html(
            url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
            error_msg=error_msg, images_data=images_data, stats_carry=_stats_carry_legacy,
        )

    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
        error_msg=error_msg, images_data=images_data, stats_carry=None,
    )

@app.route("/qr/save/images", methods=["POST"])
def qr_save_images():
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_images_proc
    from pytavia_modules.view import view_images
    response = qr_images_proc.qr_images_proc(app).complete_images_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_img
        _uap_img.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=request.form.get("qr_name", ""),
            qr_type="images", source="create",
        )
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
    stats_carry = None

    if request.method == "POST":
        url_content = request.form.get("url_content", "QRkartu")
        if url_content and not url_content.startswith("http://") and not url_content.startswith("https://"):
            url_content = "https://" + url_content
        qr_name = request.form.get("qr_name", "Untitled QR")
        short_code = (request.form.get("short_code") or "").strip().lower()

        _vid_stats_keys = frozenset([
            "scan_limit_enabled", "scan_limit_value",
            "schedule_enabled", "schedule_since", "schedule_until",
        ])
        for key in request.form:
            if key not in ["csrf_token", "url_content", "qr_name", "short_code"] and key not in _vid_stats_keys:
                if key in ["video_type[]", "video_url[]", "video_name[]", "video_desc[]"]: continue
                val_list = request.form.getlist(key)
                if len(val_list) > 1 or key.endswith("[]"): video_data[key] = val_list
                else: video_data[key] = val_list[0] if val_list else ""

        from pytavia_modules.qr.qr_video_proc import _schedule_date_for_html_input as _legacy_vid_sched
        stats_carry = {
            "scan_limit_enabled": bool(request.form.get("scan_limit_enabled")),
            "scan_limit_value": int(request.form.get("scan_limit_value") or 0) if str(request.form.get("scan_limit_value") or "").strip().isdigit() else (request.form.get("scan_limit_value") or ""),
            "schedule_enabled": bool(request.form.get("schedule_enabled")),
            "schedule_since": _legacy_vid_sched(request.form.get("schedule_since")),
            "schedule_until": _legacy_vid_sched(request.form.get("schedule_until")),
        }

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

        # Collect upload specs for parallel execution
        _vid_upload_specs = []
        _vid_upload_meta = []  # (safe_name, name, desc)
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
                            _vid_upload_specs.append((f, f"videos/_tmp/{tmp_key}/{safe_name}", None))
                            _vid_upload_meta.append({"safe_name": safe_name, "name": name.strip(), "desc": desc.strip()})
                        else:
                            error_msg = f"Video {f.filename} exceeds 50MB limit."
            else:
                if url.strip():
                    embed_url = _get_video_embed_url(url.strip())
                    tmp_gallery.append({"type": "link", "url": embed_url, "name": name.strip(), "desc": desc.strip()})

        # ── Welcome image upload ──
        _welcome_upload_spec = None
        _welcome_wkey = None
        _welcome_wext = None
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
                    _wext = os.path.splitext(welcome_img_file.filename)[1].lower() or ".jpg"
                    _wkey = session.get("video_welcome_img_tmp_key") or _uuid.uuid4().hex
                    session["video_welcome_img_tmp_key"] = _wkey
                    session["video_welcome_img_tmp_name"] = "welcome" + _wext
                    _welcome_upload_spec = (welcome_img_file, f"video/_tmp/{_wkey}/welcome{_wext}", None)
                    _welcome_wkey = _wkey
                    _welcome_wext = _wext
                else:
                    error_msg = "Welcome image exceeds 1 MB limit."
            # Preserve existing URL if already uploaded previously
            existing_url = session.get("video_welcome_img_url", "")
            if existing_url:
                video_data["welcome_img_url"] = existing_url

        # Execute all uploads in parallel
        _all_upload_specs = []
        if _welcome_upload_spec:
            _all_upload_specs.append(("welcome", _welcome_upload_spec))
        for idx, spec in enumerate(_vid_upload_specs):
            _all_upload_specs.append(("video", spec))

        if _all_upload_specs:
            _par_results = _r2.upload_files_parallel([s[1] for s in _all_upload_specs])
            for idx, _pr in enumerate(_par_results):
                _tag = _all_upload_specs[idx][0]
                if _tag == "welcome" and _pr["status"] == "success":
                    pass  # session keys already set above
                elif _tag == "video" and _pr["status"] == "success":
                    _vi = _vid_upload_meta[idx - (1 if _welcome_upload_spec else 0)]
                    tmp_gallery.append({"type": "upload", "safe_name": _vi["safe_name"], "name": _vi["name"], "desc": _vi["desc"]})
        else:
            for _vi in _vid_upload_meta:
                tmp_gallery.append({"type": "upload", "safe_name": _vi["safe_name"], "name": _vi["name"], "desc": _vi["desc"]})

        session["video_tmp_gallery"] = tmp_gallery
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
        # Save as draft so design page has a qrcard_id for proper back navigation
        draft_result = proc.save_draft(request, session, app.root_path)
        if draft_result.get("status") == "ok":
            return redirect(url_for("qr_new_video_design_draft", qrcard_id=draft_result["qrcard_id"]))

    return v.new_qr_design_html(
        url_content=url_content, qr_name=qr_name, short_code=short_code, qr_encode_url=qr_encode_url,
        error_msg=error_msg, video_data=video_data, stats_carry=stats_carry,
    )

@app.route("/qr/save/video", methods=["POST"])
def qr_save_video():
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    from pytavia_modules.qr import qr_video_proc
    from pytavia_modules.view import view_video
    response = qr_video_proc.qr_video_proc(app).complete_video_save(request, session, app.root_path)
    if response.get("success"):
        _update_frame_id(session.get("fk_user_id"), response.get("qrcard_id", ""), request.form.get("frame_id", ""))
        from pytavia_modules.user import user_activity_proc as _uap_vid
        _uap_vid.user_activity_proc(app).log(
            fk_user_id=session.get("fk_user_id"), action="CREATE_QR",
            qrcard_id=response.get("qrcard_id", ""),
            qr_name=request.form.get("qr_name", ""),
            qr_type="video", source="create",
        )
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
        _valid_new = []
        for i, f in enumerate(new_files):
            if f and f.filename and f.filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                f.seek(0, 2)
                if f.tell() <= 2 * 1024 * 1024:
                    f.seek(0)
                    _valid_new.append((i, f))
        # Welcome image: check upload eligibility early so it can join parallel batch
        _welcome_delete = request.form.get("images_welcome_img_delete") == "1"
        _welcome_img = request.files.get("images_welcome_img")
        _welcome_asset_url = (request.form.get("images_welcome_img_autocomplete_url") or "").strip()
        _welcome_spec = None
        if not _welcome_delete and _welcome_img and _welcome_img.filename:
            _welcome_img.seek(0, 2)
            _welcome_size = _welcome_img.tell()
            _welcome_img.seek(0)
            if _welcome_size <= 1024 * 1024:
                _ext = os.path.splitext(_welcome_img.filename)[1].lower() or ".jpg"
                if _ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    _ext = ".jpg"
                _safe = "welcome_" + _uuid.uuid4().hex[:12] + _ext
                _key = f"images/{qrcard_id}/{_safe}"
                _welcome_spec = (_welcome_img, _key, {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "images", "file_name": _safe})

        # Build parallel upload specs: gallery files + welcome image
        _all_specs = []
        _welcome_spec_idx = None
        if _valid_new:
            for i, f in _valid_new:
                ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
                safe_name = _uuid.uuid4().hex + ext
                r2_key = f"images/{qrcard_id}/{safe_name}"
                _all_specs.append((f, r2_key, {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "images", "file_name": safe_name}))
        if _welcome_spec:
            _welcome_spec_idx = len(_all_specs)
            _all_specs.append(_welcome_spec)

        if _all_specs:
            _upload_results = _r2.upload_files_parallel(_all_specs, max_workers=5)

        # Process gallery upload results
        _gallery_results = _upload_results[:len(_valid_new)] if _valid_new else []
        for j, result in enumerate(_gallery_results):
            if result["status"] != "success":
                continue
            i, f = _valid_new[j]
            form_idx = new_file_offset + i
            name = images_names[form_idx] if form_idx < len(images_names) else ""
            desc = images_descs[form_idx] if form_idx < len(images_descs) else ""
            updated_gallery.append({
                "url": result["url"],
                "name": name,
                "desc": desc
            })

        # Process welcome image upload result
        if _welcome_spec_idx is not None and _welcome_spec_idx < len(_upload_results):
            _wres = _upload_results[_welcome_spec_idx]
            if _wres["status"] == "success":
                images_data["welcome_img_url"] = _wres["url"]
                qrcard["welcome_img_url"] = _wres["url"]

        # Welcome image: delete or pick-from-assets (non-upload branches)
        if _welcome_delete:
            images_data["welcome_img_url"] = ""
            qrcard["welcome_img_url"] = ""
        elif _welcome_asset_url and _welcome_spec is None:
            images_data["welcome_img_url"] = _welcome_asset_url
            qrcard["welcome_img_url"] = _welcome_asset_url

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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()

    _img_skip = frozenset([
        "csrf_token", "url_content", "qr_name", "short_code",
        "scan_limit_enabled", "scan_limit_value",
        "schedule_enabled", "schedule_since", "schedule_until",
    ])
    for key in request.form:
        if key not in _img_skip:
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
    _was_draft_images = (database.get_db_conn(config.mainDB).db_qrcard.find_one(
        {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
    _enc_url_images = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_images", "/images/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_images, _frame_id_images)
    from pytavia_modules.user import user_activity_proc as _uap_img2
    if _was_draft_images:
        _uap_img2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="images", source="create",
        )
    else:
        _uap_img2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="images", source="edit",
        )
    return redirect(url_for("user_qr_list"))


@app.route("/qr/update/video/<qrcard_id>", methods=["GET", "POST"])
def qr_update_content_video(qrcard_id):
    from flask import request
    if "fk_user_id" not in session: return redirect(url_for("login_view"))
    fk_user_id = session.get("fk_user_id")
    from pytavia_modules.qr import qr_video_proc as _qrp
    from pytavia_modules.view import view_update_video
    proc = _qrp.qr_video_proc(app)
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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
                _welcome_meta = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "video", "file_name": _safe}
                # Collect for parallel upload — will execute after video specs collected
                _has_welcome_upload = True
            else:
                _has_welcome_upload = False
        else:
            _has_welcome_upload = False

        video_files = request.files.getlist("video_files")
        video_types = request.form.getlist("video_type[]")
        video_urls = request.form.getlist("video_url[]")
        video_names = request.form.getlist("video_name[]")
        video_descs = request.form.getlist("video_desc[]")

        updated_links = []
        file_idx = 0

        if not video_types and video_urls:
            video_types = ['link'] * len(video_urls)

        # Collect video upload specs for parallel execution
        _vid_upload_specs = []
        _vid_upload_meta = []
        for i, vtype in enumerate(video_types):
            url = video_urls[i] if i < len(video_urls) else ""
            name = video_names[i] if i < len(video_names) else ""
            desc = video_descs[i] if i < len(video_descs) else ""

            if vtype == 'upload':
                if url.strip() and not url.startswith('/static/uploads/'):
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
                                _v_meta = {"fk_user_id": fk_user_id, "qrcard_id": qrcard_id, "qr_type": "video", "file_name": safe_name}
                                _vid_upload_specs.append((f, r2_key, _v_meta))
                                _vid_upload_meta.append({"name": name.strip(), "desc": desc.strip()})
            else:
                if url.strip():
                    embed_url = _get_video_embed_url(url.strip())
                    updated_links.append({"url": embed_url, "name": name.strip(), "desc": desc.strip()})

        # Build combined upload list: welcome + video uploads
        _all_specs = []
        if _has_welcome_upload:
            _all_specs.append(("welcome", (_welcome_img, _key, _welcome_meta)))
        for idx, spec in enumerate(_vid_upload_specs):
            _all_specs.append(("video", spec))

        if _all_specs:
            _par_results = _r2.upload_files_parallel([s[1] for s in _all_specs])
            for idx, _pr in enumerate(_par_results):
                _tag = _all_specs[idx][0]
                if _tag == "welcome" and _pr["status"] == "success":
                    _welcome_url = _pr["url"]
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
                elif _tag == "video" and _pr["status"] == "success":
                    _vm = _vid_upload_meta[idx - (1 if _has_welcome_upload else 0)]
                    updated_links.append({"url": _pr["url"], "name": _vm["name"], "desc": _vm["desc"]})
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
    qrcard = proc.get_qrcard(fk_user_id, qrcard_id, allow_draft=True)
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

    # Use draft values as base
    for key, val in draft.items():
        if key not in ["url_content", "qr_name", "short_code"]:
            params[key] = val

    _vid_skip = frozenset([
        "csrf_token", "url_content", "qr_name", "short_code",
        "scan_limit_enabled", "scan_limit_value",
        "schedule_enabled", "schedule_since", "schedule_until",
    ])
    for key in request.form:
        if key not in _vid_skip:
            val_list = request.form.getlist(key)
            if len(val_list) > 1 or key.endswith("[]"): params[key] = val_list
            else: params[key] = val_list[0] if val_list else ""

    params["scan_limit_enabled"] = bool(request.form.get("scan_limit_enabled") or draft.get("scan_limit_enabled"))
    raw_limit = (request.form.get("scan_limit_value") or "").strip() or str(draft.get("scan_limit_value") or "")
    params["scan_limit_value"] = int(raw_limit) if raw_limit.isdigit() else 0
    params["schedule_enabled"] = bool(request.form.get("schedule_enabled") or draft.get("schedule_enabled"))
    params["schedule_since"] = (request.form.get("schedule_since") or draft.get("schedule_since") or "").strip()
    params["schedule_until"] = (request.form.get("schedule_until") or draft.get("schedule_until") or "").strip()

    proc.edit_qrcard(params)
    _clear_qr_draft(session, qrcard_id)
    _frame_id_video = request.form.get("frame_id", "")
    _update_frame_id(fk_user_id, qrcard_id, _frame_id_video)
    _was_draft_video = (database.get_db_conn(config.mainDB).db_qrcard.find_one(
        {"qrcard_id": qrcard_id, "fk_user_id": fk_user_id}) or {}).get("status") == "DRAFT"
    _enc_url_video = _activate_draft_qrcard(fk_user_id, qrcard_id, "db_qrcard_video", "/video/")
    _save_custom_qr_image(fk_user_id, qrcard_id, request.form.get("qr_image_data", ""), {
        "qr_dot_style": request.form.get("qr_dot_style", "square"),
        "qr_corner_style": request.form.get("qr_corner_style", "square"),
        "qr_dot_color": request.form.get("qr_dot_color", "#000000"),
        "qr_bg_color": request.form.get("qr_bg_color", "#ffffff"),
        "card_bg_color": request.form.get("card_bg_color", "#ffffff"),
    })
    _save_qr_composite(app, fk_user_id, qrcard_id, _enc_url_video, _frame_id_video)
    from pytavia_modules.user import user_activity_proc as _uap_vid2
    if _was_draft_video:
        _uap_vid2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="CREATE_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="video", source="create",
        )
    else:
        _uap_vid2.user_activity_proc(app).log(
            fk_user_id=fk_user_id, action="EDIT_QR",
            qrcard_id=qrcard_id, qr_name=request.form.get("qr_name", ""),
            qr_type="video", source="edit",
        )
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
    fk_user_id = session.get("fk_user_id")
    _sync_user_qr_activation_quota(fk_user_id)
    return view_qr_list.view_qr_list(app).my_qr_codes_html(
        fk_user_id=fk_user_id,
        error_msg=request.args.get("error_msg"),
    )

@app.route("/user/stats")
def user_stats():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session["fk_user_id"]
    _db = database.get_db_conn(config.mainDB)
    qrcards = list(_db.db_qrcard.find(
        {"fk_user_id": fk_user_id, "status": {"$nin": ["DELETED", "SOFT_DELETED", "DRAFT"]}},
        {"_id": 0, "stats": 1, "created_at": 1}
    ))
    total_qr = len(qrcards)
    total_scans = sum((q.get("stats") or {}).get("scan_count", 0) for q in qrcards)
    sub_info = _get_sub_info(fk_user_id)
    stats_data = {
        "total_qr": total_qr,
        "total_scans": total_scans,
    }
    return view_user.view_user(app).stats_html(stats=stats_data, sub_info=sub_info)

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
        from pytavia_modules.user import asset_tracker_proc as _atp
        from pytavia_core import database as _db_mod, config as _cfg

        fk_user_id = session["fk_user_id"]
        garbage = _usp.user_storage_proc(app).get_garbage_files(fk_user_id)
        if not garbage:
            return jsonify({"ok": True, "deleted": 0, "freed_bytes": 0, "freed_fmt": "0 B"})

        tracker = _atp.asset_tracker_proc(app)
        freed_bytes = 0
        deleted = 0
        for f in garbage:
            key = f.get("r2_key", "")
            if not key:
                continue
            tracker.soft_delete_key(key)
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

        # Calculate freed bytes before soft-deleting
        from pytavia_modules.user.asset_tracker_proc import asset_tracker_proc as _atp_st2
        _tracker_st2 = _atp_st2()
        qr_size_info = _tracker_st2.get_qr_size(qrcard_id)
        freed_bytes  = qr_size_info.get("bytes", 0)
        freed_count  = qr_size_info.get("files", 0)

        # Soft-delete tracked assets (no R2 deletion — deferred to admin bulk cleanup)
        _tracker_st2.soft_delete_qr(qrcard_id)

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

        from pytavia_modules.user.user_storage_proc import _fmt_size as _fmt_sz
        return jsonify({"ok": True, "deleted_count": freed_count, "freed_bytes": freed_bytes, "freed_fmt": _fmt_sz(freed_bytes)})
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


def _parse_rp_idr(s):
    """Parse Indonesian Rupiah display like 'Rp 4.400' to integer IDR."""
    s = (s or "").strip()
    if s.lower().startswith("rp"):
        s = s[2:].lstrip(". ").strip()
    s = s.replace(" ", "").replace(".", "")
    if s.isdigit():
        return int(s)
    return 0


def _compute_admin_fee_idr_for_payment(base_idr, fee_str):
    """Admin/payment fee in IDR from labels in payment-methods.json (e.g. '1,67%', 'Rp 4.400', '2,90% + Rp 2.500')."""
    if not fee_str or not str(fee_str).strip():
        return 0
    s = str(fee_str).strip()
    if "+" in s:
        return sum(
            _fee_part_idr(base_idr, p.strip()) for p in s.split("+")
        )
    return _fee_part_idr(base_idr, s)


def _fee_part_idr(base_idr, part):
    part = (part or "").strip()
    if not part:
        return 0
    if "%" in part:
        num = part.replace("%", "").replace(",", ".").strip()
        try:
            pct = float(num) / 100.0
        except ValueError:
            return 0
        return int(round(base_idr * pct))
    return _parse_rp_idr(part)


def _load_payment_methods_json(root_path):
    import os
    json_path = os.path.join(root_path, "static", "json_file", "payment-methods.json")
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _enrich_payment_categories_with_fees(categories, duration_options):
    """Attach fee map per duration, method metadata for checkout."""
    out = []
    duration_options = duration_options or []
    default_option = _find_duration_option(duration_options, 1) or (duration_options[0] if duration_options else {})
    for cat in categories or []:
        row = {"name": cat.get("name", ""), "payments": []}
        for pay in cat.get("payments", []):
            fee_str = pay.get("fee", "")
            fee_map = {}
            for opt in duration_options:
                m = str(int(opt.get("months", 0)))
                fee_map[m] = _compute_admin_fee_idr_for_payment(int(opt.get("final_price_idr", 0)), fee_str)
            fee_idr = fee_map.get("1", _compute_admin_fee_idr_for_payment(int(default_option.get("final_price_idr", 0)), fee_str))
            merchants = pay.get("merchants") or []
            code = merchants[0].get("id", "") if merchants else ""
            label = ", ".join(m.get("name", "") for m in merchants) or code
            row["payments"].append({
                "merchants": merchants,
                "fee": fee_str,
                "fee_idr": fee_idr,
                "fee_idr_by_month": fee_map,
                "method_code": code,
                "display_label": label,
            })
        out.append(row)
    return out


def _fee_string_for_payment_method(categories, method_code):
    for cat in categories or []:
        for pay in cat.get("payments", []):
            merchants = pay.get("merchants") or []
            if merchants and merchants[0].get("id") == method_code:
                return pay.get("fee", "")
    return None


def _payment_method_label_for_code(categories, method_code):
    for cat in categories or []:
        for pay in cat.get("payments", []):
            merchants = pay.get("merchants") or []
            if merchants and merchants[0].get("id") == method_code:
                return ", ".join(m.get("name", "") for m in merchants) or method_code
    return method_code or "-"


@app.route("/user/plans/checkout", methods=["GET", "POST"])
def user_plans_checkout():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_plans, config as _cfg_plans
    import time
    from pytavia_stdlib import idgen
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    fk_user_id = session["fk_user_id"]
    
    if request.method == "POST":
        plan_id = request.form.get("plan_id", "")
        payment_method = request.form.get("payment_method", "")
        try:
            purchase_months = int(request.form.get("purchase_months", "1"))
        except Exception:
            purchase_months = 1
        plan_doc = _db.db_plan_definition.find_one({"plan_id": plan_id})
        
        if not plan_doc or not payment_method:
            return redirect(url_for("user_plans"))
        duration_options = _build_checkout_duration_options(plan_doc)
        selected_duration = _find_duration_option(duration_options, purchase_months)
        if not selected_duration:
            selected_duration = _find_duration_option(duration_options, 1)
        if not selected_duration:
            return redirect(url_for("user_plans"))

        purchase_months = int(selected_duration.get("months", 1))
        plan_price_idr = int(selected_duration.get("final_price_idr", 0))
        subtotal_price_idr = int(selected_duration.get("subtotal_idr", plan_price_idr))
        discount_idr = int(selected_duration.get("discount_idr", 0))
        discount_pct = int(selected_duration.get("discount_pct", 0))
        period_days = int(selected_duration.get("period_days", int(plan_doc.get("period_days", 30))))

        pm_categories = _load_payment_methods_json(app.root_path)
        fee_label = _fee_string_for_payment_method(pm_categories, payment_method)
        if fee_label is None:
            return redirect(url_for("user_plans"))
        admin_fee_idr = _compute_admin_fee_idr_for_payment(plan_price_idr, fee_label)
        amount_idr = plan_price_idr + admin_fee_idr
        
        user_doc = _db.db_user.find_one({"pkey": fk_user_id})
        user_email = user_doc.get("email", "user@qrkartu.com") if user_doc else "user@qrkartu.com"
        
        sub_id = idgen._get_api_call_id()
        now_ts = int(time.time())
        
        # --- Duitku API Integration ---
        import requests
        import hashlib
        
        merchant_code = getattr(_cfg_plans, "G_DUITKU_MERCHANT_CODE", "")
        api_key = getattr(_cfg_plans, "G_DUITKU_MERCHANT_KEY", "")
        
        base_api = getattr(_cfg_plans, "G_DUIKU_INQUIRY_URL", "https://sandbox.duitku.com/webapi/api/merchant/v2/inquiry")
        
        # md5(merchantCode + merchantOrderId + paymentAmount + apiKey)
        sig_str = f"{merchant_code}{sub_id}{amount_idr}{api_key}"
        signature = hashlib.md5(sig_str.encode('utf-8')).hexdigest()
        
        payload = {
            "merchantCode": merchant_code,
            "paymentAmount": amount_idr,
            "merchantOrderId": sub_id,
            "productDetails": f"Subscription {plan_doc.get('name', plan_id)}",
            "email": user_email,
            "paymentMethod": payment_method,
            "returnUrl": getattr(_cfg_plans, "G_BASE_URL", "http://127.0.0.1:5008") + "/user/plans/success",
            "callbackUrl": getattr(_cfg_plans, "G_DUIKU_CALLBACK_URL", ""),
            "expiryPeriod": 60,
            "signature": signature
        }
        
        payment_url = None
        duitku_ref = "REF-" + sub_id[:8].upper()
        
        try:
            headers = {"Content-Type": "application/json"}
            resp = requests.post(base_api, json=payload, headers=headers)
            resp_data = resp.json()
            if resp_data.get("statusCode") == "00":
                payment_url = resp_data.get("paymentUrl")
                duitku_ref = resp_data.get("reference", duitku_ref)
            else:
                return f"<b>Duitku API Error:</b> {resp_data.get('statusMessage', str(resp_data))}<br><br><b>Hint:</b> Make sure your 'DUITKU_MERCHANT_CODE' in config.py is correct!", 400
        except Exception as e:
            return f"<b>Exception contacting Duitku:</b> {str(e)}", 500
            
        date_str = time.strftime("%Y%m%d", time.gmtime())
        today_start_str = time.strftime("%Y-%m-%d", time.gmtime())
        daily_count = _db.db_user_subscription.count_documents({"created_at": {"$regex": f"^{today_start_str}"}})
        invoice_number = f"INV-{date_str}-{daily_count + 1:03d}"
        
        doc = {
            "subscription_id": sub_id,
            "fk_user_id": fk_user_id,
            "user_email": user_email,
            "user_name": user_doc.get("name", "") if user_doc else "",
            "plan_id": plan_id,
            "plan_name": plan_doc.get("name", ""),
            "purchase_months": purchase_months,
            "subtotal_price_idr": subtotal_price_idr,
            "discount_percent": discount_pct,
            "discount_amount_idr": discount_idr,
            "plan_price_idr": plan_price_idr,
            "admin_fee_idr": admin_fee_idr,
            "price_paid_idr": amount_idr,
            "max_qr": plan_doc.get("max_qr", 0),
            "max_storage_mb": plan_doc.get("max_storage_mb", 0),
            "period_days": period_days,
            "started_at": 0,
            "expires_at": 0,
            "payment_ref": duitku_ref,
            "payment_method": payment_method,
            "payment_url": payment_url,
            "notes": "",
            "status": "PENDING",
            "invoice_number": invoice_number,
            "payment_due_timestamp": now_ts + 3600,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "timestamp": now_ts
        }
        _db.db_user_subscription.insert_one(doc)
        session["last_pending_sub"] = sub_id
        
        if payment_url:
            return redirect(payment_url)
            
        return redirect(url_for("user_plans_success"))
        
    plan_id = request.args.get("plan", "")
    plan_doc = _db.db_plan_definition.find_one({"plan_id": plan_id, "status": "ACTIVE"})
    
    if not plan_doc:
        return redirect(url_for("user_plans"))
        
    try:
        raw_pm = _load_payment_methods_json(app.root_path)
    except Exception as e:
        app.logger.error(f"Error loading payment methods JSON: {e}")
        raw_pm = []
    duration_options = _build_checkout_duration_options(plan_doc)
    payment_methods_data = _enrich_payment_categories_with_fees(raw_pm, duration_options)
    return render_template(
        "user/checkout.html",
        plan=plan_doc,
        payment_categories=payment_methods_data,
        duration_options=duration_options,
    )


@app.route("/user/plans/success")
def user_plans_success():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
        
    from pytavia_core import database as _db_plans, config as _cfg_plans
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    sub_id = session.get("last_pending_sub")
    
    subscription = None
    if sub_id:
        subscription = _db.db_user_subscription.find_one({"subscription_id": sub_id, "fk_user_id": session["fk_user_id"]})
        
    return render_template("user/payment_success.html", subscription=subscription)


@app.route("/user/plans/failed")
def user_plans_failed():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return render_template("user/payment_failed.html")


@app.route("/api/v1/payment/callback", methods=["POST"])
@csrf.exempt
def duitku_callback():
    from pytavia_core import database as _db_c, config as _cfg_c
    import hashlib
    import time
    
    merchant_code = str(request.form.get("merchantCode", ""))
    amount = str(request.form.get("amount", ""))
    order_id = str(request.form.get("merchantOrderId", ""))
    signature = str(request.form.get("signature", ""))
    result_code = str(request.form.get("resultCode", ""))
    
    cfg_merchant = getattr(_cfg_c, "G_DUITKU_MERCHANT_CODE", "")
    cfg_api_key = getattr(_cfg_c, "G_DUITKU_MERCHANT_KEY", "")
    
    sig_str = f"{cfg_merchant}{amount}{order_id}{cfg_api_key}"
    calc_sig = hashlib.md5(sig_str.encode('utf-8')).hexdigest()
    
    if signature == calc_sig:
        if result_code == "00":
            _db = _db_c.get_db_conn(_cfg_c.mainDB)
            sub = _db.db_user_subscription.find_one({"subscription_id": order_id})
            if sub and sub.get("status") == "PENDING":
                now_ts = int(time.time())
                period_days = sub.get("period_days", 30)
                expires_at = now_ts + (period_days * 86400)
                
                _db.db_user_subscription.update_one(
                    {"subscription_id": order_id},
                    {"$set": {
                        "status": "ACTIVE",
                        "started_at": now_ts,
                        "expires_at": expires_at
                    }}
                )
    
    return "SUCCESS", 200


@app.route("/user/plans")
def user_plans():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_plans, config as _cfg_plans
    import time
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    fk_user_id = session["fk_user_id"]
    now = time.time()
    # Optimize auto-cleanups via fast Mongo bulk operations
    _db.db_user_subscription.update_many(
        {"fk_user_id": fk_user_id, "status": "ACTIVE", "expires_at": {"$lt": now, "$gt": 0}},
        {"$set": {"status": "EXPIRED"}}
    )
    _db.db_user_subscription.update_many(
        {"fk_user_id": fk_user_id, "status": "PENDING", "timestamp": {"$lt": now - 3600}},
        {"$set": {"status": "FAILED"}}
    )

    # Strictly limit payload sent to the FE
    subscriptions = list(_db.db_user_subscription.find(
        {"fk_user_id": fk_user_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(5))
    plans = _get_plans_from_db(_db)
    return render_template("user/plans.html",
        active_page="plans",
        subscriptions=subscriptions,
        plans=plans,
        now=now,
    )


@app.route("/user/plans/cancel", methods=["POST"])
def user_plans_cancel():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
        
    sub_id = request.form.get("subscription_id")
    if not sub_id:
        return redirect(url_for("user_plans"))
        
    from pytavia_core import database as _db_plans, config as _cfg_plans
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    
    _db.db_user_subscription.update_one(
        {"fk_user_id": session["fk_user_id"], "subscription_id": sub_id, "status": "PENDING"},
        {"$set": {"status": "CANCELLED"}}
    )
    
    return redirect(url_for("user_plans"))


@app.route("/user/transactions")
def user_transactions():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from pytavia_core import database as _db_plans, config as _cfg_plans
    import time
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    fk_user_id = session["fk_user_id"]
    now = time.time()
    
    subscriptions = list(_db.db_user_subscription.find(
        {"fk_user_id": fk_user_id},
        {"_id": 0}
    ).sort("timestamp", -1))
    
    for s in subscriptions:
        if s.get("status") == "ACTIVE" and s.get("expires_at", 0) < now:
            _db.db_user_subscription.update_one(
                {"subscription_id": s["subscription_id"]},
                {"$set": {"status": "EXPIRED"}}
            )
            s["status"] = "EXPIRED"
        elif s.get("status") == "PENDING":
            created_ts = s.get("timestamp", 0)
            if now - created_ts > 3600:
                _db.db_user_subscription.update_one(
                    {"subscription_id": s["subscription_id"]},
                    {"$set": {"status": "FAILED"}}
                )
                s["status"] = "FAILED"
                
    return render_template("user/transactions.html",
        active_page="transactions",
        transactions=subscriptions,
        now=now
    )


@app.route("/user/transactions/invoice/<sub_id>")
def user_transactions_invoice(sub_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
        
    from pytavia_core import database as _db_plans, config as _cfg_plans
    _db = _db_plans.get_db_conn(_cfg_plans.mainDB)
    
    transaction = _db.db_user_subscription.find_one({"subscription_id": sub_id, "fk_user_id": session["fk_user_id"]})
    if not transaction:
        return "Transaction not found", 404

    user = _db.db_user.find_one({"pkey": session["fk_user_id"]})

    # Enrich transaction snapshot for invoice display consistency
    try:
        pm_categories = _load_payment_methods_json(app.root_path)
    except Exception:
        pm_categories = []
    payment_code = transaction.get("payment_method", "")
    transaction["payment_method_label"] = _payment_method_label_for_code(pm_categories, payment_code)
    transaction["payment_method_fee_label"] = _fee_string_for_payment_method(pm_categories, payment_code) or "-"

    subtotal_price_idr = int(transaction.get("subtotal_price_idr", 0) or 0)
    discount_amount_idr = int(transaction.get("discount_amount_idr", 0) or 0)
    plan_price_idr = int(transaction.get("plan_price_idr", 0) or 0)
    admin_fee_idr = int(transaction.get("admin_fee_idr", 0) or 0)
    paid_idr = int(transaction.get("price_paid_idr", 0) or 0)

    # Backward compatibility for old subscriptions before new checkout fields existed
    if subtotal_price_idr <= 0:
        subtotal_price_idr = plan_price_idr if plan_price_idr > 0 else max(0, paid_idr - admin_fee_idr)
    if plan_price_idr <= 0:
        plan_price_idr = max(0, subtotal_price_idr - discount_amount_idr)
    if admin_fee_idr <= 0:
        admin_fee_idr = max(0, paid_idr - plan_price_idr)
    if discount_amount_idr <= 0:
        discount_amount_idr = max(0, subtotal_price_idr - plan_price_idr)

    transaction["subtotal_price_idr"] = subtotal_price_idr
    transaction["plan_price_idr"] = plan_price_idr
    transaction["discount_amount_idr"] = discount_amount_idr
    transaction["admin_fee_idr"] = admin_fee_idr
    transaction["purchase_months"] = int(transaction.get("purchase_months", 1) or 1)
    transaction["discount_percent"] = int(transaction.get("discount_percent", 0) or 0)

    return render_template("user/invoice.html", transaction=transaction, user=user)


@app.route("/user/settings")
def user_settings():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    return view_user.view_user(app).settings_html()


@app.route("/user/account/delete", methods=["POST"])
def user_account_delete():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))

    from pytavia_core import database as _dba, config as _cfga
    import time as _time

    _db = _dba.get_db_conn(_cfga.mainDB)
    fk_user_id = session["fk_user_id"]
    deleted_at = _time.strftime("%Y-%m-%d %H:%M:%S UTC", _time.gmtime())
    deleted_ts = int(_time.time())

    soft = {"$set": {
        "is_deleted": True, 
        "deleted_at": deleted_at, 
        "deleted_ts": deleted_ts,
        "status": "DELETED"
    }}

    # Soft-delete the user record
    _db.db_user.update_one({"pkey": fk_user_id}, soft)
    _db.db_user_auth.update_one({"fk_user_id": fk_user_id}, soft)

    # Soft-delete all QR cards and their detail tables
    qr_cols = [
        "db_qrcard", "db_qrcard_web", "db_qrcard_ecard", "db_qrcard_images",
        "db_qrcard_video", "db_qrcard_pdf", "db_qrcard_special", "db_qrcard_allinone",
        "db_qrcard_web_static", "db_qrcard_text", "db_qrcard_wa_static",
        "db_qrcard_email_static", "db_qrcard_vcard_static", "db_qr_index",
        "db_qr_frame", "db_user_activity_log"
    ]
    for col in qr_cols:
        try:
            getattr(_db, col).update_many({"fk_user_id": fk_user_id}, soft)
        except Exception:
            pass

    # Soft-delete assets specifically to "SOFT_DELETED" for admin R2 cleanup
    soft_assets = soft.copy()
    soft_assets["$set"] = soft["$set"].copy()
    soft_assets["$set"]["status"] = "SOFT_DELETED"
    soft_assets["$set"]["soft_deleted_at"] = deleted_ts
    _db.db_qr_assets.update_many({"fk_user_id": fk_user_id, "status": "ACTIVE"}, soft_assets)

    # Soft-delete subscriptions
    _db.db_user_subscription.update_many({"fk_user_id": fk_user_id}, soft)

    session.clear()
    return redirect("/?account_deleted=1")

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

@app.route('/auth/v2/login/<provider>')
def social_login(provider):
    client = oauth.create_client(provider)
    if not client:
        abort(404)
    redirect_uri = url_for('social_authorize', provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)

@app.route('/auth/v2/callback/<provider>')
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


##########################################################
# HELP CENTER — USER SIDE
##########################################################

def _get_db_tickets():
    from pytavia_core import database as _dbt, config as _cfgt
    return _dbt.get_db_conn(_cfgt.mainDB)

def _new_ticket_id():
    import random, string
    return "TKT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

@app.route("/user/help-center")
def user_help_center():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session["fk_user_id"]
    _db = _get_db_tickets()
    tickets = list(_db.db_support_tickets.find(
        {"fk_user_id": fk_user_id},
        {"_id": 0}
    ).sort("created_at", -1))
    msg = request.args.get("msg")
    error_msg = request.args.get("error_msg")
    return render_template(
        "user/help_center.html",
        active_page="help_center",
        tickets=tickets,
        msg=msg,
        error_msg=error_msg,
        hide_top_nav=True,
    )

@app.route("/user/help-center/submit", methods=["POST"])
def user_help_center_submit():
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from datetime import datetime as _dt
    fk_user_id = session["fk_user_id"]
    subject  = (request.form.get("subject") or "").strip()
    category = (request.form.get("category") or "other").strip()
    message  = (request.form.get("message") or "").strip()
    if not subject or not message:
        return redirect(url_for("user_help_center", error_msg="Subject and message are required."))
    now = _dt.utcnow()
    ticket = {
        "ticket_id":   _new_ticket_id(),
        "fk_user_id":  fk_user_id,
        "username":    session.get("username", ""),
        "subject":     subject,
        "category":    category,
        "status":      "open",
        "created_at":  now,
        "updated_at":  now,
        "messages": [{
            "sender_type": "user",
            "sender_name": session.get("username", "User"),
            "message":     message,
            "sent_at":     now,
            "read_by_user":  True,
            "read_by_admin": False,
        }],
        "unread_user":  0,
        "unread_admin": 1,
    }
    _db = _get_db_tickets()
    _db.db_support_tickets.insert_one(ticket)
    return redirect(url_for("user_help_center", msg="Ticket submitted successfully."))

@app.route("/user/help-center/<ticket_id>")
def user_help_ticket(ticket_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    fk_user_id = session["fk_user_id"]
    _db = _get_db_tickets()
    ticket = _db.db_support_tickets.find_one(
        {"ticket_id": ticket_id, "fk_user_id": fk_user_id}, {"_id": 0}
    )
    if not ticket:
        abort(404)
    # Mark admin messages as read by user
    _db.db_support_tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$set": {
                "unread_user": 0,
                "messages.$[m].read_by_user": True,
            }
        },
        array_filters=[{"m.sender_type": "admin"}],
    )
    # Reload after mark-read
    ticket = _db.db_support_tickets.find_one(
        {"ticket_id": ticket_id, "fk_user_id": fk_user_id}, {"_id": 0}
    )
    return render_template(
        "user/help_ticket.html",
        active_page="help_center",
        ticket=ticket,
        hide_top_nav=True,
    )

@app.route("/user/help-center/<ticket_id>/reply", methods=["POST"])
def user_help_ticket_reply(ticket_id):
    if "fk_user_id" not in session:
        return redirect(url_for("login_view"))
    from datetime import datetime as _dt
    fk_user_id = session["fk_user_id"]
    _db = _get_db_tickets()
    ticket = _db.db_support_tickets.find_one(
        {"ticket_id": ticket_id, "fk_user_id": fk_user_id}, {"_id": 0}
    )
    if not ticket:
        abort(404)
    if ticket.get("status") in ("closed", "fixed"):
        return redirect(url_for("user_help_ticket", ticket_id=ticket_id))
    msg_text = (request.form.get("message") or "").strip()
    if not msg_text:
        return redirect(url_for("user_help_ticket", ticket_id=ticket_id))
    now = _dt.utcnow()
    new_msg = {
        "sender_type": "user",
        "sender_name": session.get("username", "User"),
        "message":     msg_text,
        "sent_at":     now,
        "read_by_user":  True,
        "read_by_admin": False,
    }
    _db.db_support_tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$push": {"messages": new_msg},
            "$inc":  {"unread_admin": 1},
            "$set":  {"updated_at": now},
        }
    )
    return redirect(url_for("user_help_ticket", ticket_id=ticket_id))


##########################################################
# HELP CENTER — ADMIN SIDE
##########################################################

@app.route("/admin/tickets")
def admin_tickets():
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    _db = _get_db_tickets()
    status_filter = request.args.get("status", "")
    query = {}
    if status_filter:
        query["status"] = status_filter
    tickets = list(_db.db_support_tickets.find(query, {"_id": 0}).sort("updated_at", -1))
    total_unread = _db.db_support_tickets.count_documents({"unread_admin": {"$gt": 0}})
    from pytavia_modules.view import view_admin as _va
    admin_name  = session.get("admin_name", "")
    admin_email = session.get("admin_email", "")
    admin_role  = session.get("admin_role", "")
    return render_template(
        "admin/tickets.html",
        tickets=tickets,
        status_filter=status_filter,
        total_unread=total_unread,
        admin_name=admin_name,
        admin_email=admin_email,
        admin_role=admin_role,
        msg=request.args.get("msg"),
        error_msg=request.args.get("error_msg"),
    )

@app.route("/admin/tickets/<ticket_id>")
def admin_ticket_detail(ticket_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    _db = _get_db_tickets()
    ticket = _db.db_support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        abort(404)
    # Mark user messages as read by admin
    _db.db_support_tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$set": {
                "unread_admin": 0,
                "messages.$[m].read_by_admin": True,
            }
        },
        array_filters=[{"m.sender_type": "user"}],
    )
    ticket = _db.db_support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    admin_name  = session.get("admin_name", "")
    admin_email = session.get("admin_email", "")
    admin_role  = session.get("admin_role", "")
    return render_template(
        "admin/ticket_detail.html",
        ticket=ticket,
        admin_name=admin_name,
        admin_email=admin_email,
        admin_role=admin_role,
    )

@app.route("/admin/tickets/<ticket_id>/reply", methods=["POST"])
def admin_ticket_reply(ticket_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from datetime import datetime as _dt
    _db = _get_db_tickets()
    ticket = _db.db_support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        abort(404)
    msg_text = (request.form.get("message") or "").strip()
    if not msg_text:
        return redirect(url_for("admin_ticket_detail", ticket_id=ticket_id))
    now = _dt.utcnow()
    new_msg = {
        "sender_type": "admin",
        "sender_name": session.get("admin_name") or session.get("admin_email") or "Admin",
        "message":     msg_text,
        "sent_at":     now,
        "read_by_user":  False,
        "read_by_admin": True,
    }
    _db.db_support_tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$push": {"messages": new_msg},
            "$inc":  {"unread_user": 1},
            "$set":  {"updated_at": now, "status": "in_progress" if ticket.get("status") == "open" else ticket.get("status")},
        }
    )
    return redirect(url_for("admin_ticket_detail", ticket_id=ticket_id))

@app.route("/admin/tickets/<ticket_id>/status", methods=["POST"])
def admin_ticket_status(ticket_id):
    if "fk_admin_id" not in session:
        return redirect(url_for("admin_login_view"))
    from datetime import datetime as _dt
    _db = _get_db_tickets()
    new_status = (request.form.get("status") or "").strip()
    if new_status not in ("open", "in_progress", "closed", "fixed"):
        return redirect(url_for("admin_ticket_detail", ticket_id=ticket_id))
    _db.db_support_tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {"status": new_status, "updated_at": _dt.utcnow()}}
    )
    return redirect(url_for("admin_tickets", msg=f"Ticket {ticket_id} status updated to {new_status}."))
