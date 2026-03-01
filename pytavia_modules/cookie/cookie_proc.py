import sys
import traceback
import datetime
import time
import ast # use to convert string to dictionary 
from   datetime import datetime

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
from flask.sessions          import SessionInterface, SessionMixin
class cookie_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def    
    
    def set_cookie(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_COOKIE_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            session = params["session"]
            expires = params["expires"]
            
            self.webapp.logger.debug("------ cookies proc session")
            self.webapp.logger.debug(session["fk_user_id"])
            
            """
            cookie_id     = request.cookies.get(app.session_cookie_name)
            username      = None
            x_forward_for = None
            user_agent    = None 
            x_referer     = None
            time_login    = None
            expire_time   = None
            #end """
            
            
        except:
            print (traceback.format_exc())
            response["message_action"] = "ADD_COOKIE_FAILED"
            response["message_action"] = "ADD_COOKIE_FAILED: " + str(sys.exc_info())
        # end try
        return response

    