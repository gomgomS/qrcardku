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
from flask import request
from flask import session

class security_login:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def
    
    def add_cookie(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_COOKIES_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            cookie_id = session.sid
            #expiration = session.expiration
            fk_user_id = session["fk_user_id" ]
            username   = session["username"   ]
            xff        = request.remote_addr
            referrer   = request.referrer
            user_agent = {
                "browser"  : request.user_agent.browser , 
                "platform" : request.user_agent.platform , 
                "string"   : request.user_agent.string
            }
            
            cookie_chk =  self.mgdDB.db_cookies.find_one({
                "fk_user_id" :  fk_user_id ,
                "active"     : "TRUE"
            })
            
            self.webapp.logger.debug("-------- cookie_chk")
            self.webapp.logger.debug(cookie_chk)
            self.webapp.logger.debug(username)
            
            if cookie_chk == None and username != None : 
                cookies_rec  = database.get_record("db_cookies")
                cookies_rec["x_forward_for" ] = xff
                cookies_rec["referrer"      ] = referrer
                cookies_rec["user_agent"    ] = user_agent
                cookies_rec["fk_user_id"    ] = fk_user_id
                cookies_rec["username"      ] = username
                cookies_rec["cookie_id"     ] = cookie_id
                cookies_rec["active"        ] = "TRUE"            
                cookies_rec["expire_time"   ] = ""           
                self.mgdDB.db_cookies.insert( cookies_rec)                
            #end if 
        except:
            self.webapp.logger.debug (traceback.format_exc())
            response["message_action"] = "ADD_COOKIES_FAILED"
            response["message_action"] = "ADD_COOKIES_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def
# end class
