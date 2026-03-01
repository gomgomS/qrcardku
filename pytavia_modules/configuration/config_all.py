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

class config_all(config_core.config_core):

    mgdDB = database.get_db_conn(config.mainDB)

    def __ini__(self):
        config_core.config_core.__init__(self)
    # end def

    def add(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_CONFIG_ALL_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            name           = params["name"        ]
            value          = params["value"       ]
            add_url        = params["add_url"     ]
            edit_url       = params["edit_url"    ]
            desc           = params["desc"        ]
            misc           = params["misc"        ]
            config_type    = params["type"        ]
            bo_access      = params["bo_access"   ]
            bo_access_2    = params["bo_access_2" ]
            config_all_rec = database.get_record("db_config_all")
            config_all_rec["name"       ] = name
            config_all_rec["value"      ] = value
            config_all_rec["add_url"    ] = add_url
            config_all_rec["edit_url"   ] = edit_url
            config_all_rec["desc"       ] = desc
            config_all_rec["misc"       ] = misc
            config_all_rec["type"       ] = config_type
            config_all_rec["bo_access"  ] = bo_access
            config_all_rec["bo_access_2"] = bo_access_2
            config_all_check = self.mgdDB.db_config_all.find_one({
                "value" : value
            })
            if config_all_check == None:
                self.mgdDB.db_config_all.insert( config_all_rec )
            else:
                response["message_action"] = "ADD_CONFIG_ALL_FAILED"
                response["message_code"  ] = "1"
                response["message_desc"  ] = "value already exists"
            # end if
        except :
            print (traceback.format_exc())
            response["message_action"] = "ADD_CONFIG_ALL_FAILED"
            response["message_action"] = "ADD_CONFIG_ALL_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def edit(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "EDIT_CONFIG_ALL_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "" ,
            "message_data"   : {}
        }
        try:
            name           = params["name"        ]
            value          = params["value"       ]
            add_url        = params["add_url"     ]
            edit_url       = params["edit_url"    ]
            desc           = params["desc"        ]
            misc           = params["misc"        ]
            config_type    = params["type"        ]
            bo_access      = params["bo_access"   ]
            bo_access_2    = params["bo_access_2" ]
            config_all_rec = self.mgdDB.db_config_all.find_one({
                "value" : value
            })
            if config_all_rec != None:
                self.mgdDB.db_config_all.update(
                    {"value" : value},
                    {"$set"  : {
                        "desc"        : desc        ,
                        "misc"        : misc        ,
                        "add_url"     : add_url     ,
                        "edit_url"    : edit_url    ,
                        "name"        : name        ,
                        "bo_access"   : bo_access   ,
                        "bo_access_2" : bo_access_2 ,
                        "type"        : config_type
                    }}
                )
            else:
                response["message_action"] = "EDIT_CONFIG_ALL_FAILED"
                response["message_code"  ] = "1"
                response["message_desc"  ] = "value to update does not exist"
            # end if
        except :
            print (traceback.format_exc())
            response["message_action"] = "EDIT_CONFIG_ALL_FAILED"
            response["message_action"] = "EDIT_CONFIG_ALL_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def delete(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "DELETE_CONFIG_ALL_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            name         = params["name" ]
            value        = params["value"]
            config_type  = params["type" ]
            self.mgdDB.db_config_all.remove({ "value" : value })
        except:
            print (traceback.format_exc())
            response["message_action"] = "DELETE_CONFIG_ALL_FAILED"
            response["message_action"] = "DELETE_CONFIG_ALL_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

# end class
