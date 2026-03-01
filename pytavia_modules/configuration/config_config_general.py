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

class config_config_general(config_core.config_core):

    mgdDB = database.get_db_conn(config.mainDB)

    def __ini__(self):
        config_core.config_core.__init__(self)
    # end def

    def update(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "ADD_CONFIG_GENERAL_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            name   = params["name"  ]
            value  = params["value" ]
            order  = params["order" ]
            status = params["status"]
            misc   = params["misc"  ]
            desc   = params["desc"  ]

            order = int(order)
            config_general_rec = database.get_record("db_config_general")
            config_general_rec["name"  ] = name
            config_general_rec["value" ] = value
            config_general_rec["order" ] = order
            config_general_rec["status"] = status
            config_general_rec["misc"  ] = misc
            config_general_rec["desc"  ] = desc
            config_general_check = self.mgdDB.db_config_general.find_one({
                "value" : value
            })
            if config_general_check == None:
                self.mgdDB.db_config_general.insert( config_general_rec )
            else:
                self.mgdDB.db_config_general.update(
                    {"value" : value},
                    {"$set"  : {
                        "name"    : name   ,
                        "value"   : value  ,
                        "order"   : order  ,
                        "status"  : status ,
                        "misc"    : misc   ,
                        "desc"    : desc   ,
                    }}
                )
            # end if
            item_count = self.mgdDB.db_config_general.find({}).count()
            self.mgdDB.db_config_all.update(
                {"value" : "GENERAL_CONFIGURATION"},
                {"$set"  : {"count" : item_count }}
            )
        except :
            print (traceback.format_exc())
            response["message_action"] = "ADD_CONFIG_GENERAL_FAILED"
            response["message_action"] = "ADD_CONFIG_GENERAL_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def

    def remove(self, params):
        call_id  = idgen._get_api_call_id()
        response = {
            "message_id"     : call_id,
            "message_action" : "REMOVE_CONFIG_DONGLE_FUNCTION_SUCCESS",
            "message_code"   : "0",
            "message_title"  : "",
            "message_desc"   : "",
            "message_data"   : {}
        }
        try:
            value = params["value"]
            self.mgdDB.db_config_general.remove({ "value" : value })
            item_count = self.mgdDB.db_config_general.find({}).count()
            self.mgdDB.db_config_all.update(
                {"value" : "GENERAL_CONFIGURATION"},
                {"$set"  : {"count" : item_count }}
            )
        except:
            print (traceback.format_exc())
            response["message_action"] = "REMOVE_CONFIG_GENERAL_FAILED"
            response["message_action"] = "REMOVE_CONFIG_GENERAL_FAILED: " + str(sys.exc_info())
        # end try
        return response
    # end def
# end class

