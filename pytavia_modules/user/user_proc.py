import config_core
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

class user_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def

    def validate_username(self, params) :
        username = params["add_username"]

        check_username = self.mgdDB.db_user.find_one({ "username" : username, "type" : "BO" })
        if check_username != None :
            return False
        else :
            return True


    # end def

    def update(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_USER_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            username    = params["add_username"  ]
            name        = params["add_fullname"  ]
            password    = params["add_password"  ]
            role        = params["add_role"      ]
            
            check_username = self.validate_username( params )
            if check_username == False :
                error_msg_rec = self.mgdDB.db_config_general.find_one({                            
                            "value" : "ERROR_USER_TYPE_001" 
                            })

                response["message_action"] = "ADD_USER_FAILED"
                response["message_title" ] = error_msg_rec["name"] if error_msg_rec != None else "Add User Error"
                response["message_desc"  ] = error_msg_rec["desc"] if error_msg_rec != None else "Username sudah terdaftar"
                return response

            user_rec = database.get_record("db_user")
            user_rec["username"         ] = username
            user_rec["name"             ] = name
            user_rec["role"             ] = role            
            user_rec["type"             ] = "BO"
            user_rec["email"            ] = user_rec["pkey"]
            user_rec["phone"            ] = user_rec["pkey"]
            self.mgdDB.db_user.insert( user_rec )
            

            hashed_password = utils._get_passwd_hash({
                "id" : username, "password" : password
            })
            user_auth_rec = database.get_record("db_user_auth")
            user_auth_rec["username"   ] = username
            user_auth_rec["password"   ] = hashed_password
            user_auth_rec["fk_user_id" ] = user_rec["pkey"]
            self.mgdDB.db_user_auth.insert( user_auth_rec )
          
        except :
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"   ] = "ADD_USER_FAILED"
            response["message_action"   ] = "ADD_USER_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def activate(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ACTIVE_USER_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }

        try:
            modif_user_id = params["pkey"  ]
            set_active    = params["active"]
            notes         = params["notes" ]

            active_status = config.G_STATUS_INACTIVE[ set_active ]

            #self.webapp.logger.debug( "active_status---------------------------------------------" )
            #self.webapp.logger.debug( active_status )
            #self.webapp.logger.debug( "---------------------------------------------" )

            self.mgdDB.db_user.update(
                { "pkey" : modif_user_id },
                { "$set"       : { 
                    "status"   : active_status["status"],
                    
                }}
            )

            self.mgdDB.db_user_auth.update(
                { "fk_user_id" : modif_user_id },
                { "$set"       : { 
                    "inactive_status" : active_status["value" ],
                    "inactive_note"   : notes
                }}
            )
        except:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "ACTIVE_USER_FAILED"
            response["message_action"] = "ACTIVE_USER_FAILED: " + str(sys.exc_info())
        # end try

        

        return response

    # end def

    def edit(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "EDIT_USER_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        #self.webapp.logger.debug( "user_proc params--------------------------------------------------" )
        #self.webapp.logger.debug( params )
        #self.webapp.logger.debug( "------------------------------------------------------------------" )
        try:
            modif_user_id = params["edit_pkey_id"   ]
            username      = params["edit_username"  ]
            name          = params["edit_fullname"  ]
            password      = params["edit_password"  ]
            role          = params["edit_role"      ]
            


            self.mgdDB.db_user.update(
                { 
                    "pkey"      : modif_user_id,
                    "username"  : username,
                },
                { "$set"       : { 
                    "role" : role, 
                    "name" : name,
                    }
                }
            )

            if password != "" :
                hashed_password = utils._get_passwd_hash({
                    "id" : username, "password" : password
                })
                self.mgdDB.db_user_auth.update(
                    { 
                        "fk_user_id" : modif_user_id,
                        "username"   : username,
                    },
                    { "$set"       : { 
                        "password" : hashed_password,
                        }
                    }
                )
            #end if update password


        except:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "EDIT_USER_FAILED"
            response["message_action"] = "EDIT_USER_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def remove(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "REMOVE_USER_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            pkey_user = params["del_pkey_id"]
            self.mgdDB.db_user.remove      ({ "pkey"       : pkey_user })
            self.mgdDB.db_user_auth.remove ({ "fk_user_id" : pkey_user })
        except:
            self.webapp.logger.debug(traceback.format_exc())
            response["message_action"] = "REMOVE_USER_FAILED"
            response["message_action"] = "REMOVE_USER_FAILED: " + str(sys.exc_info())
        # end try


        self.webapp.logger.debug( "remove user response ---------------------------------------------" )
        self.webapp.logger.debug( response )
        self.webapp.logger.debug( "---------------------------------------------" )

        return response
    # end def
# end class
