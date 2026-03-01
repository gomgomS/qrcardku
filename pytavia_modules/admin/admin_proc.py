import sys
import traceback
import time

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib   import idgen
from pytavia_stdlib   import utils
from pytavia_core     import database
from pytavia_core     import config

class admin_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def get_all_requests(self):
        try:
            requests = list(self.mgdDB.db_security_house_request.find({}).sort("timestamp", -1))
            return requests
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def update_request_status(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "UPDATE_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            request_id = params.get("request_id")
            new_status = params.get("status")

            if not request_id or not new_status:
                response["message_action"] = "UPDATE_FAILED"
                response["message_desc"]   = "request_id and status are required"
                return response

            self.mgdDB.db_security_house_request.update_one(
                {"request_id": request_id},
                {"$set": {"status": new_status}}
            )

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "UPDATE_FAILED"
            response["message_desc"]   = str(e)

        return response

    def delete_request(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "DELETE_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            request_id = params.get("request_id")

            if not request_id:
                response["message_action"] = "DELETE_FAILED"
                response["message_desc"]   = "request_id is required"
                return response

            self.mgdDB.db_security_house_request.delete_one({"request_id": request_id})

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "DELETE_FAILED"
            response["message_desc"]   = str(e)

        return response

    def get_all_users(self):
        try:
            users = list(self.mgdDB.db_user.find({}))
            return users
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def add_user(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_USER_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            username = params.get("username")
            password = params.get("password")
            name     = params.get("name", "")
            email    = params.get("email", "")

            if not username or not password:
                response["message_action"] = "ADD_USER_FAILED"
                response["message_desc"]   = "Username and password are required"
                return response

            # Check if user exists
            existing_user = self.mgdDB.db_user.find_one({ "username": username })
            if existing_user:
                response["message_action"] = "ADD_USER_FAILED"
                response["message_desc"]   = "Username already exists"
                return response

            # Insert db_user
            user_rec = database.get_record("db_user")
            user_rec["username"] = username
            user_rec["name"]     = name
            user_rec["email"]    = email
            self.mgdDB.db_user.insert_one(user_rec)

            # Insert db_user_auth with hashed password
            hashed_password = utils._get_passwd_hash({
                "id" : username, "password" : password
            })
            
            user_auth_rec = database.get_record("db_user_auth")
            user_auth_rec["fk_user_id"] = user_rec["pkey"]
            user_auth_rec["username"]   = username
            user_auth_rec["password"]   = hashed_password
            self.mgdDB.db_user_auth.insert_one(user_auth_rec)

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "ADD_USER_FAILED"
            response["message_desc"]   = str(e)

        return response
