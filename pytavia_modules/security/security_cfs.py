import sys
import time
import traceback
import datetime
import hashlib
import requests 
import json

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib import idgen
from pytavia_stdlib import utils
from pytavia_core   import database
from pytavia_core   import config

class security_cfs:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def

    def create_init_oneway_hash(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "CREATE_ONEWAY_HAS_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            key        = params["key"       ]
            secret     = params["secret"    ]
            fk_user_id = params["fk_user_id"]
            sequence   = params["sequence"  ]

            ms_tm      = str(int(time.time() * 1000))
            str_token  = key +"%|%"+ secret +"%|%"+ fk_user_id + "%|%" + ms_tm + "%|%" + sequence
            token = hashlib.sha256(str_token.encode('ascii')).hexdigest()
            return token
        except:
            self.webapp.logger.debug (traceback.format_exc())
            response["message_action"] = "CREATE_ONEWAY_HAS_FAILED"
            response["message_action"] = "CREATE_ONEWAY_HAS_FAILED: " + str(sys.exc_info())
            return None
        # end try
    # end def
    
    def request_security_token(self, params):
        call_id = idgen._get_api_call_id()
        try:
            fk_user_id        = params["fk_user_id"  ]
            sequence          = params["sequence"  ]
            label             = params["label"     ]
            self.webapp.logger.debug(" ** sequence ")
            self.webapp.logger.debug(sequence)
            
            security_user_rec = self .mgdDB.db_security_cfs.find_one({
                "fk_user_id" : fk_user_id
            })
            
            if security_user_rec == None:
                msg_error_rec = self.mgdDB.db_config_messages.find_one({
                    "value" : "SECURITY_LOGIN_ERROR_1"
                })
                response["message_action"] = "SECURITY_LOGIN_FAILED"
                response["message_core"  ] = msg_error_rec["code"   ]
                response["message_desc"  ] = msg_error_rec["message"]
                return response                
            # end if
            
            current_time = int(time.time()  * 1000)
            expire_time  = security_user_rec["expire_time"]
            self.webapp.logger.debug("current_time: " + str( current_time ))
            self.webapp.logger.debug("expire_time : " + str( expire_time  ))
            if current_time > expire_time:
                self.webapp.logger.debug ("---------------------------------------------------")
                self.webapp.logger.debug ("The token has expired...")
                self.webapp.logger.debug ("---------------------------------------------------")
                return None
            # end if
            
            key     = config.G_CFS_KEY
            secret  = config.G_CFS_ACCESS
            timed_token  = security_user_rec["token_value"]
            str_token    = key +"%|%"+ secret +"%|%"+ fk_user_id + "%|%" + str(timed_token) + "%|%" + sequence
            token        = hashlib.sha256(str_token.encode('ascii')).hexdigest()
            self.webapp.logger.debug("----------------------------------------------")
            self.webapp.logger.debug( token )
            self.webapp.logger.debug("----------------------------------------------")
            return token
        except:
            self.webapp.logger.debug (traceback.format_exc())
            return None
        # end try
    # end def  

    def login(self,params):
        call_id = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "SECURITY_LOGIN_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        log_url     =  params["login_url" ]
        log_access  =  params["secret"    ]
        log_key     =  params["key"       ]
        try :
            login_data = {
                "key"    : log_key,
                "secret" : log_access
            }
            
            security_login_response = requests.post(log_url,data=login_data) 
            self.webapp.logger.debug("**** security_login_response ****")
            self.webapp.logger.debug(security_login_response.json())            
            security_login          = security_login_response.json()
            security_login_action   = security_login["message_action"]
            security_login_data     = security_login["message_data"  ]
            security_user_id  = security_login_data["fk_user_id" ] if "fk_user_id"  in security_login_data else ""
            security_token    = security_login_data["token"      ] if "token"       in security_login_data else ""
            security_exprired = security_login_data["expire_time"] if "expire_time" in security_login_data else ""
            security_active   = security_login_data["active"     ] if "active"      in security_login_data else ""
            if security_login_data == "SECURITY_LOGIN_FAILED":
                security_login_response["message_desc"   ] = "Add file failed in security login process"
                return security_login
            
            security_user_rec = self.mgdDB.db_security_cfs.find_one({
                "fk_user_id" : security_user_id
            })
            
            if security_user_rec == None:   
                security_user_rec = database.get_record("db_security_cfs")
                security_user_rec["token_value" ] = security_token
                security_user_rec["fk_user_id"  ] = security_user_id
                security_user_rec["expire_time" ] = security_exprired
                security_user_rec["active"      ] = "TRUE"
                self.mgdDB.db_security_cfs.insert( security_user_rec )
            else:
                security_user_rec = self.mgdDB.db_security_cfs.update(
                    { "fk_user_id"   : security_user_id },
                    { "$set"       : {
                        "token_value" : security_token,
                        "expire_time" : security_exprired,
                        "active"      : "TRUE"
                    }}
                )  
            response = security_login
        except:
            self.webapp.logger.debug (traceback.format_exc())
            response["message_action"] = "SECURITY_LOGIN_FAILED: " + str(sys.exc_info())
        # end try
        return response 
    #end def 
