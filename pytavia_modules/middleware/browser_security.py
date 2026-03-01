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

from configuration   import config_general_message


class browser_security :
    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def

    def check_route_new(self, params):
        call_id  = idgen._get_api_call_id()        
        response = {
            "message_id"     : call_id,
            "message_action" : "CHECK_ROUTE_PERMISSION_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            fk_user_id    = params["fk_user_id"]
            route_name    = params["route_name"]
            href          = params["route_href"]

            
            # always check route and url to db first
            self.process_routes( params )
            
            superuser_rec = self.mgdDB.db_super_user.find_one({ "pkey" : fk_user_id })
            print(superuser_rec)
            print("========================superuser_rec")
            if superuser_rec != None :
                msg_rec  = config_general_message.config_general_message( self.webapp ).process({ "value" : "CHECK_ROUTE_PERMISSION_SUCCESS", "type" : "SUCCESS" })
                
                return response
            # end if

            route_priv_rec = self.mgdDB.db_config_webapp_route_privileges.find_one({ "href" : href, "status" : "ENABLE" })                      
            user_rec       = self.mgdDB.db_user.find_one({ "pkey" : fk_user_id })

            if user_rec != None : 
                # compare privilege_id (from route value) with assigned one in role to priv mapping
                check_priv_rec = self.mgdDB.db_config_webapp_role_privilege.find_one({ 
                    "fk_privilege_id" : route_priv_rec["value"],
                    "fk_role_id"      : user_rec["role"],
                    "status"          : "ENABLE"
                })

                if check_priv_rec != None : 
                    msg_rec = config_general_message.config_general_message( self.webapp ).process({ "value" : "CHECK_ROUTE_PERMISSION_SUCCESS", "type" : "SUCCESS" })
                    
                else :
                    # privilege not allowed        
                    msg_rec = config_general_message.config_general_message( self.webapp ).process({ "value" : "CHECK_ROUTE_PERMISSION_FAILED_001", "type" : "FAIL" })
                    response["message_action"   ] = msg_rec["value"] 
                    response["message_code"     ] = msg_rec["code" ]
                    response["message_desc"     ] = msg_rec["name" ]
                
                return response
            else :
                # user not exist
                
                msg_rec = config_general_message.config_general_message( self.webapp ).process({ "value" : "CHECK_USER_FAILED", "type" : "FAIL" })
                response["message_action"   ] = msg_rec["value"] 
                response["message_code"     ] = msg_rec["code" ]
                response["message_desc"     ] = msg_rec["name" ]
                return response
            # end else
            response["message_action"   ] = msg_rec["value"]
            response["message_code"     ] = msg_rec["code" ]
            response["message_desc"     ] = msg_rec["name" ]
            return response

        except :
            self.webapp.logger.debug(traceback.format_exc())
            msg_data = { "value" : "SYS_GENERAL_ERROR", "type" : "FAIL" }           
            msg_rec = config_general_message.config_general_message( self.webapp ).process( data=msg_data )

            response["message_action"   ] = "ROUTE_VIEW_FAILED"
            response["message_action"   ] = "ROUTE_VIEW_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def check_route(self, params):
        call_id  = idgen._get_api_call_id()        
        response = {
            "message_id"     : call_id,
            "message_action" : "ROUTE_VIEW_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            fk_user_id    = params["fk_user_id"]
            route_name    = params["route_name"]
            
            # superuser_rec = self.mgdDB.db_super_user.find_one({
            #     "pkey" : fk_user_id
            # })
            # if superuser_rec != None:
            #     return response
            # end if 

            # FIND USER RECORD
            user_rec = self.mgdDB.db_user.find_one({ "pkey" : str(fk_user_id), "status" : "ACTIVE" })
            if user_rec == None:
                response["message_action"   ] = "ROUTE_VIEW_FAILED" 
                response["message_code"     ] = "1001"
                response["message_desc"     ] = "USER NOT FOUND"
                return response


            # CHECK IF THE USER IS ADMIN
            # FOR THE MEANTIME ADMIN ROLES ARE WEB USERS ROLE
            superuser_rec = self.mgdDB.db_config.find_one({"config_type" : "ADMIN_ROLES", "value" : user_rec["role_position_value"] })
            if superuser_rec != None:
                return response


            user_role_rec = self.mgdDB.db_user.find_one({
                "pkey" : fk_user_id
            })
            
            if user_role_rec != None : 
                role_privilege_view = self.mgdDB.db_config_webapp_role_privilege.find({
                    "fk_role_id" : user_role_rec["role_position_value"]
                })
                for role_privilege_rec in role_privilege_view:
                    fk_privilege_id     = role_privilege_rec["fk_privilege_id"]
                    menu_privilege_view = self.mgdDB.db_config_webapp_menu_privilege.find({
                        "fk_privilege_id" : fk_privilege_id,
                        "status"          : "ENABLE"
                    })
                    for menu_privilege_rec in menu_privilege_view:
                        fk_menu_id = menu_privilege_rec["fk_menu_id"]
                        # if the menu is in the privilege list we are good
                        # and we return , if not we keep looking for it
                        webapp_handler_rec = self.mgdDB.db_config_menu_webapp_handler.find_one({
                            "value" : route_name
                        })
                        #self.webapp.logger.debug( route_name )
                        #self.webapp.logger.debug( webapp_handler_rec )
                        
                        fk_menu_id = webapp_handler_rec["fk_menu_id"] 
                        if fk_menu_id == route_name:
                            return response
                        # end if
                    # end for
                # end for
            # end if
            
            #
            # If it gets to the end of the allowable views then exit 
            # and return false
            #
            msg_config_rec = self.mgdDB.db_config_messages.find_one({
                "value" : "CHECK_ROUTE_PERMISSION_FAILED_001"
            })
            response["message_action"   ] = "ROUTE_VIEW_FAILED" 
            response["message_code"     ] = "1002"
            response["message_desc"     ] = "ROUTE_VIEW_FAILED" 
        except :
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"   ] = "ROUTE_VIEW_FAILED"
            response["message_action"   ] = "ROUTE_VIEW_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    #
    # process routes to db, check route and then insert or update
    #
    def process_routes(self, params):
        response = { "status" : "SUCCESS", "data" : {} }
        try:
            name          = params["name"         ]
            value         = params["route_name"   ]
            href          = params["route_href"   ]
            route_type    = params["route_type"   ]
            display_text  = params["display_text" ]

            # validate from href route,
            config_url_check= self.mgdDB.db_config_webapp_route_privileges.find_one({
                    "href" : href,
                })
            if config_url_check == None :
                config_rec = database.get_record("db_config_webapp_route_privileges")
                config_rec["name"         ]  = name
                config_rec["value"        ]  = value
                config_rec["href"         ]  = href
                config_rec["route_type"   ]  = route_type
                config_rec["display_text" ]  = display_text

                self.mgdDB.db_config_webapp_route_privileges.insert( config_rec )

            else :
                self.mgdDB.db_config_webapp_route_privileges.update(
                    { "href" : href },
                    { "$set"  : {
                        "value"      : value,
                        "route_type" : route_type,
                        # always update to set the default value and route_type
                        # else to be modified from CMS portal
                    }}
                )
            # end if

            item_count = self.mgdDB.db_config_webapp_route_privileges.find({}).count()
            self.mgdDB.db_config_all.update(
                {"value" : "CONFIG_ROUTE-PRIVILEGES"},
                {"$set"  : {"count" : item_count }}
            )
            return response
        
        except :
            self.webapp.debug(traceback.format_exc())
            response = { "status" : "FAILED", "data" : {} }
            return response
        # end try

    # end def

# end class
