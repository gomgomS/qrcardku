import config_core
import sys
import traceback

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib import idgen
from pytavia_stdlib import utils
from pytavia_core   import database
from pytavia_core   import config

class security_proc_api:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def    
    
    def get_token(self,params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "SECURITY_GET_TOKEN_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            api_core_rec = self.mgdDB.db_security_api_core.find_one({
                "api_key"    : key  ,
                "api_secret" : secret
            })
            if api_core_rec == None:
                msg_error_rec = self.mgdDB.db_config_messages.find_one({
                        "value" : "SECURITY_LOGIN_ERROR_1"
                })                  
                response["message_action"] = "SECURITY_LOGIN_FAILED"
                response["message_core"  ] = msg_error_rec["code"   ] if "code" in msg_error_rec else "" 
                response["message_desc"  ] = msg_error_rec["message"] if "message" in msg_error_rec else ""
                return response
            
            fk_user_id    = api_core_rec["pkey"]
            security_user_rec = self.mgdDB.db_security_user.find_one({
                "fk_user_id" : fk_user_id
            }) 
            
            current_time = int(time.time()  * 1000)
            expire_time = (time.time() * 1000) + (60 * 60 * 1000)
            token       = self.create_init_oneway_hash({
                "key"        : key,
                "secret"     : secret,
                "fk_user_id" : fk_user_id,
                "sequence"   : key + secret + fk_user_id
            })
            
            if security_user_rec == None:                   
                security_user_rec = database.get_record("db_security_user")
                security_user_rec["token_value" ] = token
                security_user_rec["fk_user_id"  ] = fk_user_id
                security_user_rec["expire_time" ] = expire_time
                security_user_rec["active"      ] = "TRUE"
                self.mgdDB.db_security_user.insert( security_user_rec )
            else:
                user_expire_time  = int(security_user_rec["expire_time"])
                if current_time < user_expire_time:
                    response["message_data"] = {
                        "token"      : security_user_rec["token_value"],
                        "expire_time": user_expire_time
                    }
                    return response
                # end if      
                
                security_user_rec = self.mgdDB.db_security_user.update(
                    { "fk_user_id"   : fk_user_id },
                    { "$set"       : {
                        "token_value" : token,
                        "expire_time" : expire_time,
                        "active"      : "TRUE"
                    }}
                )
            # end if
            response["message_data"] = {
                "fk_user_id"  : fk_user_id  ,
                "token"       : token       ,
                "expire_time" : expire_time ,
            }
        except:
            self.webapp.logger.debug (traceback.format_exc())
            response["message_action"] = "SECURITY_GET_TOKEN_FAILED"
            response["message_action"] = "SECURITY_GET_TOKEN_FAILED: " + str(sys.exc_info())
        # end try
        return response
