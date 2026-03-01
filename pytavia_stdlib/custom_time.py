import datetime
import time
import random
import hashlib
import os
import sys
import base64
import requests 
import json
import re
import pytz

from datetime import datetime, timedelta
from dateutil.parser import parse as duparse

sys.path.append("pytavia_modules/security" )

from security       import security_proc
from pytavia_core   import config
from pytavia_core   import database
from flask          import Flask
from flask          import redirect
from flask          import make_response
from math           import log, floor
from xml.sax        import saxutils as su

app            = Flask( __name__, config.G_STATIC_URL_PATH )
app.secret_key = config.G_FLASK_SECRET

mgdDB = database.get_db_conn( config.mainDB )


# convert datetime string to epoch using timestamp
# example : time_str = "2000-01-01, 05:00", str_offset = "+0700"
# this means time_str is based on GMT+7, datetime object will have +7 setting before converting to epoch
def datetime_str_to_epoch_with_timezone(datetime_str, str_offset):
    full_datetime_str = datetime_str+str_offset
    datetime_obj = duparse(full_datetime_str)
    return datetime_obj.timestamp()
# end if

