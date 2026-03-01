import config
import time
import pymongo
import sys
import uuid
import traceback
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

class ecard_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    def get_all_ecards(self):
        try:
            ecard_list = list(self.mgdDB.db_ecard.find({}).sort("timestamp", -1))
            return ecard_list
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return []

    def get_ecard_by_id(self, ecard_id):
        try:
            ecard = self.mgdDB.db_ecard.find_one({"ecard_id": ecard_id})
            return ecard
        except Exception as e:
            self.webapp.logger.debug(traceback.format_exc())
            return None

    def add_ecard(self, params, files):
        try:
            name           = params.get("name")
            title          = params.get("title")
            department     = params.get("department")
            phone          = params.get("phone")
            email          = params.get("email")
            website        = params.get("website")
            company_name   = params.get("company_name")
            theme_color    = params.get("theme_color", "#1A1A1A")
            template_name  = params.get("template_name", "default")
            fk_karyawan_id = params.get("fk_karyawan_id", "")
            photo_url      = params.get("photo_url", "")

            if not name:
                return {
                    "message_action": "ADD_ECARD_FAILED",
                    "message_desc": "Name is required.",
                    "message_data": {}
                }

            if files and 'photo' in files:
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
                    photo_url = f"/static/uploads/{unique_filename}"

            ecard_id     = uuid.uuid4().hex
            current_time = int(time.time() * 1000)
            created_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ecard_rec = database.get_record("db_ecard")
            ecard_rec["ecard_id"]       = ecard_id
            ecard_rec["fk_karyawan_id"] = fk_karyawan_id
            ecard_rec["name"]           = name
            ecard_rec["title"]          = title
            ecard_rec["department"]     = department
            ecard_rec["phone"]          = phone
            ecard_rec["email"]          = email
            ecard_rec["website"]        = website
            ecard_rec["company_name"]   = company_name
            ecard_rec["theme_color"]    = theme_color
            ecard_rec["template_name"]  = template_name
            ecard_rec["photo"]          = photo_url
            ecard_rec["status"]         = "ACTIVE"
            ecard_rec["created_at"]     = created_at
            ecard_rec["timestamp"]      = current_time

            self.mgdDB.db_ecard.insert_one(ecard_rec)

            return {
                "message_action": "ADD_ECARD_SUCCESS",
                "message_desc": "E-card created successfully.",
                "message_data": {"ecard_id": ecard_id}
            }

        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "ADD_ECARD_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }

    def edit_ecard(self, ecard_id, params, files):
        try:
            name           = params.get("name")
            title          = params.get("title")
            department     = params.get("department")
            phone          = params.get("phone")
            email          = params.get("email")
            website        = params.get("website")
            company_name   = params.get("company_name")
            theme_color    = params.get("theme_color", "#1A1A1A")
            template_name  = params.get("template_name", "default")
            fk_karyawan_id = params.get("fk_karyawan_id", "")
            photo_url      = params.get("photo_url", "")

            if not name:
                return {
                    "message_action": "EDIT_ECARD_FAILED",
                    "message_desc": "Name is required.",
                    "message_data": {}
                }

            update_data = {
                "name": name,
                "title": title,
                "department": department,
                "phone": phone,
                "email": email,
                "website": website,
                "company_name": company_name,
                "theme_color": theme_color,
                "template_name": template_name,
                "fk_karyawan_id": fk_karyawan_id
            }

            if files and 'photo' in files:
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
            elif photo_url:
                update_data["photo"] = photo_url

            self.mgdDB.db_ecard.update_one(
                {"ecard_id": ecard_id},
                {"$set": update_data}
            )

            return {
                "message_action": "EDIT_ECARD_SUCCESS",
                "message_desc": "E-card updated successfully.",
                "message_data": {"ecard_id": ecard_id}
            }

        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "EDIT_ECARD_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }

    def delete_ecard(self, ecard_id):
        try:
            self.mgdDB.db_ecard.delete_one({"ecard_id": ecard_id})
            return {
                "message_action": "DELETE_ECARD_SUCCESS",
                "message_desc": "E-card deleted successfully.",
                "message_data": {"ecard_id": ecard_id}
            }
        except Exception as e:
            err_trace = traceback.format_exc()
            self.webapp.logger.debug(err_trace)
            return {
                "message_action": "DELETE_ECARD_FAILED",
                "message_desc": f"An internal error occurred: {str(e)}",
                "message_data": {"trace": err_trace}
            }
