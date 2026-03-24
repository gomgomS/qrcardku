import sys
import traceback
import time
import datetime
import uuid

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib   import utils
from pytavia_core     import database
from pytavia_core     import config


class admin_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    VALID_ROLES = ("superadmin", "admin", "sales")

    def __init__(self, app):
        self.webapp = app

    def seed_first_admin(self):
        """Create the first superadmin if db_admin is empty. Safe to call on every startup."""
        try:
            if self.mgdDB.db_admin.count_documents({}) > 0:
                return
            email     = "admincool@qrkartu.com"
            password  = "gomgom123"
            name      = "Super Admin"
            role      = "superadmin"
            now_str   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time())
            admin_id  = str(uuid.uuid4())
            hashed    = utils._get_passwd_hash({"id": email, "password": password})
            self.mgdDB.db_admin.insert_one({
                "admin_id"       : admin_id,
                "email"          : email,
                "name"           : name,
                "role"           : role,
                "inactive_status": "FALSE",
                "created_at"     : now_str,
                "timestamp"      : timestamp,
            })
            self.mgdDB.db_admin_auth.insert_one({
                "fk_admin_id"    : admin_id,
                "email"          : email,
                "password"       : hashed,
                "inactive_status": "FALSE",
            })
        except Exception:
            pass

    def get_all_admins(self):
        try:
            return list(self.mgdDB.db_admin.find({}).sort("timestamp", -1))
        except Exception:
            return []

    def get_all_users(self):
        try:
            return list(self.mgdDB.db_user.find({}).sort("_id", -1))
        except Exception:
            return []

    def delete_user(self, params):
        response = {"message_action": "DELETE_USER_SUCCESS", "message_desc": ""}
        try:
            user_id = params.get("user_id")
            if not user_id:
                response["message_action"] = "DELETE_USER_FAILED"
                response["message_desc"]   = "user_id required"
                return response
            
            # Delete from db_user and db_user_auth
            self.mgdDB.db_user.delete_one({"pkey": user_id})
            self.mgdDB.db_user_auth.delete_one({"fk_user_id": user_id})
        except Exception as e:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "DELETE_USER_FAILED"
            response["message_desc"]   = str(e)
        return response

    def add_admin(self, params):
        response = {"message_action": "ADD_ADMIN_SUCCESS", "message_desc": "", "message_data": {}}
        try:
            email    = (params.get("email") or "").strip().lower()
            password = params.get("password", "").strip()
            name     = params.get("name", "").strip()
            role     = params.get("role", "admin").strip().lower()

            if not email or not password:
                response["message_action"] = "ADD_ADMIN_FAILED"
                response["message_desc"]   = "Email and password are required"
                return response

            if role not in self.VALID_ROLES:
                response["message_action"] = "ADD_ADMIN_FAILED"
                response["message_desc"]   = f"Invalid role. Choose: {', '.join(self.VALID_ROLES)}"
                return response

            if self.mgdDB.db_admin.find_one({"email": email}):
                response["message_action"] = "ADD_ADMIN_FAILED"
                response["message_desc"]   = "Email already exists"
                return response

            now_str   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time())
            admin_id  = str(uuid.uuid4())
            hashed    = utils._get_passwd_hash({"id": email, "password": password})

            self.mgdDB.db_admin.insert_one({
                "admin_id"       : admin_id,
                "email"          : email,
                "name"           : name,
                "role"           : role,
                "inactive_status": "FALSE",
                "created_at"     : now_str,
                "timestamp"      : timestamp,
            })
            self.mgdDB.db_admin_auth.insert_one({
                "fk_admin_id"    : admin_id,
                "email"          : email,
                "password"       : hashed,
                "inactive_status": "FALSE",
            })

        except Exception as e:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "ADD_ADMIN_FAILED"
            response["message_desc"]   = str(e)

        return response

    def toggle_admin_status(self, params):
        response = {"message_action": "TOGGLE_SUCCESS", "message_desc": ""}
        try:
            admin_id = params.get("admin_id")
            if not admin_id:
                response["message_action"] = "TOGGLE_FAILED"
                response["message_desc"]   = "admin_id required"
                return response
            rec = self.mgdDB.db_admin.find_one({"admin_id": admin_id})
            if not rec:
                response["message_action"] = "TOGGLE_FAILED"
                response["message_desc"]   = "Admin not found"
                return response
            new_status = "FALSE" if rec.get("inactive_status") == "TRUE" else "TRUE"
            self.mgdDB.db_admin.update_one(
                {"admin_id": admin_id}, {"$set": {"inactive_status": new_status}}
            )
            self.mgdDB.db_admin_auth.update_one(
                {"fk_admin_id": admin_id}, {"$set": {"inactive_status": new_status}}
            )
        except Exception as e:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "TOGGLE_FAILED"
            response["message_desc"]   = str(e)
        return response
