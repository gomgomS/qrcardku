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

import sys
import os

# Ensure brevo is importable
sys.path.append(os.path.join(os.path.dirname(__file__), "brevo"))
try:
    from brevo_email_proc import brevo_email_proc
except Exception as e:
    pass

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
            confirm_password = params.get("confirm_password")
            name     = params.get("name", "")
            email    = params.get("email", "")

            if not email and username and "@" in username:
                email = username

            if not username or not password:
                response["message_action"] = "REGISTER_FAILED"
                response["message_desc"]   = "Username and password are required"
                return response
                
            if password != confirm_password:
                response["message_action"] = "REGISTER_FAILED"
                response["message_desc"]   = "Passwords do not match"
                return response

            # Check if user exists
            existing_user = self.mgdDB.db_user.find_one({ "username": username })
            if existing_user:
                response["message_action"] = "REGISTER_FAILED"
                response["message_desc"]   = "Username already exists"
                return response

            # Insert db_user
            user_rec = database.get_record("db_user")
            user_rec["fk_user_id"] = user_rec["pkey"]   # mirror pkey into fk_user_id
            user_rec["username"] = username
            user_rec["name"]     = name
            user_rec["email"]    = email
            user_rec["status"]   = "UNVERIFIED"
            
            # Generate email verification token
            verification_token   = idgen._get_api_call_id()
            user_rec["verification_token"] = verification_token
            
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

            # Note: Email verification is sent upon user login, not immediately upon registration.

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "REGISTER_FAILED"
            response["message_desc"]   = str(e)

        return response

    def verify_otp(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "VERIFY_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            fk_user_id = params.get("fk_user_id")
            otp        = params.get("otp")
            
            if not fk_user_id or not otp:
                response["message_action"] = "VERIFY_FAILED"
                response["message_desc"]   = "User ID and OTP are required."
                return response
                
            user_rec = self.mgdDB.db_user.find_one({ "pkey": fk_user_id })
            if not user_rec:
                response["message_action"] = "VERIFY_FAILED"
                response["message_desc"]   = "User not found."
                return response
                
            if user_rec.get("status") != "UNVERIFIED":
                response["message_desc"] = "Account is already verified."
                return response
                
            if user_rec.get("verification_token") != otp:
                response["message_action"] = "VERIFY_FAILED"
                response["message_desc"]   = "Invalid verification code."
                return response
                
            self.mgdDB.db_user.update_one(
                { "pkey": user_rec["pkey"] },
                { "$set": { "status": "ACTIVE", "verification_token": "" } }
            )
            response["message_desc"] = "Account verified successfully. You are now logged in."
            response["message_data"] = {
                "fk_user_id": user_rec["pkey"],
                "username"  : user_rec["username"]
            }

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "VERIFY_FAILED"
            response["message_desc"]   = str(e)
            
        return response

    def resend_otp(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "RESEND_SUCCESS",
            "message_code"   : "0",
            "message_desc"   : "Verification code resent.",
        }
        try:
            fk_user_id = params.get("fk_user_id")
            if not fk_user_id:
                response["message_action"] = "RESEND_FAILED"
                response["message_desc"]   = "User ID required."
                return response
                
            user_rec = self.mgdDB.db_user.find_one({ "pkey": fk_user_id })
            if not user_rec:
                response["message_action"] = "RESEND_FAILED"
                response["message_desc"]   = "User not found."
                return response
                
            import time
            import random
            current_time = int(time.time())
            last_sent = user_rec.get("otp_timestamp", 0)
            
            if current_time - last_sent < 60:
                response["message_action"] = "RESEND_FAILED"
                response["message_desc"]   = "Please wait 60 seconds before requesting a new code."
                return response
                
            otp = str(random.randint(100000, 999999))
            
            self.mgdDB.db_user.update_one(
                { "pkey": user_rec["pkey"] },
                { "$set": { "verification_token": otp, "otp_timestamp": current_time } }
            )
            
            try:
                brevo_proc = brevo_email_proc(self.webapp)
                brevo_proc.send_verification_email(user_rec["email"], user_rec.get("name", "User"), otp)
            except Exception as e:
                self.webapp.logger.error(f"Failed to resend Brevo OTP email: {str(e)}")
                
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "RESEND_FAILED"
            response["message_desc"]   = str(e)
            
        return response

    def forgot_password_request(self, email):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "FORGOT_PASSWORD_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "If the email is registered, a password reset link has been sent.",
            "message_data"   : {}
        }
        try:
            user_rec = self.mgdDB.db_user.find_one({ "email": email })
            if user_rec:
                reset_token = idgen._get_api_call_id()
                self.mgdDB.db_user.update_one(
                    { "pkey": user_rec["pkey"] },
                    { "$set": { "reset_password_token": reset_token } }
                )
                try:
                    brevo_proc = brevo_email_proc(self.webapp)
                    brevo_proc.send_forgot_password_email(email, user_rec.get("name", "User"), reset_token)
                except Exception as e:
                    self.webapp.logger.error(f"Failed to send reset email: {str(e)}")
                    
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "FORGOT_PASSWORD_FAILED"
            response["message_desc"]   = str(e)
            
        return response

    def reset_password(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "RESET_PASSWORD_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "Password has been reset successfully.",
            "message_data"   : {}
        }
        try:
            token = params.get("token")
            new_password = params.get("password")
            
            if not token or not new_password:
                response["message_action"] = "RESET_PASSWORD_FAILED"
                response["message_desc"]   = "Token and new password are required."
                return response
                
            user_rec = self.mgdDB.db_user.find_one({ "reset_password_token": token })
            if not user_rec:
                response["message_action"] = "RESET_PASSWORD_FAILED"
                response["message_desc"]   = "Invalid or expired token."
                return response
                
            hashed_password = utils._get_passwd_hash({
                "id" : user_rec["username"], "password" : new_password
            })
            
            self.mgdDB.db_user_auth.update_one(
                { "fk_user_id": user_rec["pkey"] },
                { "$set": { "password": hashed_password } }
            )
            
            self.mgdDB.db_user.update_one(
                { "pkey": user_rec["pkey"] },
                { "$set": { "reset_password_token": "" } }
            )
            
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "RESET_PASSWORD_FAILED"
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

            if user_auth.get("is_deleted"):
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Account has been deleted"
                return response

            user_rec = self.mgdDB.db_user.find_one({ "pkey": user_auth["fk_user_id"] })
            
            if user_rec and user_rec.get("status") == "UNVERIFIED":
                import random
                import time
                otp = str(random.randint(100000, 999999))
                current_time = int(time.time())
                
                self.mgdDB.db_user.update_one(
                    { "pkey": user_rec["pkey"] },
                    { "$set": { "verification_token": otp, "otp_timestamp": current_time } }
                )
                
                try:
                    brevo_proc = brevo_email_proc(self.webapp)
                    brevo_proc.send_verification_email(user_rec["email"], user_rec.get("name", "User"), otp)
                except Exception as e:
                    self.webapp.logger.error(f"Failed to send Brevo OTP email: {str(e)}")
                    
                response["message_action"] = "LOGIN_UNVERIFIED"
                response["message_desc"]   = "Account is not verified. Please verify your OTP."
                response["message_data"] = {
                    "fk_user_id" : user_rec["pkey"],
                    "email"      : user_rec["email"]
                }
                return response
            
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
            email    = params.get("email") or params.get("username")
            password = params.get("password")

            if not email or not password:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Email and password are required"
                return response

            hashed_password = utils._get_passwd_hash({
                "id" : email, "password" : password
            })

            admin_auth = self.mgdDB.db_admin_auth.find_one({
                "email"    : email,
                "password" : hashed_password,
            })

            if not admin_auth:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Invalid email or password"
                return response

            if admin_auth.get("inactive_status") == "TRUE":
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Account is inactive"
                return response

            admin_rec = self.mgdDB.db_admin.find_one({"admin_id": admin_auth["fk_admin_id"]})
            if not admin_rec:
                response["message_action"] = "LOGIN_FAILED"
                response["message_desc"]   = "Admin account not found"
                return response

            response["message_data"] = {
                "fk_admin_id" : admin_rec["admin_id"],
                "email"       : admin_rec["email"],
                "name"        : admin_rec.get("name", ""),
                "role"        : admin_rec.get("role", "admin"),
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

