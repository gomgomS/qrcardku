import config
import time
import pymongo
import sys
import urllib.parse
import base64
import traceback
import random
import urllib.request
import io
import requests
import json
import hashlib
import uuid
from datetime import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib")
sys.path.append("pytavia_storage")
sys.path.append("pytavia_modules")

from pytavia_stdlib import idgen
from pytavia_stdlib import utils
from pytavia_core import database
from pytavia_core import config
from pytavia_stdlib import cfs_lib

class karyawan_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def get_all_karyawan(self):
        try:
            # Retrieve all distinct employees, sort by newest
            karyawan_list = list(self.mgdDB.db_karyawan.find({}).sort("timestamp", -1))
            return karyawan_list
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def add_karyawan(self, params, files):
        try:
            name       = params.get("name")
            title      = params.get("title")
            department = params.get("department")
            summary    = params.get("summary")
            
            phones     = params.get("phones", [])
            emails     = params.get("emails", [])
            websites   = params.get("websites", [])

            # Basic Validation
            if not name:
                return {
                    "message_action": "ADD_KARYAWAN_FAILED",
                    "message_desc": "Name is required.",
                    "message_data": {}
                }

            # Generate ID and Timestamps
            karyawan_id = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Handle File Upload
            photo_url = ""
            if 'photo' in files:
                file = files['photo']
                if file and file.filename:
                    # Very simple local save for now into static/uploads (make sure directory exists or create it)
                    import os
                    from werkzeug.utils import secure_filename
                    upload_folder = os.path.join(self.webapp.root_path, 'static', 'uploads')
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    filename = secure_filename(file.filename)
                    # Add timestamp to filename to avoid collisions
                    unique_filename = f"{current_time}_{filename}"
                    file_path = os.path.join(upload_folder, unique_filename)
                    file.save(file_path)
                    
                    photo_url = f"/static/uploads/{unique_filename}"

            # Prepare Record
            karyawan_rec = database.get_record("db_karyawan")
            karyawan_rec["karyawan_id"] = karyawan_id
            karyawan_rec["photo"]       = photo_url
            karyawan_rec["name"]        = name
            karyawan_rec["title"]       = title
            karyawan_rec["department"]  = department
            karyawan_rec["phones"]      = phones
            karyawan_rec["emails"]      = emails
            karyawan_rec["websites"]    = websites
            karyawan_rec["summary"]     = summary
            karyawan_rec["status"]      = "ACTIVE"
            karyawan_rec["created_at"]  = created_at
            karyawan_rec["timestamp"]   = current_time

            # Insert into database
            self.mgdDB.db_karyawan.insert_one(karyawan_rec)

            return {
                "message_action": "ADD_KARYAWAN_SUCCESS",
                "message_desc": "Employee added successfully.",
                "message_data": {"karyawan_id": karyawan_id}
            }

        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "ADD_KARYAWAN_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }

    def get_karyawan_by_id(self, karyawan_id):
        try:
            karyawan = self.mgdDB.db_karyawan.find_one({"karyawan_id": karyawan_id})
            return karyawan
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def edit_karyawan(self, karyawan_id, params, files):
        try:
            name       = params.get("name")
            title      = params.get("title")
            department = params.get("department")
            summary    = params.get("summary")
            
            phones     = params.get("phones", [])
            emails     = params.get("emails", [])
            websites   = params.get("websites", [])

            # Basic Validation
            if not name:
                return {
                    "message_action": "EDIT_KARYAWAN_FAILED",
                    "message_desc": "Name is required.",
                    "message_data": {}
                }

            update_data = {
                "name": name,
                "title": title,
                "department": department,
                "phones": phones,
                "emails": emails,
                "websites": websites,
                "summary": summary
            }

            # Handle File Upload
            if 'photo' in files:
                file = files['photo']
                if file and file.filename:
                    import os
                    from werkzeug.utils import secure_filename
                    upload_folder = os.path.join(self.webapp.root_path, 'static', 'uploads')
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    filename = secure_filename(file.filename)
                    current_time = int(time.time() * 1000)
                    unique_filename = f"{current_time}_{filename}"
                    file_path = os.path.join(upload_folder, unique_filename)
                    file.save(file_path)
                    
                    update_data["photo"] = f"/static/uploads/{unique_filename}"

            self.mgdDB.db_karyawan.update_one(
                {"karyawan_id": karyawan_id},
                {"$set": update_data}
            )

            return {
                "message_action": "EDIT_KARYAWAN_SUCCESS",
                "message_desc": "Employee updated successfully.",
                "message_data": {"karyawan_id": karyawan_id}
            }

        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "EDIT_KARYAWAN_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }
