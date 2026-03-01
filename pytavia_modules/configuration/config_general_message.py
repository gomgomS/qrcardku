import json
import time
import pymongo
import sys
import urllib.parse
import base64
import traceback
import random

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

sys.path.append("pytavia_modules/configuration" )

from pytavia_core    import config
from pytavia_core    import database
from pytavia_core    import helper

from pytavia_stdlib  import utils
from pytavia_stdlib  import idgen


#from cerberus        import Validator


class config_general_message :
    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        #base_core.base_core.__init__(self, app)
        self.webapp = app
    # end def

    # check the errormsg value from db, if not exist, insert new
    def process(self, data):
        response = { "status" : "SUCCESS", "data" : {} }
        try:            
            schema = { "value"  : { "required" : True, "type" : "string", "empty" : False } }
            schema = { "type"   : { "required" : True, "type" : "string", "empty" : False, "dependencies" : { "type"      : ["SUCCESS", "FAIL"] } } }
            
            #validation_resp = helper.validation( schema, params=data )
            #if not validation_resp["is_data_ok"]:
            #    response["status"] = "FAIL"
            #    response["data"  ] = validation_resp["errors"]
            #    self.webapp.logger.debug( response )
            #    return response
            # end if

            value    = data["value" ]
            msg_type = data["type"  ]
            err_msg_rec = self.mgdDB.db_config_messages.find_one(
                { "value" : value }, 
                { "_id" : 0, "name" : 1, "value" : 1, "type" : 1, "display" : 1 }
            )
            if err_msg_rec == None :
                mdl_item = database.get_record("db_config_messages")
                mdl_item["name"       ]  = value          
                mdl_item["value"      ]  = value
                mdl_item["type"       ]  = msg_type
                mdl_item["platform"   ]  = config.G_PORTAL_TYPE
                mdl_item["display"]["en"]["title"] = value
                mdl_item["display"]["en"]["msg"  ] = value
                self.mgdDB.db_config_messages.insert( mdl_item )

                err_msg_rec = self.mgdDB.db_config_messages.find_one(
                    { "value" : value }, 
                    { "_id" : 0, "name" : 1, "value" : 1, "type" : 1, "display" : 1 }
                )                
            
            response["data"] = err_msg_rec
            return response
        
        except :
            error_data = self.webapp.logger.debug( traceback.format_exc() )
            response = { "status" : "FAIL", "data" : error_data }
            return response
            
        # end try
        
    # end def

    def update(self, params) :
        call_id  = idgen._get_api_call_id()        
        response = {
            "message_id"     : call_id,
            "message_action" : "PROC_CONFIG_ERROR_MESSAGE",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }

        try:            
            schema = { "value"  : { "required" : True, "type" : "string", "empty" : False } }
            schema = { "type"   : { "required" : True, "type" : "string", "empty" : False, "dependencies" : { "type"      : ["SUCCESS", "FAIL"] } } }
            
            #validation_resp = helper.validation( schema, params=data )
            #if not validation_resp["is_data_ok"]:
            #    response["status"] = "FAIL"
            #    response["data"  ] = validation_resp["errors"]
            #    self.webapp.logger.debug( response )
            #    return response
            # end if

            value    = data["value" ]
            msg_type = data["type"  ]
            err_msg_rec = self.mgdDB.db_config_messages.find_one(
                { "value" : value }, 
                { "_id" : 0, "name" : 1, "value" : 1, "type" : 1, "display" : 1 }
            )
            if err_msg_rec == None :
                mdl_item = database.get_record("db_config_messages")
                mdl_item["name"       ]  = value          
                mdl_item["value"      ]  = value
                mdl_item["type"       ]  = msg_type
                mdl_item["platform"   ]  = config.G_PORTAL_TYPE
                mdl_item["display"]["en"]["title"] = value
                mdl_item["display"]["en"]["msg"  ] = value
                self.mgdDB.db_config_messages.insert( mdl_item )

                err_msg_rec = self.mgdDB.db_config_messages.find_one(
                    { "value" : value }, 
                    { "_id" : 0, "name" : 1, "value" : 1, "type" : 1, "display" : 1 }
                )                
            
            response["data"] = err_msg_rec
            return response
        
        except :
            error_data = self.webapp.logger.debug( traceback.format_exc() )
            response = { "status" : "FAIL", "data" : error_data }
            return response
            
        # end try
        
    # end def



# end class

