import sys

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )
sys.path.append("pytavia_modules/cookie" )

from pytavia_stdlib import idgen
from pytavia_stdlib import utils
from pytavia_stdlib import cfs_lib

from pytavia_core   import database
from pytavia_core   import config
from cookie         import cookie_engine
from uuid     import uuid4
from datetime import datetime, timedelta
from cookie   import cookie_proc

from flask import request
from flask.sessions          import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
from pymongo                 import MongoClient

class MongoSession(CallbackDict, SessionMixin):

    def __init__(self, initial=None, sid=None):
        CallbackDict.__init__(self, initial)
        self.sid = sid
        self.modified = False        
    # end def
# end class

class MongoSessionInterface(SessionInterface):

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self):
        self.store = self.mgdDB.db_sessions
    # end if

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)
        if sid:
            stored_session = self.store.find_one({'sid': sid})
            if stored_session:
                if stored_session.get('expiration') > datetime.utcnow():
                    return MongoSession(
                        initial = stored_session['data'],
                        sid     = stored_session['sid' ]
                    )                    
                # end if
            # end if
        # end if
        sid = str(uuid4())
        
        return MongoSession(sid=sid)
    # end def

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        if not session:
            response.delete_cookie(app.session_cookie_name, domain=domain)
            return
        if self.get_expiration_time(app, session):
            expiration = self.get_expiration_time(app, session)
        else:
            expiration = datetime.utcnow() + timedelta(hours=1)
        # end if
        self.store.replace_one(
            {'sid' : session.sid},
            {
                'sid'       : session.sid,
                'data'      : session,
                'expiration': expiration
            }, upsert=True
        )        
        
        # Update expiration date in db_cookie 
        if "fk_user_id" in session :
            self.mgdDB.db_cookies.update_one({
                "cookie_id"    : session.sid , 
                "fk_user_id"   : session["fk_user_id"] ,
                "active"       : "TRUE"
            }, { "$set"  : 
                    { "expire_time" : expiration }
            })
        #end if 
        
        response.set_cookie(
            app.session_cookie_name, 
            session.sid,
            expires  = self.get_expiration_time(app, session),
            httponly = True, 
            domain   = domain
        )
        
        
    # end def
# end class

