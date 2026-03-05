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
        "welcome_bg_color"           : "#2F6BFD",
        "welcome_img_url"           : "",
        "pdf_t1_header_img_url"     : "",
        "pdf_t3_circle_img_url"     : "",
        "pdf_t4_circle_img_url"     : "",
        "pdf_files"                 : [],
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
