import time
import copy
import pymongo
import os
import sys

from bson.objectid import ObjectId

class mongo_model:

    def __init__(self, record, lookup, db_handle):
        self._mongo_record  = copy.deepcopy(record)
        self._lookup_record = copy.deepcopy(lookup)
        self._db_handle     = db_handle
    # end def

    def put(self, key, value):
        if not (key in self._lookup_record):
            raise ValueError('SETTING_NON_EXISTING_FIELD', key, value)
        # end if
        self._mongo_record[key] = value
    # end def

    def get(self):
        return self._mongo_record
    # end def   

    def delete(self , query):
        collection_name = self._lookup_record["__db__name__"]
        self._db_handle[collection_name].remove( query )
    # end def

    def insert(self, lock=None):
        collection_name = self._lookup_record["__db__name__"]
        del self._mongo_record["__db__name__"]
        # if 
        #if not(collection_name in self._db_handle.list_collection_names()):
        #    self._db_handle.create_collection( collection_name )
        # end if
        if lock == None:
            self._db_handle[collection_name].insert_one(  
                self._mongo_record
            )
        else:
            self._db_handle[collection_name].insert_one(  
                self._mongo_record,
                session=lock
            )
        # end if
    # end def

    def update(self, query):
        collection_name = self._lookup_record["__db__name__"]
        self._db_handle[collection_name].update_one(
            query, 
            { "$set" : self._mongo_record }
        )
    # end def
# end class
#
#
# Define the models/collections here for the mongo db
#
db = {
    
    "db_config_all" : {
        "name"                  : "",
        "add_url"               : "",
        "edit_url"              : "",
        "value"                 : "",
        "count"                 : 0 ,
        "desc"                  : "",
        "type"                  : "", # MENU PERMISSION | ETC
        # additional
        "misc"                  : "",
        "bo_access"             : "FALSE", # TRUE | FALSE  | give access to back office
        "bo_access_2"           : "FALSE"  # TRUE | FALSE  | give access to back office
    },

    "db_config_general" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "status"                : "ENABLE",
        "desc"                  : "",
        "misc"                  : "",
    },

    "db_config_menu_webapp_handler" : {
        "name"                  : "",
        "value"                 : "",
        "href"                  : "",
        "status"                : "ENABLE",
        "fk_menu_id"            : "CONFIGURATION"
    },

    "db_config_menu_webapp_item_all" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "href"                  : "",
        "status"                : "ENABLE",
        "icon"                  : "",
        "description"           : ""
    },

    "db_config_privilege" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "status"                : "ENABLE",
        "misc"                  : "",
        "desc"                  : ""
    },

    "db_config_role" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "status"                : "ENABLE",
        "user_type"             : "BO", # additional for user type
        "misc"                  : "",
        "desc"                  : ""
    },

    "db_config_webapp_menu_privilege" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "status"                : "ENABLE",
        "fk_privilege_id"       : "SELECT PRIVILEGE",
        "fk_menu_id"            : "SELECT MENU",
        "desc"                  : ""
    },

    "db_config_webapp_role_privilege" : {
        "name"                  : "",
        "value"                 : "",
        "order"                 : 0 ,
        "status"                : "ENABLE",
        "fk_privilege_id"       : "SELECT PRIVILEGE",
        "fk_role_id"            : "SELECT ROLE"
    },

    "db_config_webapp_route_privileges" : {
        "name"                  : "", # this for route action name (for logging), display as privilege text
        "value"                 : "", # this value as ROUTE_NAME, should be Unique
        "href"                  : "", # route url
        "order"                 : 0 , # use order to sort side menu list
        "route_type"            : "", # MENU | PAGE | PROCESS ( PROCESS UPDATE, PROCESS EDIT, PROCESS DELETE, etc  )
        "status"                : "ENABLE",
        "misc"                  : "",
        "desc"                  : "" ,
        # for route_type MENU only
        "display_text"          : "", # display as MENU text
        "icon"                  : "", # icon for MENU
        "bo_access"             : "TRUE", # give privilege to Back Office, default TRUE, update in CMS
    },

    "db_cookies" : {
        "fk_user_id"            : "",
        "cookie_id"             : "",
        "user_agent"            : {},
        "referrer"              : "",
        "x_forward_for"         : "",
        "username"              : "",
        "expire_time"           : "",
        "active"                : "", # TRUE | FALSE  
    },

    "db_log_login_auth" : {
        "fk_user_id"            : "" ,
        "usernmae"              : "",
        "desc"                  : "",
        "state"                 : "LOGIN_FAILED", # LOGIN_FAILED | LOGIN_SUCCESS,
    },

    "db_role_parent_to_child_mapping" : {
        "name"                  : "",
        "value"                 : "",
        "status"                : "ENABLE",
        "parent_role_val"       : "",
        "child_role_val"        : "",
        "desc"                  : "",
    },

    "db_security_api_core" : {
        "api_key"               : "",
        "api_secret"            : "",
        "active"                : "TRUE",
        "description"           : ""
    },
    
    "db_security_cfs" : {
        "token_value"           : "",
        "username"              : "",
        "password"              : "",
        "expire_time"           : "",
        "active"                : "TRUE"
    }, 
    
    "db_security_user" : {
        "token_value"           : "",
        "username"              : "",
        "password"              : "",
        "expire_time"           : "",
        "active"                : "TRUE"
    },

    "db_session" : {
        "fk_user_id"            : "",
        "login_time"            : 0 
    },

    "db_setting_app" : {
        "idle_account"          : "",
        "force_change_password" : "",
        "password_history"      : "",
        "password_length"       : "",
        "variable_password"     : { 
            "numeric"               : "FALSE",  # <TRUE> | <FALSE>
            "lower_case"            : "FALSE",  # <TRUE> | <FALSE>
            "upper_case"            : "FALSE",  # <TRUE> | <FALSE>
            "symbol"                : "FALSE",  # <TRUE> | <FALSE>
            "symbol_str"            : ""
        },
        "wrong_counter"         : "",
        "limit_history_password": 0,
        "screen_timeout"        : 0,
        "tran_timeout"          : 0,
    },

    "db_system_activity_logging" : {
        "client_type"           : "",
        "action"                : "",
        "description"           : "",
        "action_time"           : "",
        "call_id"               : "",
        "request"               : "",
        "response"              : "",
        "fk_user_id"            : "",
        "portal_type"           : "",
        "merchant_id"           : "",
        "user_role"             : "",
        "username"              : "",
        "activity_data"         : "",
    },

    "db_unique_counter" : {
        "counter"               : 0,
    },

    "db_random_config" : {
        "config_name"           : "check_gapeka_api_status",
        "check_gpk_api_status"  : "off",
    },

    "db_config"                    : {
        "_id"                   : ObjectId(),
        "name"                  : "",
        "value"                 : "",
        "desc"                  : "",
        "config_type"           : "",
        "misc"                  : "",
        "data"                  : {}
    },

    "db_menu"                   : {
        "_id"                   : ObjectId(),
        "menu_name"             : "",
        "value"                 : "",
        "icon_class"            : "",
        "url"                   : "",
        "position"              : "",
        "desc"                  : "",
        "rec_timestamp"         : ""
    },

    "db_starter"                   : {
        "_id"                   : ObjectId(),
        "menu_value"            : "",
        "name"                  : "",
        "value"                 : "",
        "icon_class"            : "",
        "url"                   : "",
        "position"              : "",
        "desc"                  : "",
        "rec_timestamp"         : ""
    },

    "db_menu_permission"        : {
        "_id"                   : ObjectId(),
        "role_position_value"   : "",
        "menu_value"            : "",
        "desc"                  : "",
        "rec_timestamp"         : ""
    },

    "db_super_user" : {
        "username"              : "",
        "password"              : "",
        "role"                  : "ADMIN",
    },

    # ── Admin panel users (completely separate from regular db_user) ──────────
    "db_admin" : {
        "admin_id"              : "",       # generated UUID (pkey alias)
        "email"                 : "",       # login email (unique)
        "name"                  : "",       # display name
        "role"                  : "admin",  # superadmin | admin | sales
        "inactive_status"       : "FALSE",  # TRUE | FALSE
        "created_at"            : "",
        "timestamp"             : 0,
    },

    "db_admin_auth" : {
        "fk_admin_id"           : "",       # → db_admin.admin_id
        "email"                 : "",       # login email (mirrors db_admin.email)
        "password"              : "",       # MD5 hash (same algo as db_user_auth)
        "inactive_status"       : "FALSE",
    },

    # Admin-managed default QR frames (visible to all users as preset options)
    "db_admin_frame" : {
        "frame_id"              : "",       # generated UUID hex (pkey alias)
        "name"                  : "",       # display name
        "image_url"             : "",       # served from /static/uploads/admin_frames/{frame_id}/
        "qr_x"                  : 0.0,     # left edge as fraction of image width  (0.0–1.0)
        "qr_y"                  : 0.0,     # top  edge as fraction of image height (0.0–1.0)
        "qr_w"                  : 0.0,     # width  as fraction of image width
        "qr_h"                  : 0.0,     # height as fraction of image height
        "status"                : "ACTIVE",# ACTIVE | DELETED
        "created_at"            : "",
        "timestamp"             : 0,
    },

    # USERS

    "db_user"                         : {
        "fk_user_id"                : "",
        "user_uuid"                 : "",
        "username"                  : "",
        "password"                  : "",
        "role"                      : "TRAINEE", # TRAINER | TRAINEE | ADMIN
        "name"                      : "",
        "phone"                     : "",
        "email"                     : "",
        #email verificatoin
        "ver_email"                 : "FALSE",
        'ver_rec'                   : [],
        # money information
        "balance"                   : 0,
        "rec_transaction"           : [],
        # apply trainer information
        "cv_user"                   : "",
        "cv_user_html"              : "",
        "cv_user_preview"           : "",
        "cv_link"                   : "",
        "status_applying"           : [],
        "summery_status_applying"   : "",
        "last_login"                : "",
        "str_last_login"            : "",       
        "login_status"              : "",      # TRUE | FALSE
        "inactive_status"           : "FALSE", # TRUE | FALSE
        "lock_status"               : "FALSE", # TRUE | FALSE
        "lock_note"                 : "",
        "image"                     : "",
        "register_trainee"          : "TRUE",   # TRUE | FALSE
        "register_trainer"          : "FALSE",  # TRUE | FALSE
    },

    "db_user_auth"                    : {
        "fk_user_id"                : "",
        "username"                  : "",
        "password"                  : "",
        "inactive_status"           : "FALSE",
        "inactive_note"             : ""
    },

    # SECURITY HOUSE landing
    "db_security_house_request": {
        "request_id"                : "",       # generated UUID
        "name"                      : "",       # sender name
        "email"                     : "",       # sender email
        "phone"                     : "",       # sender phone
        "service_type"              : "",       # requested service type
        "message"                   : "",       # message body
        "status"                    : "PENDING", # PENDING | RESOLVED
        "created_at"                : "",       # timestamp string
        "timestamp"                 : 0,        # unix timestamp
    },
    
    # STAFF / KARYAWAN management
    "db_karyawan": {
        "karyawan_id"               : "",       # generated UUID
        "photo"                     : "",       # path to uploaded photo
        "name"                      : "",
        "title"                     : "",       # replaces position
        "department"                : "",
        "phones"                    : [],       # list of dicts: {"label": "", "number": ""}
        "emails"                    : [],       # list of dicts: {"label": "", "value": ""}
        "websites"                  : [],       # list of dicts: {"label": "", "value": ""}
        "summary"                   : "",       # large text block
        "status"                    : "ACTIVE", # ACTIVE | INACTIVE
        "created_at"                : "",       # timestamp string
        "timestamp"                 : 0,        # unix timestamp
    },
    
    # USER QR CODES
    "db_qrcard": {
        "qrcard_id"                 : "",       # generated UUID
        "fk_user_id"                : "",       # link to db_user
        "qr_type"                   : "web",    # web (dynamic), web-static, vcard, pdf, etc.
        "name"                      : "",       # user specified name
        "url_content"               : "",       # destination URL (for web: redirect target; for web-static: encoded in QR)
        "short_code"                : "",       # for web (dynamic): unique slug for qrcardku.com/p/<short_code>; empty for web-static
        "design_data"               : {},       # JSON object for frame/color configurations
        
        # --- PDF Specific Fields ---
        "pdf_template"              : "default",
        "pdf_primary_color"         : "#2F6BFD",
        "pdf_secondary_color"       : "#0E379A",
        "pdf_title_font"            : "Lato",
        "pdf_title_color"           : "#000000",
        "pdf_text_font"             : "Lato",
        "pdf_text_color"            : "#000000",
        "pdf_company"               : "",
        "pdf_title"                 : "",
        "pdf_desc"                  : "",
        "pdf_website"               : "",
        "pdf_btn_text"              : "See PDF",
        "welcome_time"              : "5.0",
        "welcome_bg_color"          : "#2F6BFD",  # background color of welcome screen overlay
        "welcome_img_url"           : "",       # URL to welcome screen image shown before PDF (e.g. /static/uploads/pdf/<id>/welcome.jpg)
        "pdf_files"                 : [],
        # ---------------------------

        "frame_id"                  : "",       # custom QR frame (fk → db_qr_frame.frame_id); empty = no frame
        "qr_image_url"              : "",       # internal path to rendered QR if physically saved
        "stats"                     : {
            "scan_count": 0        # total successful page hits
        },
        "scan_limit_enabled"       : False,    # whether scan limit is enforced
        "scan_limit_value"         : 0,        # max allowed scans when enabled (0 = unlimited)
        "status"                    : "ACTIVE", # ACTIVE | INACTIVE
        "created_at"                : "",       # timestamp string
        "timestamp"                 : 0,        # unix timestamp
    },

    # Dedicated collection for web-type QR cards (dynamic redirect)
    "db_qrcard_web": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "web",    # always 'web'
        "name"                      : "",
        "url_content"               : "",       # redirect target URL
        "short_code"                : "",       # unique slug for /web/<short_code>
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for e-card-type QR cards
    "db_qrcard_ecard": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "ecard",  # always 'ecard'
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",
        # Design and typography
        "E-card_template"           : "default",
        "E-card_primary_color"      : "#2F6BFD",
        "E-card_secondary_color"    : "#0E379A",
        "E-card_title_font"         : "Lato",
        "E-card_title_color"        : "#000000",
        "E-card_text_font"          : "Lato",
        "E-card_text_color"         : "#000000",
        # About you
        "E-card_company"            : "",
        "E-card_title"              : "",
        "E-card_desc"               : "",
        "E-card_website"            : "",
        "E-card_btn_text"           : "See E-card",
        "E-card_profile_img_url"    : "",
        # Welcome screen & shared images
        "welcome_time"              : "5.0",
        "welcome_bg_color"          : "#2F6BFD",
        "welcome_img_url"           : "",
        "E-card_t1_header_img_url"  : "",
        "E-card_t3_circle_img_url"  : "",
        "E-card_t4_circle_img_url"  : "",
        # Files & contacts
        "E-card_files"              : [],
        "E-card_phones"             : [],  # [{label, number}]
        "E-card_emails"             : [],  # [{label, value}]
        "E-card_websites"           : [],  # [{label, value}]
        # Meta
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for images-type QR cards (image gallery)
    "db_qrcard_images": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "images",
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",
        # Design and typography
        "images_template"           : "1col",   # 1col | 2col | 3col
        "images_primary_color"      : "#2F6BFD",
        "images_secondary_color"    : "#0E379A",
        "images_title_font"         : "Lato",
        "images_title_color"        : "#000000",
        "images_text_font"          : "Lato",
        "images_text_color"         : "#000000",
        # Gallery info
        "images_gallery_title"      : "",
        "images_gallery_desc"       : "",
        # Gallery files - list of {url, name, desc}
        "images_gallery_files"      : [],
        # Welcome screen
        "welcome_time"              : "5.0",
        "welcome_bg_color"          : "#2F6BFD",
        "welcome_img_url"           : "",
        # Font apply
        "images_font_apply_all"     : False,
        # Meta
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for video-type QR cards (video gallery)
    "db_qrcard_video": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "video",
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",
        # Design and typography
        "video_template"            : "1col",   # 1col | 2col | 3col
        "video_primary_color"       : "#2F6BFD",
        "video_secondary_color"     : "#0E379A",
        "video_title_font"          : "Lato",
        "video_title_color"         : "#000000",
        "video_text_font"           : "Lato",
        "video_text_color"          : "#000000",
        # Gallery info
        "video_title"               : "",
        "video_desc"                : "",
        # Video links - list of {url, name, desc}
        "video_links"               : [],
        # Font apply
        "video_font_apply_all"      : False,
        # Meta
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for PDF-type QR cards (normalized view of PDF-specific fields)
    "db_qrcard_pdf": {
        "qrcard_id"                 : "",       # link back to master qrcard_id
        "fk_user_id"                : "",       # link to db_user
        "qr_type"                   : "pdf",    # always 'pdf'
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",

        # Appearance / content fields (mirror of PDF-specific section above)
        "pdf_template"              : "default",
        "pdf_primary_color"         : "#2F6BFD",
        "pdf_secondary_color"       : "#0E379A",
        "pdf_title_font"            : "Lato",
        "pdf_title_color"           : "#000000",
        "pdf_text_font"             : "Lato",
        "pdf_text_color"            : "#000000",
        "pdf_company"               : "",
        "pdf_title"                 : "",
        "pdf_desc"                  : "",
        "pdf_website"               : "",
        "pdf_btn_text"              : "See PDF",
        "welcome_time"              : "5.0",
        "welcome_bg_color"          : "#2F6BFD",
        "welcome_img_url"           : "",
        "pdf_font_apply_all"        : False,
        "pdf_t1_header_img_url"     : "",
        "pdf_t3_circle_img_url"     : "",
        "pdf_t4_circle_img_url"     : "",
        "pdf_files"                 : [],

        # Shared stats and meta
        "stats"                     : {
            "scan_count": 0
        },
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for special-type QR cards (custom HTML builder)
    "db_qrcard_special": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "special",
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",
        # Layers / content blocks stored as a JSON string (json.dumps of list).
        # Storing as string avoids MongoDB 16 MB BSON nested-document depth issues
        # with large HTML payloads and makes the field easy to audit/query as text.
        # Always serialize with json.dumps() on write and json.loads() on read.
        "special_sections"          : "",
        # Meta
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for all-in-one QR cards (multi-section page builder)
    "db_qrcard_allinone": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "allinone",
        "name"                      : "",
        "url_content"               : "",
        "short_code"                : "",
        "design_data"               : {},
        "qr_image_url"              : "",
        # Allinone design / branding
        "Allinone_template"         : "default",
        "Allinone_title"            : "",
        "Allinone_desc"             : "",
        "Allinone_cover_img_url"    : "",
        "Allinone_primary_color"    : "#2F6BFD",
        "Allinone_secondary_color"  : "#0E379A",
        "Allinone_title_font"       : "Lato",
        "Allinone_title_color"      : "#111827",
        "Allinone_text_font"        : "Lato",
        "Allinone_text_color"       : "#6b7280",
        "Allinone_font_apply_all"   : False,
        # Content sections — list of dicts: {type, v1, v2, v3, v4}
        "Allinone_sections"         : [],
        # Welcome screen
        "welcome_time"              : "5.0",
        "welcome_bg_color"          : "#2F6BFD",
        "welcome_img_url"           : "",
        # Meta
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for web-static QR cards (URL encoded directly in QR)
    "db_qrcard_web_static": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "web-static",
        "name"                      : "",
        "url_content"               : "",       # URL encoded directly into QR
        "short_code"                : "",       # always empty for static
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for text QR cards (plain text encoded directly)
    "db_qrcard_text": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "text",
        "name"                      : "",
        "text_content"              : "",       # plain text encoded into QR
        "url_content"               : "",       # always empty
        "short_code"                : "",
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for WhatsApp static QR cards
    "db_qrcard_wa_static": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "wa-static",
        "name"                      : "",
        "wa_phone"                  : "",       # phone number (digits only, no spaces)
        "wa_message"                : "",       # pre-filled message text
        "url_content"               : "",       # wa.me URL built from phone+message
        "short_code"                : "",
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for email static QR cards
    "db_qrcard_email_static": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "email-static",
        "name"                      : "",
        "email_address"             : "",       # recipient email
        "email_subject"             : "",       # pre-filled subject
        "email_body"                : "",       # pre-filled body
        "url_content"               : "",       # mailto: URL built from fields
        "short_code"                : "",
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Dedicated collection for vCard static QR cards
    "db_qrcard_vcard_static": {
        "qrcard_id"                 : "",
        "fk_user_id"                : "",
        "qr_type"                   : "vcard-static",
        "name"                      : "",
        "vcard_first_name"          : "",
        "vcard_surname"             : "",
        "vcard_company"             : "",
        "vcard_title"               : "",       # job title within company
        "vcard_phones"              : [],       # list of {type, number}
        "vcard_email"               : "",
        "vcard_website"             : "",
        "url_content"               : "",       # raw vCard 3.0 text encoded into QR
        "short_code"                : "",
        "stats"                     : {"scan_count": 0},
        "scan_limit_enabled"        : False,
        "scan_limit_value"          : 0,
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Custom QR frame templates (image background + QR placement area)
    "db_qr_frame": {
        "frame_id"                  : "",
        "fk_user_id"                : "",
        "name"                      : "",
        "image_url"                 : "",   # served from /static/uploads/frames/{frame_id}/
        "qr_x"                      : 0.0,  # left edge as fraction of image width  (0.0–1.0)
        "qr_y"                      : 0.0,  # top  edge as fraction of image height (0.0–1.0)
        "qr_w"                      : 0.0,  # width  as fraction of image width
        "qr_h"                      : 0.0,  # height as fraction of image height
        "status"                    : "ACTIVE",
        "created_at"                : "",
        "timestamp"                 : 0,
    },

    # Lightweight index of all QR cards (used for listing and routing)
    "db_qr_index": {
        "qrcard_id"                 : "",       # link to type-specific collection
        "fk_user_id"                : "",       # owner
        "qr_type"                   : "",       # 'web' | 'pdf' | 'ecard' | ...
        "name"                      : "",
        "short_code"                : "",
        "status"                    : "ACTIVE", # ACTIVE | DELETED
        "created_at"                : "",       # timestamp string
        "timestamp"                 : 0,        # unix timestamp
    }
}
