import time
import datetime
import os
import json
import traceback


from pytavia_core import config
from pytavia_core import database
from pytavia_core import helper

from flask import Flask
from flask import redirect
from flask import make_response

app            = Flask( __name__, config.G_STATIC_URL_PATH )
app.secret_key = config.G_FLASK_SECRET

wmsDB = database.get_db_conn( config.mainDB )

class security_lib:

    def _check(self, params):
        response = helper.response_msg(
            "AUTHENTICATION_SUCCESS", "AUTHENTICATION SUCCESS", {} , "0000"
        )

        try:
            auth_key    = params["auth_key"     ]
            auth_token  = params["auth_token"   ]


            if auth_key == "USR01" and auth_token == "5f8d6cf005975990cd2f807c":
                response.put( "data"        , { "is_verified" : True })
            else:
                response.put( "status"      , "AUTHENTICATION_FAILED" )
                response.put( "desc"        , "AUTHENTICATION FAILED" )
                response.put( "status_code" , "1001" )
                response.put( "data"        , { "is_verified" : False })
        
        except:
            trace_back_msg = traceback.format_exc() 
            self.webapp.logger.debug(traceback.format_exc())

            response.put( "status"      , "AUTHENTICATION_FAILED" )
            response.put( "desc"        , "AUTHENTICATION FAILED" )
            response.put( "status_code" , "9999" )
            response.put( "data"        , { "error_message" : trace_back_msg })

        return response
