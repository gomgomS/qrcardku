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

class landing_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def submit_request(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "SUBMIT_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            name         = params.get("name")
            email        = params.get("email")
            phone        = params.get("phone", "")
            service_type = params.get("service_type")
            message      = params.get("message")

            if not name or not email or not service_type or not message:
                response["message_action"] = "SUBMIT_FAILED"
                response["message_desc"]   = "All required fields must be filled"
                return response

            request_rec = database.get_record("db_security_house_request")
            request_rec["request_id"]   = idgen._get_api_call_id()
            request_rec["name"]         = name
            request_rec["email"]        = email
            request_rec["phone"]        = phone
            request_rec["service_type"] = service_type
            request_rec["message"]      = message
            request_rec["status"]       = "PENDING"
            request_rec["created_at"]   = time.strftime("%Y-%m-%d %H:%M:%S")
            request_rec["timestamp"]    = int(time.time())

            self.mgdDB.db_security_house_request.insert_one(request_rec)

        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "SUBMIT_FAILED"
            response["message_desc"]   = str(e)

        return response
