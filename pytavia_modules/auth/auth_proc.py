import sys
import traceback

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib   import idgen
from pytavia_stdlib   import utils
from pytavia_core     import database
from pytavia_core     import config

class auth_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def register(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "REGISTER_SUCCESS",
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
                response["message_action"] = "REGISTER_FAILED"
                response["message_desc"]   = "Username and password are required"
                return response

            # Check if user exists
            existing_user = self.mgdDB.db_user.find_one({ "username": username })
            if existing_user:
                response["message_action"] = "REGISTER_FAILED"
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
            response["message_action"] = "REGISTER_FAILED"
            response["message_desc"]   = str(e)

        return response

    def login(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "LOGIN_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            username = params.get("username")
            password = params.get("password")

            if not username or not password:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Username and password are required"
                return response

            hashed_password = utils._get_passwd_hash({
                "id" : username, "password" : password
            })

            user_auth = self.mgdDB.db_user_auth.find_one({
                "username": username,
                "password": hashed_password
            })

            if not user_auth:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Invalid username or password"
                return response
            
            if user_auth.get("inactive_status") == "TRUE":
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Account is inactive"
                return response

            user_rec = self.mgdDB.db_user.find_one({ "pkey": user_auth["fk_user_id"] })
            
            if user_rec:
                response["message_data"] = {
                    "fk_user_id" : user_rec["pkey"],
                    "username"   : user_rec["username"],
                    "role"       : user_rec.get("role")
                }

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "LOGIN_FAILED"
            response["message_desc"]   = str(e)

        return response

    def admin_login(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "LOGIN_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            username = params.get("username")
            password = params.get("password")

            if not username or not password:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Username and password are required"
                return response

            hashed_password = utils._get_passwd_hash({
                "id" : username, "password" : password
            })

            user_auth = self.mgdDB.db_user_auth.find_one({
                "username": username,
                "password": hashed_password
            })

            if not user_auth:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Invalid admin username or password"
                return response
            
            if user_auth.get("inactive_status") == "TRUE":
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Account is inactive"
                return response

            user_rec = self.mgdDB.db_user.find_one({ "pkey": user_auth["fk_user_id"] })
            
            if user_rec:
                # Optionally enforce role="ADMIN" here if you implement RBAC structure
                # if user_rec.get("role") != "ADMIN":
                #    response["message_action"] = "LOGIN_FAILED"
                #    response["message_desc"]   = "Unauthorized administrative access"
                #    return response

                response["message_data"] = {
                    "fk_user_id" : user_rec["pkey"],
                    "username"   : user_rec["username"],
                    "role"       : user_rec.get("role", "ADMIN")
                }

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "LOGIN_FAILED"
            response["message_desc"]   = str(e)

        return response

    def social_login(self, provider, user_info):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "LOGIN_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            email    = user_info.get("email")
            # For facebook or linkedin, email might be missing if permissions aren't correct
            if not email:
                soc_id = user_info.get("id", user_info.get("sub"))
                if not soc_id:
                    response["message_action"] = "LOGIN_FAILED"
                    response["message_desc"]   = f"Could not retrieve user info from {provider}."
                    return response
                email = f"{soc_id}@{provider}.social"

            name     = user_info.get("name", user_info.get("localizedFirstName", ""))
            if not name and provider == 'linkedin':
                name = user_info.get("localizedFirstName", "") + " " + user_info.get("localizedLastName", "")

            # Check if user already exists by email
            user_rec = self.mgdDB.db_user.find_one({ "email": email })
            
            if not user_rec:
                # User doesn't exist, we must register them automatically
                username = email
                random_pass = idgen._get_api_call_id() # generate strong random password for social users
                
                new_user_rec = database.get_record("db_user")
                new_user_rec["username"] = username
                new_user_rec["name"]     = name
                new_user_rec["email"]    = email
                new_user_rec["role"]     = "USER"
                self.mgdDB.db_user.insert_one(new_user_rec)

                hashed_password = utils._get_passwd_hash({
                    "id" : username, "password" : random_pass
                })
                
                user_auth_rec = database.get_record("db_user_auth")
                user_auth_rec["fk_user_id"] = new_user_rec["pkey"]
                user_auth_rec["username"]   = username
                user_auth_rec["password"]   = hashed_password
                self.mgdDB.db_user_auth.insert_one(user_auth_rec)
                
                user_rec = new_user_rec

            # Now the user_rec exists (either old or newly created)
            # Make sure it's not inactive
            user_auth = self.mgdDB.db_user_auth.find_one({"fk_user_id": user_rec["pkey"]})
            if user_auth and user_auth.get("inactive_status") == "TRUE":
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Account is inactive"
                return response

            response["message_data"] = {
                "fk_user_id" : user_rec["pkey"],
                "username"   : user_rec["username"],
                "role"       : user_rec.get("role", "USER")
            }

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "LOGIN_FAILED"
            response["message_desc"]   = str(e)

        return response

