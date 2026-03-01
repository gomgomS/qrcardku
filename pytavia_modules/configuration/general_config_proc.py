import config_core
import sys
import traceback
import requests
import json
import ast
import re

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )

from pytavia_stdlib   import idgen
from pytavia_stdlib   import utils
from pytavia_core     import database
from pytavia_core     import config
from pytavia_core     import helper

class general_config_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app
    # end def


    def _add(self, params):
        response = helper.response_msg(
            "ADD_CONFIG_SUCCESS", "ADD CONFIG SUCCESS", {} , "0000"
        )

        try:

            # CREATE VALUE
            initial_value = params["name"].upper()
            initial_value = re.sub(r"[^a-zA-Z0-9]+", '_', initial_value)

            # CHECK IF VALUE IS EXISTING IN CONFIG TYPE
            existing_value_config_rec = self.mgdDB.db_config.find_one(
                {
                    "config_type"   : params["config_type"],
                    "value"         : initial_value
                }
            )

            if existing_value_config_rec == None:
                final_value = initial_value
                
            else:
                unique_value = False
                counter = 2
                while unique_value != True:
                    final_value = initial_value + "_" + str(counter) 
                    existing_value_config_rec = self.mgdDB.db_config.find_one(
                        {
                            "config_type"   : params["config_type"],
                            "value"         : final_value
                        }
                    )
                    if existing_value_config_rec == None:
                        unique_value = True
                    else:
                        counter += 1
                    
            config_rec  = database.new(self.mgdDB, "db_config")
            config_rec.put("name",			params["name"       ])
            config_rec.put("value",         final_value         )
            config_rec.put("misc",			params["misc"       ])
            config_rec.put("desc",			params["desc"       ])
            config_rec.put("config_type",   params["config_type"])
            config_rec.insert()



        except :
            trace_back_msg = traceback.format_exc() 
            self.webapp.logger.debug(traceback.format_exc())

            response.put( "status"      , "ADD_CONFIG_FAILED" )
            response.put( "desc"        , "ADD CONFIG FAILED" )
            response.put( "status_code" , "9999" )
            response.put( "data"        , { "error_message" : trace_back_msg })
        # end try
        return response
    # end def
    
    def _update(self, params):
        response = helper.response_msg(
            "UPDATE_CONFIG_SUCCESS", "UPDATE CONFIG SUCCESS", {} , "0000"
        )
        try:

            # ADDITIONAL CONDITIONS FOR UPDATE
            config_rec = self.mgdDB.db_config.find_one({ "pkey" : params["fk_config_id"] })

            
            if config_rec["name"] != params["name"]:
                # UPDATE ALL RECORDS CONNECTED TO THE CONFIG
                if config_rec["config_type"] == "POSISI_DI_APLIKASI" :
                    
                    self.mgdDB.db_konten.update_many(
                        {"fk_posisi_value"     : config_rec["value"]},
                        { "$set" : { 
                            "posisi_name"   : params["name"] }
                            })
                    
                    self.mgdDB.db_iklan.update_many(
                        {"fk_posisi_value"     : config_rec["value"]},
                        { "$set" : { 
                            "posisi_name"   : params["name"] }
                            })
                    
                    self.mgdDB.db_program.update_many(
                        {"fk_posisi_value": config_rec["value"]},
                        {"$set": {
                            "posisi_name": params["name"]}
                        })
                    
                    self.mgdDB.db_event.update_many(
                        {"fk_posisi_value": config_rec["value"]},
                        {"$set": {
                            "posisi_name": params["name"]}
                        })

                    self.mgdDB.db_online_survey.update_many(
                        {"fk_posisi_value": config_rec["value"]},
                        {"$set": {
                            "posisi_name": params["name"]}
                        })

                    self.mgdDB.db_belanja_online.update_many(
                        {"fk_posisi_value": config_rec["value"]},
                        {"$set": {
                            "posisi_name": params["name"]}
                        })

                elif config_rec["config_type"] == "JENIS_TAMPILAN":
                    
                    self.mgdDB.db_konten.update_many(
                        {"fk_jenis_tampilan_value"     : config_rec["value"]},
                        { "$set" : { 
                            "jenis_tampilan_name"   : params["name"] }
                            })
                    
                    self.mgdDB.db_iklan.update_many(
                        {"fk_jenis_tampilan_value"     : config_rec["value"]},
                        { "$set" : { 
                            "jenis_tampilan_name"   : params["name"] }
                            })
                    
                    self.mgdDB.db_program.update_many(
                        {"fk_jenis_tampilan_value": config_rec["value"]},
                        {"$set": {
                            "jenis_tampilan_name": params["name"]}
                        })
                        
                    self.mgdDB.db_event.update_many(
                        {"fk_jenis_tampilan_value": config["value"]},
                        {"$set": {
                            "jenis_tampilan_name": params["name"]}
                        })
                    self.mgdDB.db_event.update_many(
                        {"fk_jenis_pendaftaran_value": config["value"]},
                        {"$set": {
                            "jenis_pendaftaran_name": params["name"]}
                        })

                    self.mgdDB.db_belanja_online.update_many(
                        {"fk_jenis_tampilan_value": config_rec["value"]},
                        {"$set": {
                            "jenis_tampilan_name": params["name"]}
                        })
                
                elif config_rec["config_type"] == "TIPE_PERUSAHAAN":
                    
                    self.mgdDB.db_trainingtracker_partner.update_many(
                        {"fk_tipe_perusahaan_value"    : config_rec["value"]},
                        { "$set" : { 
                            "tipe_perusahaan_name"  : params["name"] }
                            })
                    self.mgdDB.db_program.update_many(
                        { "fk_tipe_perusahaan_value"    : config_rec["value"] },
                        { "$set" : { 
                            "tipe_perusahaan_name"  : params["name"] }
                        }
                    )

                elif config_rec["config_type"] == "KATEGORI_LAPORAN":
                    
                    self.mgdDB.db_laporan_online.update_many(
                        {"fk_kategori_laporan_value"    : config_rec["value"]},
                        { "$set" : { 
                            "kategori_laporan_name"  : params["name"] }
                            })
                
                elif config_rec["config_type"] == "KATEGORI_FAQ":
                    
                    self.mgdDB.db_faq.update_many(
                        {"fk_kategori_faq_value"    : config_rec["value"]},
                        { "$set" : { 
                            "kategori_faq_name"  : params["name"] }
                            })
                
                elif config_rec["config_type"] == "CHANNEL":
                    
                    self.mgdDB.db_push_notification.update_many(
                        {"fk_channel_value"    : config_rec["value"]},
                        { "$set" : { 
                            "channel_name"  : params["name"] }
                            })

                    self.mgdDB.db_notif_event.update_many(
                        {"fk_channel_value"    : config_rec["value"]},
                        { "$set" : { 
                            "channel_name"  : params["name"] }
                            })
                
                elif config_rec["config_type"] == "EVENT":
                    
                    self.mgdDB.db_push_notification.update_many(
                        {"fk_event_value"    : config_rec["value"]},
                        { "$set" : { 
                            "event_name"  : params["name"] }
                            })



            # UPDATE THE CONFIG RECORD
            self.mgdDB.db_config.update(
                {"pkey" : params["fk_config_id"]},
                {"$set" : {
                    "name"  : params["name"     ],
                    "misc"  : params["misc"     ],
                    "desc"  : params["desc"     ]
                }
            })



        except :
            trace_back_msg = traceback.format_exc() 
            self.webapp.logger.debug(traceback.format_exc())

            response.put( "status"      , "UPDATE_CONFIG_FAILED" )
            response.put( "desc"        , "UPDATE CONFIG FAILED" )
            response.put( "status_code" , "9999" )
            response.put( "data"        , { "error_message" : trace_back_msg })

        # end try
        return response
    # end def

    def _delete(self, params):
        response = helper.response_msg(
            "DELETE_CONFIG_SUCCESS", "DELETE CONFIG SUCCESS", {} , "0000"
        )

        try:
            
            self.mgdDB.db_config.update_one(
                { "pkey" : params["fk_config_id"] },
                {"$set" : { 
                    "is_deleted" : True 
                    }
                }
            )

        except :
            trace_back_msg = traceback.format_exc() 
            self.webapp.logger.debug(traceback.format_exc())

            response.put( "status"      , "DELETE_CONFIG_FAILED" )
            response.put( "desc"        , "DELETE CONFIG FAILED" )
            response.put( "status_code" , "9999" )
            response.put( "data"        , { "error_message" : trace_back_msg })
        # end try
        return response
    # end def



    

# end class
