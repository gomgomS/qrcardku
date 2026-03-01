import datetime
import time
import copy
import pymongo
import os
import sys
import model
import config
import random

from bson.objectid      import ObjectId

db_conn_completed = False

db_conn = {}
for row in config.G_DATABASE_CONNECT:
    db_conn[row["dbname"]] = row["dbstring"]
#endfor

db_active_con = {}
for row in config.G_DATABASE_CONNECT:
    db_active_con[row["dbname"]] = None
#endfor

db = model.db

def get_database(database_name):
    return db_active_con[database_name]
#enddef

def connect_db():
    for row in config.G_DATABASE_CONNECT:
        if db_active_con[row["dbname"]] == None:
            db_active_con[row["dbname"]] = pymongo.MongoClient( db_conn[row["dbname"]] )
        #endif
    #endfor
    db_conn_completed = True
#enddef

def get_db_conn(db_conn):
    # make sure we are connected to the database
    if not db_conn_completed:
        connect_db()
    #endif

    # get the specific handle we want to connect to
    handle = db_active_con[db_conn][db_conn]
    handle.db_conn.find({})
    return handle
#enddef

def _convert_datetime_to_timestamp(date_time, IN_MILLISECONDS = True):
    if IN_MILLISECONDS:
        timestamp = int(date_time.strftime("%s")) * 1000 
        ms = int(date_time.microsecond / 1000)
        timestamp += ms
        return timestamp
    else:
        # return time.mktime(date_time.timetuple())
        return int(date_time.strftime("%s")) 
        
def _get_current_datetime(days = 0, hours = 0, minutes = 0, seconds = 0):
    return datetime.datetime.utcnow() + datetime.timedelta(days = days, hours=hours, minutes = minutes, seconds = seconds )

def get_record(db_table):
    now         = _get_current_datetime(hours = config.JKTA_TZ)
    timestamp   = _convert_datetime_to_timestamp(now)
    
    record    = db[db_table]
    record["rec_timestamp"    ] = timestamp
    record["rec_timestamp_str"] = time.strftime(
        #'%Y-%m-%d %H:%M:%S', time.localtime(int(time.time()))
        '%Y-%m-%d %H:%M:%S', time.localtime( timestamp/1000 )
        
    )
    record["_id"        ] = ObjectId()
    record["pkey"       ] = str( record["_id"] )
    record["is_deleted" ] = False
    return copy.deepcopy( record )
#enddef

def new(db_handle, db_table):
    now            = _get_current_datetime(hours = config.JKTA_TZ)
    timestamp      = _convert_datetime_to_timestamp(now)

    record    = db[db_table]
    record["__db__name__"     ] = db_table
    record["rec_timestamp"    ] = timestamp
    record["rec_timestamp_str"] = time.strftime(
        #'%Y-%m-%d %H:%M:%S', time.localtime(int(time.time()))
        '%Y-%m-%d %H:%M:%S', time.localtime( timestamp/1000 )
    )

    request_rec  = db_handle.db_unique_counter.find_and_modify(
        query    = {},
        update   = { "$inc" : {"counter" : 1}}
    )
    now_time     = int(time.time() * 1000)
    random_int   = random.randint( 1000 , 9999 )
    req_id       = str(random_int) + "-" + str(int(request_rec["counter"]))


    record["_id"        ] = ObjectId()
    record["ipkey"      ] = str( record["_id"] )
    record["pkey"       ] = str( record["_id"] ) + "-" + req_id
    record["is_deleted" ] = False
    mongo_record_model      = model.mongo_model( record , record , db_handle )
    return  mongo_record_model 
#enddef

def load(db_handle, db_table):
    record                  = db[db_table]
    record["__db__name__" ] = db_table
    mongo_record_model      = model.mongo_model( {} , record , db_handle )
    return mongo_record_model
#enddef